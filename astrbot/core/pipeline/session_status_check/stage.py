from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ..context import PipelineContext
from ..stage import Stage, register_stage


@register_stage
class SessionStatusCheckStage(Stage):
    """检查会话是否整体启用"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        # 检查会话是否整体启用
        if not await SessionServiceManager.is_session_enabled(event.unified_msg_origin):
            logger.debug(
                f"Session {event.unified_msg_origin} is disabled; event propagation "
                "was stopped."
            )
            event.stop_event()
