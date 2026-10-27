from __future__ import annotations

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_message_chain_from_payload,
)


class OpenApiServiceError(Exception):
    pass


class OpenApiService:
    """IM endpoints of the Open API (LoAgent channel gateway build)."""

    def __init__(
        self,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.platform_manager = core_lifecycle.platform_manager

    async def build_message_chain_from_payload(self, message_payload: str | list):
        return await build_message_chain_from_payload(
            message_payload,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=True,
        )

    async def send_message(self, post_data: object) -> None:
        payload = post_data if isinstance(post_data, dict) else {}
        message_payload = payload.get("message", {})
        umo = payload.get("umo")

        if message_payload is None:
            raise OpenApiServiceError("Missing key: message")
        if not umo:
            raise OpenApiServiceError("Missing key: umo")

        try:
            session = MessageSesion.from_str(str(umo))
        except Exception as exc:
            raise OpenApiServiceError(f"Invalid umo: {exc}") from exc

        platform_id = session.platform_name
        platform_inst = next(
            (
                inst
                for inst in self.platform_manager.platform_insts
                if inst.meta().id == platform_id
            ),
            None,
        )
        if not platform_inst:
            raise OpenApiServiceError(
                f"Bot not found or not running for platform: {platform_id}"
            )

        try:
            message_chain = await self.build_message_chain_from_payload(message_payload)
            await platform_inst.send_by_session(session, message_chain)
        except OpenApiServiceError:
            raise
        except ValueError as exc:
            raise OpenApiServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error(f"Open API send_message failed: {exc}", exc_info=True)
            raise OpenApiServiceError(f"Failed to send message: {exc}") from exc

    def get_bots(self) -> dict:
        bot_ids = []
        for platform in self.core_lifecycle.astrbot_config.get("platform", []):
            platform_id = platform.get("id") if isinstance(platform, dict) else None
            if (
                isinstance(platform_id, str)
                and platform_id
                and platform_id not in bot_ids
            ):
                bot_ids.append(platform_id)
        return {"bot_ids": bot_ids}
