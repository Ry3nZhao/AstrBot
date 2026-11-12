"""The gateway: reports events, sends messages, answers queries, watches accounts.

Wiring (the only places it touches AstrBot's own code):

- ``EventBus.observer`` → :meth:`LoAgentGateway.observe_event` sees every event
  an adapter puts on the queue. When the gateway is enabled it takes the event
  and AstrBot's pipeline (wake rules, whitelist, plugins, the legacy
  ``loagent_forward``) does not run.
- ``AstrBotCoreLifecycle`` creates the gateway and runs :meth:`run` with its
  other tasks.
- ``create_dashboard_asgi_app`` mounts the HTTP API (``api.install``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import weakref
from collections.abc import Callable
from typing import Any

import aiohttp

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import Platform, PlatformStatus

from . import convert
from . import protocol as P
from .accounts import AccountTracker
from .convert import ONEBOT, platform_kind
from .media import MediaStore
from .outbound import OutboundError, chain_from_segments, plan_onebot
from .settings import GatewaySettings, apply_platforms, declared_platforms
from .store import GatewayStore, now_ms

PlatformsGetter = Callable[[], list[Platform]]


def _id_param(value: str) -> int | str:
    """OneBot implementations want numeric ids as numbers."""
    return int(value) if value.isdigit() else value


def _ms(seconds: Any) -> int | None:
    try:
        return int(seconds) * 1000 if seconds else None
    except (TypeError, ValueError):
        return None


class LoAgentGateway:
    def __init__(
        self,
        settings: GatewaySettings,
        platforms: PlatformsGetter,
        *,
        astrbot_version: str = "",
        store: GatewayStore | None = None,
    ) -> None:
        self.settings = settings
        self._platforms = platforms
        self.astrbot_version = astrbot_version
        self._store = store  # opened on first use: a disabled gateway writes nothing
        self.media = MediaStore(settings.data_dir / "media")
        self.tracker = AccountTracker(
            self._emit_account, heartbeat_grace=settings.heartbeat_grace
        )
        self._inbox: asyncio.Queue[AstrMessageEvent] = asyncio.Queue()
        self._wake = asyncio.Event()
        self._send_locks: dict[str, asyncio.Lock] = {}
        self._hooked: weakref.WeakSet[Platform] = weakref.WeakSet()
        self._known_instances: set[str] = set()
        self.last_delivered_ms: int | None = None
        self.last_error: str | None = None

    @property
    def store(self) -> GatewayStore:
        if self._store is None:
            self._store = GatewayStore(self.settings.data_dir / "gateway.db")
        return self._store

    @classmethod
    def from_core(cls, core) -> LoAgentGateway:
        from astrbot.core.config.default import VERSION

        settings = GatewaySettings.resolve(core.astrbot_config)
        if settings.enabled:
            # The protocol sides LoAgent runs (LOAGENT_GATEWAY_PLATFORMS), before the
            # platform manager starts the instances.
            try:
                apply_platforms(core.astrbot_config["platform"], declared_platforms())
            except ValueError as e:
                logger.error(f"LoAgent gateway: {e}")
        return cls(
            settings,
            lambda: list(core.platform_manager.platform_insts),
            astrbot_version=VERSION,
        )

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    # --- inbound --------------------------------------------------------

    def observe_event(self, event: AstrMessageEvent) -> bool:
        """EventBus hook. True: the gateway took the event, skip the pipeline."""
        if not self.enabled:
            return False
        self._inbox.put_nowait(event)
        return True

    def _instance(self, instance_id: str) -> Platform | None:
        return next((p for p in self._platforms() if p.meta().id == instance_id), None)

    def _account(
        self, inst: Platform | None, instance_id: str, adapter: str, self_id: str
    ) -> P.AccountRef:
        conf = inst.config if inst is not None else {}
        return P.AccountRef(
            platform=platform_kind(adapter, conf), instance=instance_id, self_id=self_id
        )

    def account_of_event(self, event: AstrMessageEvent) -> P.AccountRef:
        instance_id = event.get_platform_id()
        return self._account(
            self._instance(instance_id),
            instance_id,
            event.get_platform_name(),
            str(event.get_self_id() or ""),
        )

    async def ingest(self, event: AstrMessageEvent) -> None:
        """Turn one AstrBot event into protocol events and queue them."""
        account = self.account_of_event(event)
        now = now_ms()
        raw = convert.raw_onebot(event)
        if raw is not None and raw.get("post_type") in ("notice", "request"):
            if raw.get("notice_type") == "bot_offline":
                self.tracker.kicked(
                    account, str(raw.get("message") or raw.get("tag") or "") or None
                )
                return
            got = convert.onebot_notice(raw, account)
            if got is None:
                return
            conversation, notice, key = got
            out: P.Event = convert.notice_event(account, conversation, notice, key, now)
            self.tracker.activity(account)
        else:
            message = await asyncio.to_thread(
                convert.message_from_event, event, account, self.media, now
            )
            out = convert.message_event(message, now)
            self.tracker.activity(account)
        await asyncio.to_thread(self.store.enqueue, out.id, out.to_json())
        self._wake.set()

    def _emit_account(self, status: P.AccountStatus) -> None:
        if not self.enabled:
            return
        event = convert.account_event(status, now_ms())
        logger.info(
            "LoAgent gateway: account %s is %s%s",
            status.account.key(),
            status.state,
            f" ({status.reason})" if status.reason else "",
        )
        self.store.enqueue(event.id, event.to_json())
        self._wake.set()

    # --- delivery -------------------------------------------------------

    async def deliver_once(self, session: aiohttp.ClientSession) -> bool:
        """POST one batch. True when something was delivered or buried."""
        batch = await asyncio.to_thread(self.store.peek, self.settings.batch_size)
        if not batch:
            return False
        if not self.settings.endpoint:
            self.last_error = "no endpoint configured (LOAGENT_GATEWAY_ENDPOINT)"
            raise ConnectionError(self.last_error)
        seqs = [seq for seq, _ in batch]
        headers = (
            {"Authorization": f"Bearer {self.settings.token}"}
            if self.settings.token
            else {}
        )
        url = self.settings.endpoint + P.EVENTS_PATH
        await asyncio.to_thread(self.store.note_attempt, seqs)
        try:
            async with session.post(
                url,
                json={"events": [body for _, body in batch]},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout),
            ) as resp:
                if 200 <= resp.status < 300:
                    await asyncio.to_thread(self.store.ack, seqs)
                    self.last_delivered_ms = now_ms()
                    self.last_error = None
                    return True
                text = (await resp.text())[:300]
                if resp.status in (400, 413, 422):
                    # The backend will never take these: keep them aside.
                    reason = f"HTTP {resp.status}: {text}"
                    await asyncio.to_thread(self.store.bury, seqs, reason)
                    logger.error(
                        "LoAgent gateway: backend rejected %d events: %s",
                        len(seqs),
                        reason,
                    )
                    return True
                self.last_error = f"HTTP {resp.status}: {text}"
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        raise ConnectionError(self.last_error)

    async def _deliver_loop(self) -> None:
        backoff = 1.0
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    if await self.deliver_once(session):
                        backoff = 1.0
                        continue
                    self._wake.clear()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._wake.wait(), timeout=5)
                except ConnectionError:
                    logger.warning(
                        "LoAgent gateway: delivery failed (%s); %d pending, retry in %.0fs",
                        self.last_error,
                        await asyncio.to_thread(self.store.pending),
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)

    async def _ingest_loop(self) -> None:
        while True:
            event = await self._inbox.get()
            try:
                await self.ingest(event)
            except Exception:
                logger.exception("LoAgent gateway: could not report an event")

    # --- accounts -------------------------------------------------------

    def _ws_connected(self, ref: P.AccountRef) -> bool | None:
        inst = self._instance(ref.instance)
        if inst is None:
            return False
        clients = getattr(getattr(inst, "bot", None), "_wsr_api_clients", None)
        if isinstance(clients, dict):
            return ref.self_id in clients
        return None

    def hook_instance(self, inst: Platform) -> None:
        """Listen to an OneBot instance's meta events (connect, heartbeat)."""
        if inst in self._hooked or inst.meta().name != ONEBOT:
            return
        bot = getattr(inst, "bot", None)
        if bot is None:
            return
        self._hooked.add(inst)
        instance_id = inst.meta().id

        async def on_meta(ev) -> None:
            self_id = str(ev.get("self_id") or "")
            if not self_id:
                return
            ref = self._account(inst, instance_id, ONEBOT, self_id)
            kind = ev.get("meta_event_type")
            if kind == "lifecycle" and ev.get("sub_type") in (
                "connect",
                "enable",
                None,
            ):
                self.tracker.connected(ref)
                asyncio.create_task(self._fetch_nickname(inst, ref))
            elif kind == "heartbeat":
                status = ev.get("status") or {}
                self.tracker.heartbeat(
                    ref,
                    online=status.get("online"),
                    good=status.get("good"),
                    interval_ms=ev.get("interval"),
                )

        bot.subscribe("meta_event", on_meta)

    async def _fetch_nickname(self, inst: Platform, ref: P.AccountRef) -> None:
        with contextlib.suppress(Exception):
            info = await inst.bot.call_action(
                "get_login_info", self_id=_id_param(ref.self_id)
            )
            if isinstance(info, dict) and info.get("nickname"):
                self.tracker.set_nickname(ref, str(info["nickname"]))

    def check_accounts(self) -> None:
        current = {}
        for inst in self._platforms():
            instance_id = inst.meta().id
            current[instance_id] = inst
            self.hook_instance(inst)
            if inst.status == PlatformStatus.ERROR:
                err = inst.last_error.message if inst.last_error else None
                self.tracker.mark_instance(
                    instance_id, "offline", "platform_error", err
                )
            elif inst.status == PlatformStatus.STOPPED:
                self.tracker.mark_instance(instance_id, "offline", "stopped")
            else:
                self.tracker.instance_recovered(instance_id)
        for gone in self._known_instances - set(current):
            self.tracker.forget_instance(gone)
        self._known_instances = set(current)
        self.tracker.check(self._ws_connected)

    async def _watch_loop(self) -> None:
        ticks = 0
        while True:
            try:
                self.check_accounts()
                if ticks % 720 == 0:  # hourly
                    await asyncio.to_thread(
                        self.media.cleanup, self.settings.media_retention_days
                    )
                    await asyncio.to_thread(
                        self.store.prune_sent, self.settings.send_retention_days
                    )
            except Exception:
                logger.exception("LoAgent gateway: account check failed")
            ticks += 1
            await asyncio.sleep(5)

    async def run(self) -> None:
        if not self.enabled:
            logger.info("LoAgent gateway is off (set LOAGENT_GATEWAY=1 to turn it on).")
            return
        if not self.settings.token:
            logger.warning(
                "LoAgent gateway: no LOAGENT_GATEWAY_TOKEN; its API refuses every call."
            )
        logger.info(
            "LoAgent gateway on: reporting to %s; AstrBot's pipeline is bypassed.",
            self.settings.endpoint or "(no endpoint yet)",
        )
        await asyncio.gather(
            self._ingest_loop(), self._deliver_loop(), self._watch_loop()
        )

    # --- auth -----------------------------------------------------------

    def check_token(self, authorization: str | None) -> str | None:
        """None when the bearer token is right, else the error code."""
        if not self.settings.token:
            return "not_configured"
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), self.settings.token.encode()):
            return "unauthorized"
        return None

    # --- outbound -------------------------------------------------------

    def _resolve(self, account: P.AccountRef) -> Platform:
        inst = self._instance(account.instance)
        if inst is None:
            raise OutboundError(
                "account_not_found", f"no platform instance {account.instance!r}"
            )
        kind = platform_kind(inst.meta().name, inst.config)
        if kind != account.platform:
            raise OutboundError(
                "account_not_found",
                f"instance {account.instance!r} is {kind!r}, not {account.platform!r}",
            )
        return inst

    def _require_online(self, inst: Platform, account: P.AccountRef) -> None:
        if inst.status in (PlatformStatus.ERROR, PlatformStatus.STOPPED):
            raise OutboundError(
                "account_offline",
                f"instance {account.instance} is {inst.status.value}",
                True,
            )
        if inst.meta().name == ONEBOT and self._ws_connected(account) is False:
            raise OutboundError(
                "account_offline",
                f"账号 {account.key()} 没有连上（协议端未连接）",
                True,
            )
        status = self.tracker.get(account.instance, account.self_id)
        if (
            status is not None
            and status.state == "offline"
            and status.reason in ("kicked", "unhealthy")
        ):
            raise OutboundError(
                "account_offline",
                f"账号 {account.key()} 不在线（{status.reason}）",
                True,
            )

    async def send(self, req: P.SendRequest) -> P.SendResult:
        if req.v != P.PROTOCOL_VERSION:
            raise OutboundError(
                "unsupported_version", f"protocol v{req.v} is not supported"
            )
        if len(self._send_locks) > 1000:
            self._send_locks = {k: v for k, v in self._send_locks.items() if v.locked()}
        lock = self._send_locks.setdefault(req.request_id, asyncio.Lock())
        async with lock:
            stored = await asyncio.to_thread(self.store.sent_result, req.request_id)
            if stored is not None:
                result = P.SendResult.model_validate(stored)
                result.duplicate = True
                return result
            inst = self._resolve(req.account)
            self._require_online(inst, req.account)
            if inst.meta().name == ONEBOT:
                message_ids, degraded = await self._send_onebot(inst, req)
            else:
                message_ids, degraded = await self._send_generic(inst, req)
            result = P.SendResult(
                request_id=req.request_id, message_ids=message_ids, degraded=degraded
            )
            await asyncio.to_thread(
                self.store.record_sent, req.request_id, result.to_json()
            )
            return result

    async def _send_onebot(
        self, inst: Platform, req: P.SendRequest
    ) -> tuple[list[str], list[P.Degradation]]:
        plan = await asyncio.to_thread(
            plan_onebot, req.account.platform, req.segments, self.media
        )
        if not plan.batches:
            raise OutboundError(
                "unsupported_segment", "nothing in the request can be sent here"
            )
        bot = inst.bot
        self_id = _id_param(req.account.self_id)
        target = _id_param(req.conversation.id)
        group = req.conversation.kind == "group"
        ids: list[str] = []
        for done, (kind, payload) in enumerate(plan.batches):
            try:
                if kind == "msg":
                    if group:
                        ret = await bot.call_action(
                            "send_group_msg",
                            group_id=target,
                            message=payload,
                            self_id=self_id,
                        )
                    else:
                        ret = await bot.call_action(
                            "send_private_msg",
                            user_id=target,
                            message=payload,
                            self_id=self_id,
                        )
                elif kind == "forward":
                    if group:
                        ret = await bot.call_action(
                            "send_group_forward_msg",
                            group_id=target,
                            messages=payload,
                            self_id=self_id,
                        )
                    else:
                        ret = await bot.call_action(
                            "send_private_forward_msg",
                            user_id=target,
                            messages=payload,
                            self_id=self_id,
                        )
                else:  # poke
                    user = _id_param(payload)
                    if group:
                        ret = await bot.call_action(
                            "group_poke", group_id=target, user_id=user, self_id=self_id
                        )
                    else:
                        ret = await bot.call_action(
                            "friend_poke", user_id=user, self_id=self_id
                        )
            except Exception as exc:
                partial = f"（前 {done} 条已发出：{ids}）" if done else ""
                raise OutboundError(
                    "platform_error",
                    f"{type(exc).__name__}: {exc}{partial}",
                    retryable=done == 0,
                ) from exc
            if isinstance(ret, dict) and ret.get("message_id") not in (None, ""):
                ids.append(str(ret["message_id"]))
        return ids, plan.degraded

    async def _send_generic(
        self, inst: Platform, req: P.SendRequest
    ) -> tuple[list[str], list[P.Degradation]]:
        chain, degraded = await asyncio.to_thread(
            chain_from_segments, req.segments, self.media
        )
        if not chain:
            raise OutboundError(
                "unsupported_segment", "nothing in the request can be sent here"
            )
        session = MessageSesion(
            platform_name=req.account.instance,
            message_type=MessageType.GROUP_MESSAGE
            if req.conversation.kind == "group"
            else MessageType.FRIEND_MESSAGE,
            session_id=convert.session_id_for(inst.meta().name, req.conversation),
        )
        try:
            await inst.send_by_session(session, MessageChain(chain))
        except Exception as exc:
            raise OutboundError(
                "platform_error", f"{type(exc).__name__}: {exc}", True
            ) from exc
        return [], degraded

    # --- queries --------------------------------------------------------

    def health(self) -> P.Health:
        return P.Health(
            v=P.PROTOCOL_VERSION,
            astrbot_version=self.astrbot_version,
            enabled=self.enabled,
            outbox=P.OutboxStatus(
                pending=self.store.pending(),
                last_delivered_ms=self.last_delivered_ms,
                last_error=self.last_error,
            ),
        )

    def accounts(self) -> P.AccountsResponse:
        return P.AccountsResponse(accounts=self.tracker.all())

    def _onebot(self, instance: str, self_id: str) -> tuple[Platform, P.AccountRef]:
        inst = self._instance(instance)
        if inst is None:
            raise OutboundError(
                "account_not_found", f"no platform instance {instance!r}"
            )
        if inst.meta().name != ONEBOT:
            raise OutboundError(
                "unsupported", f"queries are not available for {inst.meta().name}"
            )
        return inst, self._account(inst, instance, ONEBOT, self_id)

    async def _call(
        self, inst: Platform, action: str, ref: P.AccountRef, **params
    ) -> Any:
        try:
            return await inst.bot.call_action(
                action, self_id=_id_param(ref.self_id), **params
            )
        except Exception as exc:
            retcode = getattr(exc, "retcode", None)
            if retcode == 1404:
                raise OutboundError(
                    "unsupported", f"{action} is not supported by this protocol side"
                ) from exc
            raise OutboundError(
                "platform_error", f"{action}: {type(exc).__name__}: {exc}", True
            ) from exc

    async def conversations(
        self, instance: str, self_id: str
    ) -> P.ConversationsResponse:
        inst, ref = self._onebot(instance, self_id)
        out: list[P.ConversationInfo] = []
        for g in await self._call(inst, "get_group_list", ref) or []:
            out.append(
                P.ConversationInfo(
                    kind="group",
                    id=str(g.get("group_id")),
                    name=g.get("group_name") or None,
                    member_count=g.get("member_count"),
                )
            )
        try:
            friends = await self._call(inst, "get_friend_list", ref) or []
        except OutboundError as exc:
            if exc.code != "unsupported":
                raise
            friends = []  # WeChat's gateway has no friend list
        for f in friends:
            out.append(
                P.ConversationInfo(
                    kind="private",
                    id=str(f.get("user_id")),
                    name=f.get("remark") or f.get("nickname") or None,
                )
            )
        return P.ConversationsResponse(conversations=out)

    @staticmethod
    def _member(d: dict) -> P.Member:
        role = d.get("role")
        return P.Member(
            user_id=str(d.get("user_id") or ""),
            nickname=str(d.get("nickname") or d.get("nick") or ""),
            card=d.get("card") or None,
            role=role if role in ("owner", "admin", "member") else None,
            joined_at_ms=_ms(d.get("join_time")),
            last_sent_ms=_ms(d.get("last_sent_time")),
        )

    async def members(
        self, instance: str, self_id: str, group_id: str
    ) -> P.MembersResponse:
        inst, ref = self._onebot(instance, self_id)
        rows = await self._call(
            inst, "get_group_member_list", ref, group_id=_id_param(group_id)
        )
        return P.MembersResponse(members=[self._member(r) for r in rows or []])

    async def profile(
        self, instance: str, self_id: str, user_id: str, group_id: str | None
    ) -> P.ProfileResponse:
        inst, ref = self._onebot(instance, self_id)
        if group_id:
            row = await self._call(
                inst,
                "get_group_member_info",
                ref,
                group_id=_id_param(group_id),
                user_id=_id_param(user_id),
            )
        else:
            row = await self._call(
                inst, "get_stranger_info", ref, user_id=_id_param(user_id)
            )
        return P.ProfileResponse(profile=self._member(row or {"user_id": user_id}))

    async def history(
        self,
        instance: str,
        self_id: str,
        kind: str,
        conv_id: str,
        count: int,
        before: str | None,
    ) -> P.HistoryResponse:
        from aiocqhttp import Event as OneBotEvent

        inst, ref = self._onebot(instance, self_id)
        params: dict[str, Any] = {"count": max(1, min(count, 100))}
        if before:
            params["message_seq"] = _id_param(before)
        if kind == "group":
            ret = await self._call(
                inst,
                "get_group_msg_history",
                ref,
                group_id=_id_param(conv_id),
                **params,
            )
        else:
            ret = await self._call(
                inst,
                "get_friend_msg_history",
                ref,
                user_id=_id_param(conv_id),
                **params,
            )
        rows = (ret.get("messages") or []) if isinstance(ret, dict) else []
        out: list[P.Message] = []
        now = now_ms()
        for row in rows:
            row = {**row, "post_type": "message"}
            row.setdefault("self_id", _id_param(ref.self_id))
            ev = OneBotEvent.from_payload(row)
            if ev is None:
                continue
            try:
                abm = await inst._convert_handle_message_event(ev, get_reply=False)
            except Exception:
                logger.warning("LoAgent gateway: skip a history message it cannot read")
                continue
            astr_event = inst.create_event(abm)
            out.append(
                await asyncio.to_thread(
                    convert.message_from_event, astr_event, ref, self.media, now
                )
            )
        return P.HistoryResponse(messages=out)
