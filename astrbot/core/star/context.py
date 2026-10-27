from __future__ import annotations

import logging
from asyncio import Queue
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

from deprecated import deprecated

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Platform
from astrbot.core.platform.astr_message_event import (
    MessageSesion,
    current_message_event,
    streaming_response_event,
)
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.star.filter.platform_adapter_type import (
    ADAPTER_NAME_2_TYPE,
    PlatformAdapterType,
)

from .filter.command import CommandFilter
from .filter.regex import RegexFilter
from .star import StarMetadata, star_registry
from .star_handler import EventType, StarHandlerMetadata, star_handlers_registry

logger = logging.getLogger("astrbot")

if TYPE_CHECKING:
    from astrbot.core.utils.t2i.renderer import HtmlRenderer

WebApiHandler = Callable[..., Awaitable[Any]]
RegisteredWebApi = tuple[str, WebApiHandler, list[str], str]


class PlatformManagerProtocol(Protocol):
    platform_insts: list[Platform]
    get_insts: Callable[[], list[Platform]]


class Context:
    """Plugin-facing context of the LoAgent channel gateway.

    The gateway build of AstrBot has no LLM providers, conversations, personas,
    knowledge bases or cron jobs; those live in LoAgent. This context keeps the
    platform, configuration, database and plugin registration surface only.
    """

    registered_web_apis: list[RegisteredWebApi] = []
    html_renderer: HtmlRenderer
    """Text-to-image renderer, injected by the core lifecycle after creation."""

    # 向后兼容的变量
    _register_tasks: list[Awaitable] = []
    _star_manager = None

    def __init__(
        self,
        event_queue: Queue,
        config: AstrBotConfig,
        db: BaseDatabase,
        platform_manager: PlatformManagerProtocol,
        message_history_manager: PlatformMessageHistoryManager,
        astrbot_config_mgr: AstrBotConfigManager,
    ) -> None:
        self._event_queue = event_queue
        """事件队列。消息平台通过事件队列传递消息事件。"""
        self._config = config
        """AstrBot 默认配置"""
        self._db = db
        """AstrBot 数据库"""
        self.platform_manager = platform_manager
        """平台适配器管理器"""
        self.message_history_manager = message_history_manager
        """平台消息历史管理器"""
        self.astrbot_config_mgr = astrbot_config_mgr
        """配置文件管理器(非webui)"""

    def get_registered_star(self, star_name: str) -> StarMetadata | None:
        """根据插件名获取插件的 Metadata"""
        for star in star_registry:
            if star.name == star_name:
                return star

    def get_all_stars(self) -> list[StarMetadata]:
        """获取当前载入的所有插件 Metadata 的列表"""
        return star_registry

    async def get_using_stt_provider_async(self, umo: str | None = None) -> None:
        """Speech-to-text is not available in the gateway build.

        Args:
            umo: Unified message origin, ignored.

        Returns:
            Always None, so the STT branch of the preprocess stage is a no-op.
        """
        return None

    async def get_using_tts_provider_async(self, umo: str | None = None) -> None:
        """Text-to-speech is not available in the gateway build.

        Args:
            umo: Unified message origin, ignored.

        Returns:
            Always None, so the TTS branch of the result decorate stage is a no-op.
        """
        return None

    def get_config(self, umo: str | None = None) -> AstrBotConfig:
        """获取 AstrBot 的配置。

        Args:
            umo: unified_message_origin 值，用于获取特定会话的配置。

        Returns:
            AstrBot 配置对象。

        Note:
            如果不提供 umo 参数，将返回默认配置。
        """
        if not umo:
            # 使用默认配置
            return self._config
        return self.astrbot_config_mgr.get_conf(umo)

    async def send_message(
        self,
        session: str | MessageSesion,
        message_chain: MessageChain,
    ) -> bool:
        """根据 session(unified_msg_origin) 主动发送消息。

        Args:
            session: 消息会话。通过 event.session 或者 event.unified_msg_origin 获取。
            message_chain: 消息链。

        Returns:
            是否找到匹配的平台。

        Raises:
            ValueError: session 字符串不合法时抛出。

        Note:
            当 session 为字符串时，会尝试解析为 MessageSession 对象。(类名为MessageSesion是因为历史遗留拼写错误)
            qq_official(QQ 官方 API 平台) 不支持此方法。
        """
        if isinstance(session, str):
            try:
                session = MessageSesion.from_str(session)
            except BaseException as e:
                raise ValueError("不合法的 session 字符串: " + str(e))

        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == session.platform_name:
                await platform.send_by_session(session, message_chain)
                event = current_message_event.get()
                if (
                    event is not None
                    and event._execution_active
                    and message_chain.chain
                    and streaming_response_event.get() is not event
                ):
                    event.trace.record(
                        "response_sent",
                        kind="response",
                        message=event._outline_chain(message_chain.chain),
                        component_types=[
                            str(component.type) for component in message_chain.chain
                        ],
                        component_count=len(message_chain.chain),
                        message_type=message_chain.type,
                        target_umo=str(session),
                    )
                return True
        logger.warning(
            f"cannot find platform for session {str(session)}, message not sent"
        )
        return False

    def register_web_api(
        self,
        route: str,
        view_handler: WebApiHandler,
        methods: list[str],
        desc: str,
    ) -> None:
        """注册 Web API。

        Args:
            route: API 路由路径。
            view_handler: 异步视图处理函数。
            methods: HTTP 方法列表。
            desc: API 描述。

        Note:
            如果相同路由和方法已注册，会替换现有的 API。
        """
        for idx, api in enumerate(self.registered_web_apis):
            if api[0] == route and methods == api[2]:
                self.registered_web_apis[idx] = (route, view_handler, methods, desc)
                return
        self.registered_web_apis.append((route, view_handler, methods, desc))

    """
    以下的方法已经不推荐使用。请从 AstrBot 文档查看更好的注册方式。
    """

    def get_event_queue(self) -> Queue:
        """获取事件队列。"""
        return self._event_queue

    @deprecated(version="4.0.0", reason="Use get_platform_inst instead")
    def get_platform(self, platform_type: PlatformAdapterType | str) -> Platform | None:
        """获取指定类型的平台适配器。

        Args:
            platform_type: 平台类型或平台名称。

        Returns:
            平台适配器实例，如果未找到则返回 None。

        Note:
            该方法已经过时，请使用 get_platform_inst 方法。(>= AstrBot v4.0.0)
        """
        for platform in self.platform_manager.platform_insts:
            name = platform.meta().name
            if isinstance(platform_type, str):
                if name == platform_type:
                    return platform
            elif (
                name in ADAPTER_NAME_2_TYPE
                and ADAPTER_NAME_2_TYPE[name] & platform_type
            ):
                return platform

    def get_platform_inst(self, platform_id: str) -> Platform | None:
        """获取指定 ID 的平台适配器实例。

        Args:
            platform_id: 平台适配器的唯一标识符。

        Returns:
            平台适配器实例，如果未找到则返回 None。

        Note:
            可以通过 event.get_platform_id() 获取平台 ID。
        """
        for platform in self.platform_manager.platform_insts:
            if platform.meta().id == platform_id:
                return platform

    def get_db(self) -> BaseDatabase:
        """获取 AstrBot 数据库。

        Returns:
            数据库实例。
        """
        return self._db

    @deprecated(reason="Use the command decorator (@filter.command) instead.")
    def register_commands(
        self,
        star_name: str,
        command_name: str,
        desc: str,
        priority: int,
        awaitable: Callable[..., Awaitable[Any]],
        use_regex=False,
        ignore_prefix=False,
    ) -> None:
        """[DEPRECATED]注册一个命令。

        Args:
            star_name: 插件（Star）名称。
            command_name: 命令名称。
            desc: 命令描述。
            priority: 优先级。1-10。
            awaitable: 异步处理函数。
            use_regex: 是否使用正则表达式匹配命令。
            ignore_prefix: 是否忽略命令前缀。

        Note:
            推荐使用装饰器注册指令。该方法将在未来的版本中被移除。
        """
        md = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=awaitable.__module__ + "_" + awaitable.__name__,
            handler_name=awaitable.__name__,
            handler_module_path=awaitable.__module__,
            handler=awaitable,
            event_filters=[],
            desc=desc,
        )
        if use_regex:
            md.event_filters.append(RegexFilter(regex=command_name))
        else:
            md.event_filters.append(
                CommandFilter(command_name=command_name, handler_md=md),
            )
        star_handlers_registry.append(md)

    @deprecated(
        reason="Start background tasks in the plugin's initialize() method instead."
    )
    def register_task(self, task: Awaitable, desc: str) -> None:
        """[DEPRECATED]注册一个异步任务。

        Args:
            task: 异步任务。
            desc: 任务描述。

        Note:
            该方法已弃用。
        """
        self._register_tasks.append(task)
