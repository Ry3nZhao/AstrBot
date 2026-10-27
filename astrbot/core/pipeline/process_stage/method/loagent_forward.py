"""Forward woken messages to LoAgent and turn its reply into a message chain.

This sub stage replaces AstrBot's built-in agent request in the LoAgent channel
gateway build. AstrBot keeps channels, routing and wake rules; LoAgent owns the
persona, memory and the decision whether to reply.

Request: ``POST <endpoint>/api/channel/message`` with
``Authorization: Bearer <token>`` and a JSON body built by
``build_loagent_request``. Reply: ``{"silent": true}`` or
``{"text": ..., "at": ..., "replyTo": ..., "images": ...}``, converted by
``build_reply_chain``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import aiohttp

from astrbot.core import logger
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    Image,
    Plain,
    Reply,
)
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ...context import PipelineContext
from ...stage import Stage

CHANNEL_MESSAGE_PATH = "/api/channel/message"
DEFAULT_ENDPOINT = "http://loagent:3080"
DEFAULT_TIMEOUT = 120.0

_MESSAGE_TYPES = {
    MessageType.GROUP_MESSAGE: "group",
    MessageType.FRIEND_MESSAGE: "private",
    MessageType.OTHER_MESSAGE: "other",
}


def _chain_text(chain: list[BaseMessageComponent] | None) -> str:
    """Concatenate the plain text segments of a message chain."""
    return "".join(c.text for c in chain or [] if isinstance(c, Plain)).strip()


async def build_loagent_request(event: AstrMessageEvent, project: str) -> dict:
    """Build the JSON body sent to LoAgent for one message event.

    Args:
        event: The woken message event.
        project: LoAgent project bound to the event's configuration.

    Returns:
        The request body. See ``LOAGENT.md`` for the field reference.
    """
    self_id = str(event.get_self_id())
    mentions: dict[str, Any] = {"bot": False, "all": False, "users": []}
    reply_to = None
    images: list[str] = []
    for comp in event.get_messages():
        if isinstance(comp, AtAll) or (isinstance(comp, At) and str(comp.qq) == "all"):
            mentions["all"] = True
        elif isinstance(comp, At):
            if str(comp.qq) == self_id:
                mentions["bot"] = True
            else:
                mentions["users"].append({"id": str(comp.qq), "name": comp.name or ""})
        elif isinstance(comp, Reply) and reply_to is None:
            reply_to = {
                "id": str(comp.id),
                "text": comp.message_str or _chain_text(comp.chain),
                "sender": {
                    "id": str(comp.sender_id or ""),
                    "name": comp.sender_nickname or "",
                },
                "isBot": bool(comp.sender_id) and str(comp.sender_id) == self_id,
            }
        elif isinstance(comp, Image):
            # LoAgent runs in another container, so local paths are inlined.
            url = comp.url or comp.file or ""
            if url.startswith(("http://", "https://")):
                images.append(url)
            else:
                try:
                    images.append(
                        "data:image/jpeg;base64," + await comp.convert_to_base64()
                    )
                except Exception as exc:
                    logger.warning("LoAgent forward: skip unreadable image: %s", exc)

    timestamp = getattr(event.message_obj, "timestamp", None) or 0
    return {
        "project": project,
        "umo": event.unified_msg_origin,
        "platform": {"id": event.get_platform_id(), "type": event.get_platform_name()},
        "messageType": _MESSAGE_TYPES.get(event.get_message_type(), "other"),
        "messageId": str(getattr(event.message_obj, "message_id", "") or ""),
        "groupId": str(event.get_group_id() or ""),
        "selfId": self_id,
        "sender": {
            "id": str(event.get_sender_id()),
            "name": event.get_sender_name() or "",
        },
        "text": event.message_str,
        "images": images,
        "mentions": mentions,
        "replyTo": reply_to,
        "at": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
    }


def build_reply_chain(reply: Any) -> list[BaseMessageComponent] | None:
    """Convert a LoAgent reply into an AstrBot message chain.

    Args:
        reply: Parsed JSON reply. ``{"silent": true}`` or an object with
            ``text``, optional ``at`` (id, object or a list of them),
            ``replyTo`` (message id or ``{"id": ...}``) and ``images`` (URLs).

    Returns:
        The message chain, or None when nothing should be sent.
    """
    if not isinstance(reply, dict) or reply.get("silent"):
        return None
    text = reply.get("text") or ""
    images = [i for i in reply.get("images") or [] if isinstance(i, str) and i]
    if not isinstance(text, str) or not (text.strip() or images):
        return None

    chain: list[BaseMessageComponent] = []
    reply_to = reply.get("replyTo")
    if isinstance(reply_to, dict):
        reply_to = reply_to.get("id")
    if reply_to not in (None, ""):
        chain.append(Reply(id=str(reply_to)))

    targets = reply.get("at") or []
    if not isinstance(targets, list):
        targets = [targets]
    for target in targets:
        if isinstance(target, dict):
            target_id, name = target.get("id"), target.get("name") or ""
        else:
            target_id, name = target, ""
        if target_id in (None, ""):
            continue
        chain.append(
            AtAll() if str(target_id) == "all" else At(qq=str(target_id), name=name)
        )
        chain.append(Plain(" "))

    if text.strip():
        chain.append(Plain(text))
    for image in images:
        if image.startswith(("http://", "https://")):
            chain.append(Image.fromURL(image))
        elif image.startswith("data:") and "base64," in image:
            chain.append(Image.fromBase64(image.split("base64,", 1)[1]))
        elif image.startswith("base64://"):
            chain.append(Image(file=image))
    return chain


class LoAgentForwardSubStage(Stage):
    """Send woken messages to LoAgent and reply with what it returns."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        # The entry point is global: read it from the default configuration.
        default_conf = ctx.plugin_manager.context.get_config()
        loagent_conf = default_conf.get("loagent") or {}
        self.endpoint = (
            os.environ.get("LOAGENT_ENDPOINT")
            or loagent_conf.get("endpoint")
            or DEFAULT_ENDPOINT
        ).rstrip("/")
        self.token = os.environ.get("LOAGENT_TOKEN") or loagent_conf.get("token") or ""
        self.timeout = float(loagent_conf.get("timeout") or DEFAULT_TIMEOUT)
        self.project = str(self.config.get("loagent_project") or "").strip()

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        if not self.project:
            logger.debug(
                "Configuration %s has no loagent_project; message not forwarded.",
                self.ctx.astrbot_config_id,
            )
            return
        if not await SessionServiceManager.should_process_llm_request(event):
            logger.debug(
                "Session %s has forwarding disabled, skipping.",
                event.unified_msg_origin,
            )
            return

        url = self.endpoint + CHANNEL_MESSAGE_PATH
        body = await build_loagent_request(event, self.project)
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        event.trace.record(
            "agent_start", kind="agent", status="running", runner_type="loagent"
        )
        reply: Any = None
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                async with session.post(url, json=body, headers=headers) as resp:
                    if resp.status in (401, 403):
                        logger.error(
                            "LoAgent rejected the gateway token (HTTP %s) for %s; "
                            "no reply sent. Check loagent.token / LOAGENT_TOKEN.",
                            resp.status,
                            event.unified_msg_origin,
                        )
                    elif resp.status >= 400:
                        logger.error(
                            "LoAgent returned HTTP %s for %s: %s",
                            resp.status,
                            event.unified_msg_origin,
                            (await resp.text())[:500],
                        )
                    else:
                        reply = await resp.json(content_type=None)
        except asyncio.TimeoutError:
            logger.warning(
                "LoAgent did not reply within %.0fs for %s; no reply sent.",
                self.timeout,
                event.unified_msg_origin,
            )
        except Exception as exc:
            logger.error(
                "Forwarding to LoAgent at %s failed for %s: %s",
                url,
                event.unified_msg_origin,
                exc,
            )

        chain = build_reply_chain(reply)
        event.trace.record(
            "agent_end",
            kind="agent",
            status="success" if reply is not None else "error",
            runner_type="loagent",
            silent=chain is None,
        )
        if chain is None:
            return
        event.set_result(
            MessageEventResult(chain=chain).set_result_content_type(
                ResultContentType.LLM_RESULT
            )
        )
        yield
