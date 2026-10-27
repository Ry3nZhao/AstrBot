"""Send group messages that did not wake the bot to LoAgent's observe entry.

LoAgent records every group message in the event's memory, not only the ones
it answers. Messages that pass the wake check go through ``loagent_forward``;
the rest are stopped by ``WakingCheckStage``, which hands them to
``LoAgentObserver.schedule`` first.

Request: ``POST <endpoint>/api/channel/observe`` with the same body and token
as ``loagent_forward`` (see ``build_loagent_request``). LoAgent only stores the
message and answers ``204``. The request runs in the background, so the
pipeline never waits for it, and failures are only logged.
"""

from __future__ import annotations

import asyncio

import aiohttp

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ...context import PipelineContext
from .loagent_forward import build_loagent_request, resolve_loagent_settings

CHANNEL_OBSERVE_PATH = "/api/channel/observe"
OBSERVE_TIMEOUT = 10.0

_pending: set[asyncio.Task] = set()


def pending_tasks() -> set[asyncio.Task]:
    """Return the observe requests still in flight (used by tests)."""
    return set(_pending)


class LoAgentObserver:
    """Decide whether an unwoken message is observed and send it."""

    def __init__(self, ctx: PipelineContext) -> None:
        config = ctx.astrbot_config
        self.config_id = ctx.astrbot_config_id
        self.enabled = bool(config.get("loagent_observe", False))
        self.project = str(config.get("loagent_project") or "").strip()
        self.endpoint, self.token = "", ""
        if self.enabled and self.project:
            self.endpoint, self.token, _ = resolve_loagent_settings(
                ctx.plugin_manager.context.get_config()
            )
        # The whitelist stage runs after the wake check, so apply it here too:
        # a group that may not talk to the bot is not recorded either.
        settings = config.get("platform_settings") or {}
        self.whitelist_enabled = bool(settings.get("enable_id_white_list", False))
        self.whitelist = [
            str(i).strip()
            for i in settings.get("id_whitelist") or []
            if str(i).strip() != ""
        ]
        self.whitelist_ignores_admin = bool(
            settings.get("wl_ignore_admin_on_group", False)
        )

    def _allowed_by_whitelist(self, event: AstrMessageEvent) -> bool:
        if not self.whitelist_enabled or not self.whitelist:
            return True
        if self.whitelist_ignores_admin and event.role == "admin":
            return True
        return (
            event.unified_msg_origin in self.whitelist
            or str(event.get_group_id()).strip() in self.whitelist
        )

    def should_observe(self, event: AstrMessageEvent) -> bool:
        """Whether an unwoken message should be sent to the observe entry.

        Args:
            event: A message event that did not wake the bot.

        Returns:
            True for group messages from other people, when this configuration
            has ``loagent_observe`` on, a ``loagent_project`` and the group
            passes the whitelist.
        """
        return (
            self.enabled
            and bool(self.project)
            and event.get_message_type() == MessageType.GROUP_MESSAGE
            and str(event.get_sender_id()) != str(event.get_self_id())
            and self._allowed_by_whitelist(event)
        )

    def schedule(self, event: AstrMessageEvent) -> None:
        """Send the message to LoAgent in the background if it qualifies."""
        if not self.should_observe(event):
            return
        task = asyncio.create_task(self._send(event))
        _pending.add(task)
        task.add_done_callback(_pending.discard)

    async def _send(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        url = self.endpoint + CHANNEL_OBSERVE_PATH
        try:
            # Same switches as forwarding: a disabled session, or one with
            # forwarding turned off in session management, is not recorded.
            if not await SessionServiceManager.is_session_enabled(umo):
                return
            if not await SessionServiceManager.should_process_llm_request(event):
                return
            body = await build_loagent_request(event, self.project)
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=OBSERVE_TIMEOUT)
            ) as session:
                async with session.post(url, json=body, headers=headers) as resp:
                    if resp.status in (401, 403):
                        logger.error(
                            "LoAgent rejected the gateway token (HTTP %s) when "
                            "observing %s. Check loagent.token / LOAGENT_TOKEN.",
                            resp.status,
                            umo,
                        )
                    elif resp.status >= 400:
                        logger.warning(
                            "LoAgent observe returned HTTP %s for %s: %s",
                            resp.status,
                            umo,
                            (await resp.text())[:500],
                        )
        except asyncio.TimeoutError:
            logger.warning(
                "LoAgent observe timed out after %.0fs for %s.", OBSERVE_TIMEOUT, umo
            )
        except Exception as exc:
            logger.warning("LoAgent observe at %s failed for %s: %s", url, umo, exc)
