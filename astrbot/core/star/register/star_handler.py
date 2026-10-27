from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageEventResult

from ..filter.command import CommandFilter
from ..filter.command_group import CommandGroupFilter
from ..filter.custom_filter import CustomFilterAnd, CustomFilterOr
from ..filter.event_message_type import EventMessageType, EventMessageTypeFilter
from ..filter.permission import PermissionType, PermissionTypeFilter
from ..filter.platform_adapter_type import (
    PlatformAdapterType,
    PlatformAdapterTypeFilter,
)
from ..filter.regex import RegexFilter
from ..star_handler import EventType, StarHandlerMetadata, star_handlers_registry


def get_handler_full_name(
    awaitable: Callable[..., Awaitable[Any] | AsyncGenerator[Any]],
) -> str:
    """获取 Handler 的全名"""
    return f"{awaitable.__module__}_{awaitable.__name__}"


def get_handler_or_create(
    handler: Callable[
        ...,
        Awaitable[MessageEventResult | str | None]
        | AsyncGenerator[MessageEventResult | str | None],
    ],
    event_type: EventType,
    dont_add=False,
    **kwargs,
) -> StarHandlerMetadata:
    """获取 Handler 或者创建一个新的 Handler"""
    handler_full_name = get_handler_full_name(handler)
    md = star_handlers_registry.get_handler_by_full_name(handler_full_name)
    if md:
        return md
    md = StarHandlerMetadata(
        event_type=event_type,
        handler_full_name=handler_full_name,
        handler_name=handler.__name__,
        handler_module_path=handler.__module__,
        handler=handler,
        event_filters=[],
    )

    # 插件handler的附加额外信息
    if handler.__doc__:
        md.desc = handler.__doc__.strip()
    if "desc" in kwargs:
        md.desc = kwargs["desc"]
        del kwargs["desc"]
    md.extras_configs = kwargs

    if not dont_add:
        star_handlers_registry.append(md)
    return md


def register_command(
    command_name: str | None = None,
    sub_command: str | None = None,
    alias: set | None = None,
    **kwargs,
):
    """注册一个 Command."""
    new_command = None
    add_to_event_filters = False
    if isinstance(command_name, RegisteringCommandable):
        # 子指令
        if sub_command is not None:
            parent_command_names = (
                command_name.parent_group.get_complete_command_names()
            )
            new_command = CommandFilter(
                sub_command,
                alias,
                None,
                parent_command_names=parent_command_names,
            )
            command_name.parent_group.add_sub_command_filter(new_command)
        else:
            logger.warning(
                f"No sub_command argument was provided while registering a "
                f"subcommand for {command_name}.",
            )
    # 裸指令
    elif command_name is None:
        logger.warning(
            "No command_name argument was provided while registering a bare command."
        )
    else:
        new_command = CommandFilter(command_name, alias, None)
        add_to_event_filters = True

    def decorator(awaitable):
        if not add_to_event_filters:
            kwargs["sub_command"] = (
                True  # 打一个标记，表示这是一个子指令，再 wakingstage 阶段这个 handler 将会直接被跳过（其父指令会接管）
            )
        handler_md = get_handler_or_create(
            awaitable,
            EventType.AdapterMessageEvent,
            **kwargs,
        )
        if new_command:
            new_command.init_handler_md(handler_md)
            handler_md.event_filters.append(new_command)
        return awaitable

    return decorator


def register_custom_filter(custom_type_filter, *args, **kwargs):
    """注册一个自定义的 CustomFilter

    Args:
        custom_type_filter: 在裸指令时为CustomFilter对象
                                        在指令组时为父指令的RegisteringCommandable对象，即self或者command_group的返回
        raise_error: 如果没有权限，是否抛出错误到消息平台，并且停止事件传播。默认为 True

    """
    add_to_event_filters = False
    raise_error = True

    # 判断是否是指令组，指令组则添加到指令组的CommandGroupFilter对象中在waking_check的时候一起判断
    if isinstance(custom_type_filter, RegisteringCommandable):
        # 子指令, 此时函数为RegisteringCommandable对象的方法，首位参数为RegisteringCommandable对象的self。
        parent_register_commandable = custom_type_filter
        custom_filter = args[0]
        if len(args) > 1:
            raise_error = args[1]
    else:
        # 裸指令
        add_to_event_filters = True
        custom_filter = custom_type_filter
        if args:
            raise_error = args[0]

    if not isinstance(custom_filter, (CustomFilterAnd, CustomFilterOr)):
        custom_filter = custom_filter(raise_error)

    def decorator(awaitable):
        # 裸指令，子指令与指令组的区分，指令组会因为标记跳过wake。
        if (
            not add_to_event_filters and isinstance(awaitable, RegisteringCommandable)
        ) or (add_to_event_filters and isinstance(awaitable, RegisteringCommandable)):
            # 指令组 与 根指令组，添加到本层的grouphandle中一起判断
            awaitable.parent_group.add_custom_filter(custom_filter)
        else:
            handler_md = get_handler_or_create(
                awaitable,
                EventType.AdapterMessageEvent,
                **kwargs,
            )

            if not add_to_event_filters and not isinstance(
                awaitable,
                RegisteringCommandable,
            ):
                # 底层子指令
                handle_full_name = get_handler_full_name(awaitable)
                for (
                    sub_handle
                ) in parent_register_commandable.parent_group.sub_command_filters:
                    if isinstance(sub_handle, CommandGroupFilter):
                        continue
                    # 所有符合fullname一致的子指令handle添加自定义过滤器。
                    # 不确定是否会有多个子指令有一样的fullname，比如一个方法添加多个command装饰器？
                    sub_handle_md = sub_handle.get_handler_md()
                    if (
                        sub_handle_md
                        and sub_handle_md.handler_full_name == handle_full_name
                    ):
                        sub_handle.add_custom_filter(custom_filter)

            else:
                # 裸指令
                # 确保运行时是可调用的 handler，针对类型检查器添加忽略
                assert isinstance(awaitable, Callable)
                handler_md = get_handler_or_create(
                    awaitable,
                    EventType.AdapterMessageEvent,
                    **kwargs,
                )
                handler_md.event_filters.append(custom_filter)

        return awaitable

    return decorator


def register_command_group(
    command_group_name: str | None = None,
    sub_command: str | None = None,
    alias: set | None = None,
    **kwargs,
):
    """注册一个 CommandGroup"""
    new_group = None
    if isinstance(command_group_name, RegisteringCommandable):
        # 子指令组
        if sub_command is None:
            logger.warning(
                f"No sub_command was specified for a subgroup of command group "
                f"{command_group_name}."
            )
        else:
            new_group = CommandGroupFilter(
                sub_command,
                alias,
                parent_group=command_group_name.parent_group,
            )
            command_group_name.parent_group.add_sub_command_filter(new_group)
    # 根指令组
    elif command_group_name is None:
        logger.warning("No name was specified for the root command group.")
    else:
        new_group = CommandGroupFilter(command_group_name, alias)

    def decorator(obj):
        if new_group:
            handler_md = get_handler_or_create(
                obj,
                EventType.AdapterMessageEvent,
                **kwargs,
            )
            handler_md.event_filters.append(new_group)

            return RegisteringCommandable(new_group)
        raise ValueError("注册指令组失败。")

    return decorator


class RegisteringCommandable:
    """用于指令组级联注册"""

    group: Callable[..., Callable[..., RegisteringCommandable]] = register_command_group
    command: Callable[..., Callable[..., None]] = register_command
    custom_filter: Callable[..., Callable[..., Any]] = register_custom_filter

    def __init__(self, parent_group: CommandGroupFilter) -> None:
        self.parent_group = parent_group


def register_event_message_type(event_message_type: EventMessageType, **kwargs):
    """注册一个 EventMessageType"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable,
            EventType.AdapterMessageEvent,
            **kwargs,
        )
        handler_md.event_filters.append(EventMessageTypeFilter(event_message_type))
        return awaitable

    return decorator


def register_platform_adapter_type(
    platform_adapter_type: PlatformAdapterType,
    **kwargs,
):
    """注册一个 PlatformAdapterType"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable,
            EventType.AdapterMessageEvent,
            **kwargs,
        )
        handler_md.event_filters.append(
            PlatformAdapterTypeFilter(platform_adapter_type),
        )
        return awaitable

    return decorator


def register_regex(regex: str | re.Pattern, **kwargs):
    """注册一个 Regex"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable,
            EventType.AdapterMessageEvent,
            **kwargs,
        )
        handler_md.event_filters.append(RegexFilter(regex))
        return awaitable

    return decorator


def register_permission_type(
    permission_type: PermissionType, raise_error: bool = True, **kwargs
):
    """注册一个 PermissionType

    Args:
        permission_type: PermissionType
        raise_error: 如果没有权限，是否抛出错误到消息平台，并且停止事件传播。默认为 True

    """

    def decorator(awaitable):
        handler_md = get_handler_or_create(
            awaitable,
            EventType.AdapterMessageEvent,
            **kwargs,
        )
        handler_md.event_filters.append(
            PermissionTypeFilter(permission_type, raise_error),
        )
        return awaitable

    return decorator


def register_on_astrbot_loaded(**kwargs):
    """当 AstrBot 加载完成时"""

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnAstrBotLoadedEvent, **kwargs)
        return awaitable

    return decorator


def register_on_platform_loaded(**kwargs):
    """当平台加载完成时"""

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnPlatformLoadedEvent, **kwargs)
        return awaitable

    return decorator


def register_on_plugin_error(**kwargs):
    """当插件处理消息异常时触发。

    Hook 参数:
        event, plugin_name, handler_name, error, traceback_text

    说明:
        在 hook 中调用 `event.stop_event()` 可屏蔽默认报错回显，
        并由插件自行决定是否转发到其他会话。
    """

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnPluginErrorEvent, **kwargs)
        return awaitable

    return decorator


def register_on_plugin_loaded(**kwargs):
    """当有插件加载完成时

    Hook 参数:
        metadata

    说明:
        当有插件加载完成时，触发该事件并获取到该插件的元数据
    """

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnPluginLoadedEvent, **kwargs)
        return awaitable

    return decorator


def register_on_plugin_unloaded(**kwargs):
    """当有插件卸载完成时

    Hook 参数:
        metadata

    说明:
        当有插件卸载完成时，触发该事件并获取到该插件的元数据
    """

    def decorator(awaitable):
        _ = get_handler_or_create(awaitable, EventType.OnPluginUnloadedEvent, **kwargs)
        return awaitable

    return decorator


def register_on_decorating_result(**kwargs):
    """在发送消息前的事件"""

    def decorator(awaitable):
        _ = get_handler_or_create(
            awaitable,
            EventType.OnDecoratingResultEvent,
            **kwargs,
        )
        return awaitable

    return decorator


def register_after_message_sent(**kwargs):
    """在消息发送后的事件"""

    def decorator(awaitable):
        _ = get_handler_or_create(
            awaitable,
            EventType.OnAfterMessageSentEvent,
            **kwargs,
        )
        return awaitable

    return decorator
