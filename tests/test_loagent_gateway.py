"""LoAgent gateway: reporting, delivery, accounts, sending, queries and the API.

The real aiocqhttp adapter converts OneBot v11 payloads; its OneBot calls are
faked, so nothing reaches a protocol side. A stub backend (aiohttp) receives
the reported events.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
import pytest_asyncio
from aiocqhttp import Event
from aiohttp import web
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrbot.core.event_bus import EventBus
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)
from astrbot.loagent_gateway import GatewaySettings, LoAgentGateway
from astrbot.loagent_gateway import api as gateway_api
from astrbot.loagent_gateway import protocol as P
from astrbot.loagent_gateway.accounts import AccountTracker
from astrbot.loagent_gateway.media import MediaStore
from astrbot.loagent_gateway.outbound import OutboundError, plan_onebot

TOKEN = "gw-token"
SELF_ID = 10001
GROUP_ID = 123456
PNG = b"\x89PNG\r\n\x1a\nfake"


# --- fixtures --------------------------------------------------------------------


class FakeOneBot:
    """Records OneBot actions; answers the queries the adapter makes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_on: str | None = None
        self.next_id = 900

    async def call_action(self, action, **params):
        self.calls.append((action, params))
        if action == self.fail_on:
            raise RuntimeError("protocol side said no")
        if action == "get_msg":
            return {
                "message_id": 555,
                "message_type": "group",
                "group_id": GROUP_ID,
                "self_id": SELF_ID,
                "user_id": SELF_ID,
                "time": 1700000000,
                "sender": {"user_id": SELF_ID, "nickname": "小助手"},
                "message": [
                    {"type": "text", "data": {"text": "看这张图"}},
                    {
                        "type": "image",
                        "data": {"file": "A1.jpg", "url": "https://cdn/a1"},
                    },
                ],
            }
        if action == "get_group_member_info":
            names = {SELF_ID: "小助手", 30003: "Bob"}
            return {
                "user_id": params["user_id"],
                "card": names.get(params["user_id"], ""),
                "nickname": "n",
                "role": "member",
            }
        if action == "get_stranger_info":
            return {"user_id": params["user_id"], "nickname": "Stranger"}
        if action.startswith("send_"):
            self.next_id += 1
            return {"message_id": self.next_id}
        if action == "get_group_list":
            return [{"group_id": GROUP_ID, "group_name": "测试群", "member_count": 3}]
        if action == "get_friend_list":
            return [{"user_id": 20002, "nickname": "Alice", "remark": ""}]
        if action == "get_group_member_list":
            return [
                {
                    "user_id": 20002,
                    "nickname": "Alice",
                    "card": "阿丽",
                    "role": "admin",
                    "join_time": 1700000000,
                    "last_sent_time": 0,
                }
            ]
        if action == "get_group_msg_history":
            return {
                "messages": [
                    {
                        "message_id": 1,
                        "message_type": "group",
                        "group_id": GROUP_ID,
                        "user_id": 20002,
                        "time": 1700000300,
                        "sender": {"user_id": 20002, "nickname": "Alice"},
                        "message": [{"type": "text", "data": {"text": "old"}}],
                    }
                ]
            }
        return {}


def make_adapter(
    instance="qq_main", platform="qq"
) -> tuple[AiocqhttpAdapter, FakeOneBot]:
    adapter = AiocqhttpAdapter(
        {
            "id": instance,
            "ws_reverse_host": "127.0.0.1",
            "ws_reverse_port": 0,
            "loagent_platform": platform,
        },
        {},
        asyncio.Queue(),
    )
    fake = FakeOneBot()
    adapter.bot.call_action = fake.call_action
    adapter.bot._wsr_api_clients[str(SELF_ID)] = object()  # connected
    return adapter, fake


def make_gateway(tmp_path, platforms, endpoint="") -> LoAgentGateway:
    settings = GatewaySettings(
        enabled=True, endpoint=endpoint, token=TOKEN, data_dir=tmp_path
    )
    return LoAgentGateway(settings, lambda: platforms, astrbot_version="4.29.3")


async def astr_event(adapter, payload):
    abm = await adapter.convert_message(Event.from_payload(payload))
    return adapter.create_event(abm)


def group_payload(**extra) -> dict:
    payload = {
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 777,
        "group_id": GROUP_ID,
        "self_id": SELF_ID,
        "user_id": 20002,
        "time": 1700000100,
        "sender": {
            "user_id": 20002,
            "nickname": "Alice",
            "card": "阿丽",
            "role": "admin",
        },
        "message": [
            {"type": "reply", "data": {"id": "555"}},
            {"type": "at", "data": {"qq": str(SELF_ID)}},
            {"type": "text", "data": {"text": " 这是哪里？"}},
            {"type": "at", "data": {"qq": "30003"}},
            {"type": "at", "data": {"qq": "all"}},
            {
                "type": "image",
                "data": {
                    "file": "C3.png",
                    "url": "https://cdn/c3",
                    "summary": "[图片]",
                },
            },
            {
                "type": "image",
                "data": {"file": "base64://" + base64.b64encode(PNG).decode()},
            },
            {"type": "face", "data": {"id": "14"}},
        ],
    }
    payload.update(extra)
    return payload


def queued(gateway: LoAgentGateway, kind: str | None = None) -> list[dict]:
    bodies = [body for _, body in gateway.store.peek(1000)]
    return [b for b in bodies if kind is None or b["kind"] == kind]


class StubBackend:
    def __init__(self) -> None:
        self.batches: list[dict] = []
        self.statuses: list[int] = []

    async def handle(self, request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.json_response({}, status=401)
        status = self.statuses.pop(0) if self.statuses else 200
        if status == 200:
            self.batches.append(await request.json())
        return web.json_response({}, status=status)


@pytest_asyncio.fixture
async def backend():
    stub = StubBackend()
    app = web.Application()
    app.router.add_post("/v1/events", stub.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    stub.endpoint = f"http://127.0.0.1:{port}"
    try:
        yield stub
    finally:
        await runner.cleanup()


# --- inbound -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_message_is_reported_with_every_segment(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    await gw.ingest(await astr_event(adapter, group_payload()))

    [body] = queued(gw, "message")
    event = P.MessageEvent.model_validate(body)
    msg = event.message
    assert event.dedupe_key == "msg:qq:10001:777"
    assert msg.account == P.AccountRef(
        platform="qq", instance="qq_main", self_id="10001"
    )
    assert msg.conversation.kind == "group" and msg.conversation.id == str(GROUP_ID)
    assert msg.sender == P.Sender(
        user_id="20002", nickname="Alice", card="阿丽", role="admin", is_self=False
    )
    assert msg.sent_at_ms == 1700000100000
    assert msg.reply_to == "555"
    assert msg.at == ["10001", "30003", "all"]
    types = [s.type for s in msg.segments]
    assert types == ["reply", "at", "text", "at", "at_all", "image", "image", "sticker"]
    reply = msg.segments[0]
    assert reply.sender_id == "10001" and reply.text == "看这张图"
    assert [s.type for s in reply.segments] == ["text", "image"]
    assert msg.segments[5].media.url == "https://cdn/c3"
    local = msg.segments[6].media
    assert (
        local.url.startswith("gateway://")
        and local.mime == "image/png"
        and local.size == len(PNG)
    )
    assert gw.media.read_ref(local.url)[0] == PNG
    assert msg.segments[7].face_id == "14"
    # The account proved itself by talking.
    assert gw.tracker.get("qq_main", "10001").state == "online"


@pytest.mark.asyncio
async def test_unwoken_and_private_messages_are_reported_too(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    plain = group_payload(
        message_id=778, message=[{"type": "text", "data": {"text": "明天三点开会"}}]
    )
    private = {
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 779,
        "self_id": SELF_ID,
        "user_id": 20002,
        "time": 1700000200,
        "sender": {"user_id": 20002, "nickname": "Alice"},
        "message": [{"type": "text", "data": {"text": "在吗"}}],
    }
    await gw.ingest(await astr_event(adapter, plain))
    await gw.ingest(await astr_event(adapter, private))
    a, b = (P.MessageEvent.model_validate(x).message for x in queued(gw, "message"))
    assert a.at == [] and a.segments[0].text == "明天三点开会"
    assert b.conversation == P.Conversation(kind="private", id="20002")


@pytest.mark.asyncio
async def test_event_bus_hands_events_to_the_gateway_and_skips_the_pipeline(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    queue: asyncio.Queue = asyncio.Queue()
    scheduler = MagicMock()
    scheduler.execute = AsyncMock()
    conf_mgr = MagicMock()
    conf_mgr.get_conf_info.return_value = {"id": "default", "name": "default"}
    bus = EventBus(queue, {"default": scheduler}, conf_mgr)
    bus.observer = gw.observe_event
    await queue.put(await astr_event(adapter, group_payload()))
    task = asyncio.create_task(bus.dispatch())
    for _ in range(50):
        await asyncio.sleep(0.01)
        if not gw._inbox.empty():
            break
    task.cancel()
    assert gw._inbox.qsize() == 1
    scheduler.execute.assert_not_called()

    # Turned off, the gateway lets AstrBot's pipeline run as before.
    gw.settings.enabled = False
    assert gw.observe_event(MagicMock()) is False


@pytest.mark.asyncio
async def test_notices_and_requests(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    base = {"post_type": "notice", "self_id": SELF_ID, "time": 1700000400}
    payloads = [
        {
            **base,
            "notice_type": "group_increase",
            "sub_type": "approve",
            "group_id": GROUP_ID,
            "user_id": 40004,
            "operator_id": 20002,
        },
        {
            **base,
            "notice_type": "group_decrease",
            "sub_type": "kick",
            "group_id": GROUP_ID,
            "user_id": 40004,
            "operator_id": 20002,
        },
        {
            **base,
            "notice_type": "group_recall",
            "group_id": GROUP_ID,
            "user_id": 20002,
            "operator_id": 20002,
            "message_id": 777,
        },
        {
            **base,
            "notice_type": "notify",
            "sub_type": "poke",
            "group_id": GROUP_ID,
            "user_id": 20002,
            "target_id": SELF_ID,
        },
        {**base, "notice_type": "friend_add", "user_id": 50005},
        {
            "post_type": "request",
            "request_type": "group",
            "sub_type": "invite",
            "self_id": SELF_ID,
            "group_id": GROUP_ID,
            "user_id": 60006,
            "comment": "来",
            "flag": "f1",
            "time": 1,
        },
        {
            **base,
            "notice_type": "group_ban",
            "sub_type": "ban",
            "group_id": GROUP_ID,
            "user_id": 40004,
            "operator_id": 20002,
            "duration": 600,
        },
    ]
    for payload in payloads:
        await gw.ingest(await astr_event(adapter, payload))
    events = [P.NoticeEvent.model_validate(x) for x in queued(gw, "notice")]
    notices = [e.notice for e in events]
    assert [n.type for n in notices] == [
        "member_joined",
        "member_left",
        "recalled",
        "poke",
        "friend_added",
        "request",
        "other",
    ]
    assert notices[1].kicked is True
    assert notices[2].message_id == "777"
    assert events[2].dedupe_key == "notice:qq:10001:recalled:777"
    assert notices[3].target_id == str(SELF_ID)
    assert events[4].conversation == P.Conversation(kind="private", id="50005")
    assert notices[5].request == "group_invite" and notices[5].flag == "f1"
    assert notices[6].raw["notice_type"] == "group_ban"


@pytest.mark.asyncio
async def test_bot_offline_marks_the_account_kicked(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    await gw.ingest(await astr_event(adapter, group_payload()))
    offline = {
        "post_type": "notice",
        "notice_type": "bot_offline",
        "self_id": SELF_ID,
        "user_id": SELF_ID,
        "tag": "被踢下线",
        "message": "账号在别处登录",
        "time": 1,
    }
    await gw.ingest(await astr_event(adapter, offline))
    status = gw.tracker.get("qq_main", str(SELF_ID))
    assert (status.state, status.reason, status.detail) == (
        "offline",
        "kicked",
        "账号在别处登录",
    )
    kinds = [b["kind"] for b in queued(gw)]
    assert kinds == ["account", "message", "account"]  # online, the message, offline


# --- delivery ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_retries_until_acknowledged(tmp_path, backend):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter], endpoint=backend.endpoint)
    await gw.ingest(await astr_event(adapter, group_payload()))
    backend.statuses = [503]
    async with aiohttp.ClientSession() as session:
        with pytest.raises(ConnectionError):
            await gw.deliver_once(session)
        assert gw.store.pending() == 2 and "503" in gw.last_error
        assert await gw.deliver_once(session) is True
        assert await gw.deliver_once(session) is False
    assert gw.store.pending() == 0
    [batch] = backend.batches
    P.EventBatch.model_validate(batch)
    assert [e["kind"] for e in batch["events"]] == ["account", "message"]
    assert gw.health().outbox.pending == 0 and gw.health().outbox.last_error is None


@pytest.mark.asyncio
async def test_rejected_batches_are_set_aside(tmp_path, backend):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter], endpoint=backend.endpoint)
    await gw.ingest(await astr_event(adapter, group_payload()))
    backend.statuses = [422]
    async with aiohttp.ClientSession() as session:
        assert await gw.deliver_once(session) is True
    assert gw.store.pending() == 0 and gw.store.dead_count() == 2


@pytest.mark.asyncio
async def test_outbox_survives_a_restart(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    await gw.ingest(await astr_event(adapter, group_payload()))
    gw.store.close()
    again = make_gateway(tmp_path, [adapter])
    assert again.store.pending() == 2


@pytest.mark.asyncio
async def test_no_endpoint_keeps_events(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    await gw.ingest(await astr_event(adapter, group_payload()))
    async with aiohttp.ClientSession() as session:
        with pytest.raises(ConnectionError):
            await gw.deliver_once(session)
    assert gw.store.pending() == 2 and "endpoint" in gw.last_error


# --- accounts ------------------------------------------------------------------


def test_tracker_heartbeats_timeouts_and_reconnects():
    now = [1_000_000]
    emitted: list[P.AccountStatus] = []
    tracker = AccountTracker(emitted.append, heartbeat_grace=3, clock=lambda: now[0])
    ref = P.AccountRef(platform="qq", instance="qq_main", self_id="1")
    up = {"1": True}
    tracker.connected(ref)
    tracker.heartbeat(ref, online=True, good=True, interval_ms=30_000)
    assert [s.state for s in emitted] == ["connecting", "online"]

    now[0] += 60_000
    tracker.check(lambda r: up[r.self_id])
    assert emitted[-1].state == "online"  # within 3 intervals
    now[0] += 40_000
    tracker.check(lambda r: up[r.self_id])
    assert (emitted[-1].state, emitted[-1].reason) == ("offline", "heartbeat_timeout")

    tracker.heartbeat(ref, online=True, good=True, interval_ms=None)
    assert emitted[-1].state == "online"
    up["1"] = False
    tracker.check(lambda r: up[r.self_id])
    assert (emitted[-1].state, emitted[-1].reason) == ("offline", "disconnected")

    tracker.connected(ref)
    tracker.heartbeat(ref, online=False, good=True, interval_ms=None)
    assert (emitted[-1].state, emitted[-1].reason) == ("offline", "unhealthy")
    count = len(emitted)
    tracker.heartbeat(ref, online=False, good=True, interval_ms=None)
    assert len(emitted) == count  # no repeat without a change


@pytest.mark.asyncio
async def test_meta_events_drive_account_state(tmp_path):
    adapter, _ = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    gw.check_accounts()  # hooks the instance
    handlers = adapter.bot._bus._subscribers["meta_event"]
    assert handlers
    lifecycle = {
        "post_type": "meta_event",
        "meta_event_type": "lifecycle",
        "sub_type": "connect",
        "self_id": SELF_ID,
    }
    heartbeat = {
        "post_type": "meta_event",
        "meta_event_type": "heartbeat",
        "self_id": SELF_ID,
        "interval": 30000,
        "status": {"online": True, "good": True},
    }
    await adapter.bot._bus.emit("meta_event", Event.from_payload(lifecycle))
    assert gw.tracker.get("qq_main", str(SELF_ID)).state == "connecting"
    await adapter.bot._bus.emit("meta_event", Event.from_payload(heartbeat))
    assert gw.tracker.get("qq_main", str(SELF_ID)).state == "online"

    adapter.bot._wsr_api_clients.clear()
    gw.check_accounts()
    assert gw.tracker.get("qq_main", str(SELF_ID)).reason == "disconnected"

    adapter.status = PlatformStatus.ERROR
    adapter.record_error("boom")
    gw.check_accounts()
    assert gw.tracker.get("qq_main", str(SELF_ID)).reason == "platform_error"

    adapter.clear_errors()  # back to running, but still not connected
    gw.check_accounts()
    assert gw.tracker.get("qq_main", str(SELF_ID)).reason == "disconnected"

    gw._platforms = lambda: []
    gw.check_accounts()
    assert gw.tracker.get("qq_main", str(SELF_ID)).reason == "stopped"


# --- sending -------------------------------------------------------------------


def send_request(
    segments,
    *,
    request_id="r1",
    kind="group",
    conv=str(GROUP_ID),
    platform="qq",
    instance="qq_main",
) -> P.SendRequest:
    return P.SendRequest.model_validate(
        {
            "v": 1,
            "request_id": request_id,
            "account": {
                "platform": platform,
                "instance": instance,
                "self_id": str(SELF_ID),
            },
            "conversation": {"kind": kind, "id": conv},
            "segments": segments,
        }
    )


@pytest.mark.asyncio
async def test_send_group_message_with_self_id(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    req = send_request(
        [
            {"type": "at", "user_id": "20002"},
            {"type": "text", "text": " 这是故宫。"},
            {"type": "reply", "message_id": "777"},
            {
                "type": "image",
                "media": {
                    "url": "data:image/png;base64," + base64.b64encode(PNG).decode()
                },
            },
            {"type": "sticker", "face_id": "14"},
        ]
    )
    result = await gw.send(req)
    [(action, params)] = fake.calls
    assert action == "send_group_msg"
    assert params["self_id"] == SELF_ID and params["group_id"] == GROUP_ID
    assert params["message"] == [
        {"type": "reply", "data": {"id": "777"}},
        {"type": "at", "data": {"qq": "20002"}},
        {"type": "text", "data": {"text": " 这是故宫。"}},
        {
            "type": "image",
            "data": {"file": "base64://" + base64.b64encode(PNG).decode()},
        },
        {"type": "face", "data": {"id": "14"}},
    ]
    assert (
        result.message_ids == ["901"] and result.degraded == [] and not result.duplicate
    )

    again = await gw.send(req)
    assert again.duplicate is True and again.message_ids == ["901"]
    assert len(fake.calls) == 1  # not sent twice


@pytest.mark.asyncio
async def test_send_splits_standalone_segments_and_degrades(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    uploaded = gw.media.put(b"pdf", name="资料.pdf")
    req = send_request(
        [
            {"type": "text", "text": "资料："},
            {"type": "file", "media": {"url": uploaded.url, "name": "资料.pdf"}},
            {"type": "voice", "media": {"url": "https://example.com/43.mp3"}},
            {
                "type": "forward",
                "nodes": [
                    {
                        "sender_id": "1",
                        "sender_name": "A",
                        "segments": [{"type": "text", "text": "一"}],
                    }
                ],
            },
            {"type": "share", "url": "https://e/a", "title": "文章"},
            {"type": "poke", "target_id": "20002"},
            {"type": "unknown", "raw_type": "x", "data": {}},
        ],
        kind="private",
        conv="20002",
    )
    result = await gw.send(req)
    actions = [a for a, _ in fake.calls]
    assert actions == [
        "send_private_msg",
        "send_private_msg",
        "send_private_msg",
        "send_private_forward_msg",
        "send_private_msg",
        "friend_poke",
    ]
    assert fake.calls[1][1]["message"] == [
        {
            "type": "file",
            "data": {
                "file": "base64://" + base64.b64encode(b"pdf").decode(),
                "name": "资料.pdf",
            },
        }
    ]
    assert fake.calls[2][1]["message"] == [
        {"type": "record", "data": {"file": "https://example.com/43.mp3"}}
    ]
    assert fake.calls[3][1]["messages"][0]["data"]["content"] == [
        {"type": "text", "data": {"text": "一"}}
    ]
    assert fake.calls[4][1]["message"] == [
        {"type": "text", "data": {"text": "文章\nhttps://e/a"}}
    ]
    assert all(params["self_id"] == SELF_ID for _, params in fake.calls)
    assert [(d.index, d.from_, d.to) for d in result.degraded] == [
        (4, "share", "text"),
        (6, "unknown", "dropped"),
    ]
    assert result.to_json()["degraded"][0]["from"] == "share"
    assert len(result.message_ids) == 5


def test_wechat_sends_text_at_and_reply_only(tmp_path):
    store = MediaStore(tmp_path)
    segs = send_request(
        [
            {"type": "reply", "message_id": "41"},
            {"type": "at", "user_id": "800345"},
            {"type": "text", "text": " 好"},
            {"type": "image", "media": {"url": "https://e/x.png"}},
            {"type": "location", "lat": 1.5, "lon": 2.5, "title": "这里"},
        ],
        platform="wechat",
    ).segments
    plan = plan_onebot("wechat", segs, store)
    assert plan.batches == [
        (
            "msg",
            [
                {"type": "reply", "data": {"id": "41"}},
                {"type": "at", "data": {"qq": "800345"}},
                {"type": "text", "data": {"text": " 好"}},
                {"type": "text", "data": {"text": "[位置] 这里 (1.5, 2.5)"}},
            ],
        )
    ]
    assert [(d.from_, d.to) for d in plan.degraded] == [
        ("image", "dropped"),
        ("location", "text"),
    ]


@pytest.mark.asyncio
async def test_send_errors(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    text = [{"type": "text", "text": "hi"}]

    with pytest.raises(OutboundError) as e:
        await gw.send(send_request(text, instance="nope"))
    assert e.value.code == "account_not_found"
    with pytest.raises(OutboundError) as e:
        await gw.send(send_request(text, platform="wechat"))
    assert e.value.code == "account_not_found"
    with pytest.raises(OutboundError) as e:
        await gw.send(send_request([{"type": "image", "media": {}}]))
    assert e.value.code == "media_unavailable"
    with pytest.raises(OutboundError) as e:
        await gw.send(send_request([{"type": "unknown", "raw_type": "x", "data": {}}]))
    assert e.value.code == "unsupported_segment"

    fake.fail_on = "send_group_msg"
    with pytest.raises(OutboundError) as e:
        await gw.send(send_request(text, request_id="r-fail"))
    assert (e.value.code, e.value.retryable) == ("platform_error", True)
    assert gw.store.sent_result("r-fail") is None  # a retry may send it

    fake.fail_on = None
    adapter.bot._wsr_api_clients.clear()
    with pytest.raises(OutboundError) as e:
        await gw.send(send_request(text, request_id="r-off"))
    assert (e.value.code, e.value.retryable) == ("account_offline", True)


@pytest.mark.asyncio
async def test_partial_send_failure_is_not_retryable(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    fake.fail_on = "group_poke"
    with pytest.raises(OutboundError) as e:
        await gw.send(
            send_request(
                [{"type": "text", "text": "看"}, {"type": "poke", "target_id": "1"}]
            )
        )
    assert e.value.retryable is False and "前 1 条已发出" in e.value.message


# --- queries -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queries(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    convs = await gw.conversations("qq_main", str(SELF_ID))
    assert [(c.kind, c.id, c.name) for c in convs.conversations] == [
        ("group", str(GROUP_ID), "测试群"),
        ("private", "20002", "Alice"),
    ]
    members = await gw.members("qq_main", str(SELF_ID), str(GROUP_ID))
    assert members.members[0] == P.Member(
        user_id="20002",
        nickname="Alice",
        card="阿丽",
        role="admin",
        joined_at_ms=1700000000000,
    )
    profile = await gw.profile("qq_main", str(SELF_ID), "777", None)
    assert profile.profile.nickname == "Stranger"
    history = await gw.history(
        "qq_main", str(SELF_ID), "group", str(GROUP_ID), 500, None
    )
    assert history.messages[0].segments[0].text == "old"
    assert dict(fake.calls[-1][1])["count"] == 100
    assert all(params.get("self_id") == SELF_ID for _, params in fake.calls)


# --- HTTP API ------------------------------------------------------------------


def api_client(gw: LoAgentGateway) -> TestClient:
    app = FastAPI()
    app.state.loagent_gateway = gw
    gateway_api.install(app)

    @app.post("/api/v1/updates/core")
    async def update():
        return {"status": "ok"}

    return TestClient(app)


def test_api_auth_send_media_and_update_refusal(tmp_path):
    adapter, fake = make_adapter()
    gw = make_gateway(tmp_path, [adapter])
    client = api_client(gw)
    auth = {"Authorization": f"Bearer {TOKEN}"}

    assert client.get("/api/v1/loagent/health").status_code == 401
    assert (
        client.get(
            "/api/v1/loagent/health", headers={"Authorization": "Bearer nope"}
        ).json()["error"]["code"]
        == "unauthorized"
    )
    health = client.get("/api/v1/loagent/health", headers=auth).json()
    assert P.Health.model_validate(health).enabled is True

    up = client.post(
        "/api/v1/loagent/media",
        content=PNG,
        headers={**auth, "Content-Type": "image/png", "X-Media-Name": "%E5%9B%BE.png"},
    )
    media = P.MediaUploadResponse.model_validate(up.json()).media
    assert media.name == "图.png" and media.mime == "image/png"
    down = client.get(f"/api/v1/loagent/media/{media.sha256}", headers=auth)
    assert down.content == PNG and down.headers["content-type"] == "image/png"
    assert (
        client.get("/api/v1/loagent/media/" + "0" * 64, headers=auth).status_code == 422
    )

    body = send_request([{"type": "image", "media": {"url": media.url}}]).to_json()
    sent = client.post("/api/v1/loagent/send", json=body, headers=auth)
    assert sent.status_code == 200, sent.text
    assert P.SendResult.model_validate(sent.json()).message_ids == ["901"]

    bad = client.post("/api/v1/loagent/send", json={**body, "v": 2}, headers=auth)
    assert (
        bad.status_code == 400 and bad.json()["error"]["code"] == "unsupported_version"
    )
    bad = client.post("/api/v1/loagent/send", json={"v": 1}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_request"
    missing = client.get("/api/v1/loagent/members?instance=qq_main", headers=auth)
    assert missing.status_code == 400

    accounts = client.get("/api/v1/loagent/accounts", headers=auth).json()
    P.AccountsResponse.model_validate(accounts)

    assert client.post("/api/v1/updates/core").status_code == 403
    gw.settings.enabled = False
    assert client.post("/api/v1/updates/core").status_code == 200


def test_api_without_token_is_closed(tmp_path):
    gw = make_gateway(tmp_path, [])
    gw.settings.token = ""
    res = api_client(gw).get(
        "/api/v1/loagent/accounts", headers={"Authorization": "Bearer "}
    )
    assert res.status_code == 503 and res.json()["error"]["code"] == "not_configured"


# --- settings and media --------------------------------------------------------


def test_settings_env_overrides_config(tmp_path):
    conf = {
        "loagent_gateway": {"enabled": False, "endpoint": "http://a/", "token": "c"}
    }
    s = GatewaySettings.resolve(conf, env={})
    assert (s.enabled, s.endpoint, s.token) == (False, "http://a", "c")
    s = GatewaySettings.resolve(
        conf,
        env={
            "LOAGENT_GATEWAY": "1",
            "LOAGENT_GATEWAY_ENDPOINT": "http://b",
            "LOAGENT_GATEWAY_TOKEN": "e",
        },
    )
    assert (s.enabled, s.endpoint, s.token) == (True, "http://b", "e")


def test_media_store_ingest_and_cleanup(tmp_path):
    store = MediaStore(tmp_path / "m")
    local = tmp_path / "x.jpg"
    local.write_bytes(b"\xff\xd8\xffjpeg")
    assert store.ingest(["https://cdn/x", str(local)]).url == "https://cdn/x"
    m = store.ingest(["ABCD.jpg", local.as_uri()])
    assert (
        m.mime == "image/jpeg"
        and m.name == "ABCD.jpg"
        and m.url.startswith("gateway://")
    )
    assert store.ingest(["not-a-path.amr"]) == P.Media(name="not-a-path.amr")
    assert store.cleanup(7) == 0
    assert store.cleanup(-1) == 1
    assert store.read_ref(m.url) is None
