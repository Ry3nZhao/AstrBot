"""Account state: online, connecting, offline, and why.

Sources, for OneBot v11 instances (QQ through NapCat, WeChat through the
wechat-selkies gateway):

- ``meta_event`` ``lifecycle`` / ``connect``: the protocol side connected →
  ``connecting`` until it proves healthy;
- ``meta_event`` ``heartbeat``: ``status.online`` and ``status.good`` →
  ``online``, otherwise ``offline/unhealthy``; its ``interval`` sets the
  deadline for the next one;
- any message or notice from the account → ``online``;
- NapCat's ``bot_offline`` notice → ``offline/kicked`` (scan again);
- the watchdog: no heartbeat for ``heartbeat_grace`` intervals →
  ``offline/heartbeat_timeout`` (the 「假活」 case); the reverse WebSocket gone
  → ``offline/disconnected``; the AstrBot instance in error or removed →
  ``offline/platform_error`` / ``offline/stopped``.

Every change is handed to ``emit`` (which reports an ``account`` event).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import protocol as P
from .store import now_ms


@dataclass
class _Account:
    ref: P.AccountRef
    state: str = "connecting"
    reason: str | None = None
    detail: str | None = None
    nickname: str | None = None
    since_ms: int = 0
    last_seen_ms: int | None = None
    heartbeat_ms: int | None = None  # interval announced by the protocol side
    last_heartbeat_ms: int | None = None

    def status(self) -> P.AccountStatus:
        return P.AccountStatus(
            account=self.ref,
            state=self.state,
            reason=self.reason,
            detail=self.detail,
            nickname=self.nickname,
            since_ms=self.since_ms,
            last_seen_ms=self.last_seen_ms,
        )


class AccountTracker:
    def __init__(
        self,
        emit: Callable[[P.AccountStatus], None],
        *,
        heartbeat_grace: float = 3.0,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._emit = emit
        self._grace = heartbeat_grace
        self._clock = clock
        self._accounts: dict[tuple[str, str], _Account] = {}

    def get(self, instance: str, self_id: str) -> P.AccountStatus | None:
        acc = self._accounts.get((instance, self_id))
        return acc.status() if acc else None

    def all(self) -> list[P.AccountStatus]:
        return [a.status() for a in self._accounts.values()]

    def accounts_of(self, instance: str) -> list[P.AccountRef]:
        return [a.ref for (inst, _), a in self._accounts.items() if inst == instance]

    def _account(self, ref: P.AccountRef) -> tuple[_Account, bool]:
        key = (ref.instance, ref.self_id)
        acc = self._accounts.get(key)
        if acc is None:
            acc = _Account(ref=ref, since_ms=self._clock())
            self._accounts[key] = acc
            return acc, True
        if acc.ref != ref:  # the instance's platform kind changed
            acc.ref = ref
        return acc, False

    def _set(
        self,
        acc: _Account,
        state: str,
        reason: str | None = None,
        detail: str | None = None,
        *,
        new: bool = False,
    ) -> None:
        if not new and acc.state == state and acc.reason == reason:
            return
        acc.state, acc.reason, acc.detail = state, reason, detail
        acc.since_ms = self._clock()
        self._emit(acc.status())

    # --- inputs ---------------------------------------------------------

    def connected(self, ref: P.AccountRef) -> None:
        acc, new = self._account(ref)
        acc.last_seen_ms = self._clock()
        acc.last_heartbeat_ms = acc.last_seen_ms
        if new or acc.state == "offline":
            self._set(acc, "connecting", new=new)

    def heartbeat(
        self,
        ref: P.AccountRef,
        *,
        online: bool | None,
        good: bool | None,
        interval_ms: int | None,
    ) -> None:
        acc, new = self._account(ref)
        now = self._clock()
        acc.last_seen_ms = now
        acc.last_heartbeat_ms = now
        if interval_ms and interval_ms > 0:
            acc.heartbeat_ms = interval_ms
        if online is False or good is False:
            detail = f"online={online}, good={good}"
            self._set(acc, "offline", "unhealthy", detail, new=new)
        elif acc.reason == "kicked" and online is None:
            pass  # a bare heartbeat does not prove the login is back
        else:
            self._set(acc, "online", new=new)

    def activity(self, ref: P.AccountRef, nickname: str | None = None) -> None:
        """A message or notice arrived from the account: it works."""
        acc, new = self._account(ref)
        acc.last_seen_ms = self._clock()
        if nickname:
            acc.nickname = nickname
        self._set(acc, "online", new=new)

    def kicked(self, ref: P.AccountRef, detail: str | None) -> None:
        acc, new = self._account(ref)
        self._set(acc, "offline", "kicked", detail, new=new)

    def set_nickname(self, ref: P.AccountRef, nickname: str) -> None:
        acc, _ = self._account(ref)
        acc.nickname = nickname or acc.nickname

    def mark_instance(
        self, instance: str, state: str, reason: str, detail: str | None = None
    ) -> None:
        for (inst, _), acc in list(self._accounts.items()):
            if inst == instance:
                self._set(acc, state, reason, detail)

    def instance_recovered(self, instance: str) -> None:
        """The AstrBot instance runs again: its accounts must prove themselves."""
        for (inst, _), acc in list(self._accounts.items()):
            if inst == instance and acc.reason in ("platform_error", "stopped"):
                self._set(acc, "connecting")

    def forget_instance(self, instance: str) -> None:
        self.mark_instance(instance, "offline", "stopped")

    # --- watchdog -------------------------------------------------------

    def check(
        self,
        connected: Callable[[P.AccountRef], bool | None],
    ) -> None:
        """Run the deadlines. ``connected(ref)`` says whether the account's
        connection is up (``None``: the adapter cannot tell)."""
        now = self._clock()
        for acc in list(self._accounts.values()):
            if acc.state == "offline" and acc.reason in (
                "kicked",
                "stopped",
                "platform_error",
            ):
                continue
            is_up = connected(acc.ref)
            if is_up is False:
                self._set(acc, "offline", "disconnected")
                continue
            if acc.state == "offline":
                continue
            if acc.heartbeat_ms and acc.last_heartbeat_ms is not None:
                deadline = acc.last_heartbeat_ms + int(acc.heartbeat_ms * self._grace)
                if now > deadline:
                    self._set(
                        acc,
                        "offline",
                        "heartbeat_timeout",
                        f"no heartbeat for {(now - acc.last_heartbeat_ms) // 1000}s",
                    )
