from __future__ import annotations

import asyncio
import copy
import inspect
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astrbot.core import file_token_service, logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
    DEFAULT_CONFIG,
    DEFAULT_VALUE_MAP,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.register import platform_cls_map, platform_registry
from astrbot.core.star.star import star_registry
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
from astrbot.core.utils.totp import (
    is_totp_enabled,
    revoke_user_trusted_devices,
    set_pending_totp_secret,
    verify_configured_2fa_code,
)
from astrbot.core.utils.upload import UploadTooLargeError
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.schemas import BotCleanupTarget
from astrbot.dashboard.services.bot_cleanup_service import delete_bot_data

PROTECTED_2FA_CONFIG_PATHS = (
    ("dashboard", "totp", "enable"),
    ("dashboard", "totp", "secret"),
    ("dashboard", "totp", "recovery_code_hash"),
)
MAX_FILE_BYTES = 500 * 1024 * 1024


def try_cast(value: Any, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    elif (
        type_ == "float"
        and isinstance(value, str)
        and value.replace(".", "", 1).isdigit()
    ) or (type_ == "float" and isinstance(value, int)):
        return float(value)
    elif type_ == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def _expect_type(value, expected_type, path_key, errors, expected_name=None) -> bool:
    if not isinstance(value, expected_type):
        errors.append(
            f"错误的类型 {path_key}: 期望是 {expected_name or expected_type.__name__}, "
            f"得到了 {type(value).__name__}"
        )
        return False
    return True


def _validate_template_list(value, meta, path_key, errors, validate_fn) -> None:
    if not _expect_type(value, list, path_key, errors, "list"):
        return

    templates = meta.get("templates")
    if not isinstance(templates, dict):
        templates = {}

    for idx, item in enumerate(value):
        item_path = f"{path_key}[{idx}]"
        if not _expect_type(item, dict, item_path, errors, "dict"):
            continue

        template_key = item.get("__template_key") or item.get("template")
        if not template_key:
            errors.append(f"缺少模板选择 {item_path}: 需要 __template_key")
            continue

        template_meta = templates.get(template_key)
        if not template_meta:
            errors.append(f"未知模板 {item_path}: {template_key}")
            continue

        validate_fn(
            item,
            template_meta.get("items", {}),
            path=f"{path_key}.templates.{template_key}.",
        )


def sanitize_path_segment(segment: str) -> str:
    cleaned = []
    for ch in segment:
        if (
            ("a" <= ch <= "z")
            or ("A" <= ch <= "Z")
            or ch.isdigit()
            or ch
            in {
                "-",
                "_",
            }
        ):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    result = "".join(cleaned).strip("_")
    return result or "_"


def _config_key_to_folder(key_path: str) -> str:
    parts = [sanitize_path_segment(part) for part in key_path.split(".") if part]
    return "/".join(parts) if parts else "_"


def config_key_to_folder(key_path: str) -> str:
    return _config_key_to_folder(key_path)


def _normalize_rel_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    rel = path.replace("\\", "/").lstrip("/")
    if not rel:
        return None
    parts = [part for part in rel.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return None
    if rel.startswith("../") or "/../" in rel:
        return None
    return "/".join(parts)


def normalize_rel_path(path: str | None) -> str | None:
    return _normalize_rel_path(path)


def _get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    if not isinstance(schema, dict) or not key_path:
        return None
    if key_path in schema:
        return schema.get(key_path)

    parts = key_path.split(".")
    current = schema
    idx = 0
    while idx < len(parts):
        part = parts[idx]
        if part not in current:
            return None
        meta = current.get(part)
        if idx == len(parts) - 1:
            return meta
        if not isinstance(meta, dict) or meta.get("type") != "object":
            if not isinstance(meta, dict) or meta.get("type") != "template_list":
                return None
            if idx + 2 >= len(parts) or parts[idx + 1] != "templates":
                return None
            template_meta = meta.get("templates", {}).get(parts[idx + 2])
            if not isinstance(template_meta, dict):
                return None
            if idx + 2 == len(parts) - 1:
                return template_meta
            current = template_meta.get("items", {})
            idx += 3
            continue
        current = meta.get("items", {})
        idx += 1
    return None


def get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    return _get_schema_item(schema, key_path)


def _sanitize_filename(name: str) -> str:
    cleaned = os.path.basename(name).strip()
    if not cleaned or cleaned in {".", ".."}:
        return ""
    for sep in (os.sep, os.altsep):
        if sep:
            cleaned = cleaned.replace(sep, "_")
    return cleaned


def sanitize_filename(name: str) -> str:
    return _sanitize_filename(name)


def validate_config(
    data,
    schema: dict,
    is_core: bool,
    *,
    runtime: dict | None = None,
) -> tuple[list[str], dict]:
    """Validate configuration values and normalize linked Local permissions.

    Args:
        data: Submitted configuration, normalized in place.
        schema: Configuration metadata used for validation.
        is_core: Whether this is a core configuration rather than a plugin.
        runtime: Startup runtime snapshot for platform-specific defaults.

    Returns:
        Validation errors and the normalized configuration.
    """
    errors = []

    def validate(data: dict, metadata: dict = schema, path="") -> None:
        for key, value in data.items():
            if key not in metadata:
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            if value is None:
                data[key] = DEFAULT_VALUE_MAP[meta["type"]]
                continue

            if meta["type"] == "template_list":
                _validate_template_list(value, meta, f"{path}{key}", errors, validate)
                continue

            if meta["type"] == "file":
                if not _expect_type(value, list, f"{path}{key}", errors, "list"):
                    continue
                for idx, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(
                            f"Invalid type {path}{key}[{idx}]: expected string, got {type(item).__name__}",
                        )
                        continue
                    normalized = _normalize_rel_path(item)
                    if not normalized or not normalized.startswith("files/"):
                        errors.append(
                            f"Invalid file path {path}{key}[{idx}]: {item}",
                        )
                        continue
                    key_path = f"{path}{key}"
                    expected_folder = _config_key_to_folder(key_path)
                    expected_prefix = f"files/{expected_folder}/"
                    if not normalized.startswith(expected_prefix):
                        errors.append(
                            f"Invalid file path {path}{key}[{idx}]: {item}",
                        )
                        continue
                    value[idx] = normalized
                continue

            if meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif (
                meta["type"] == "list"
                and isinstance(value, list)
                and value
                and "items" in meta
                and isinstance(value[0], dict)
            ):
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                validate(value, meta["items"], path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}",
                )
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )

    if is_core:
        meta_all = {
            **schema["platform_group"]["metadata"],
            **schema["misc_config_group"]["metadata"],
        }
        validate(data, meta_all)

    else:
        validate(data, schema)

    return errors, data


def _get_nested_value(data: dict, path: tuple[str, ...]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested_value(data: dict, path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path[-1]] = value


def _protected_2fa_config_changed(old_config: dict, new_config: dict) -> bool:
    return any(
        _get_nested_value(old_config, path) != _get_nested_value(new_config, path)
        for path in PROTECTED_2FA_CONFIG_PATHS
    )


def save_config(
    post_config: dict,
    config: AstrBotConfig,
    is_core: bool = False,
    *,
    runtime: dict | None = None,
) -> None:
    """Validate and persist a dashboard configuration update.

    Args:
        post_config: Submitted configuration to validate and save.
        config: Existing configuration and persistence target.
        is_core: Whether this is a core configuration rather than a plugin.
        runtime: Startup runtime snapshot supplied by the profile service.

    Raises:
        ValueError: If configuration validation fails.
    """
    try:
        if is_core:
            errors, post_config = validate_config(
                post_config,
                CONFIG_METADATA_2,
                is_core,
                runtime=runtime,
            )
        else:
            errors, post_config = validate_config(
                post_config,
                getattr(config, "schema", {}),
                is_core,
            )
    except BaseException as exc:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {exc}")
        raise ValueError(f"验证配置时出现异常: {exc}")
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")

    config.save_config(post_config)


class ConfigProfileService:
    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase | None = None,
        *,
        runtime: dict,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.acm = core_lifecycle.astrbot_config_mgr
        self.db = db
        self.runtime = runtime

    def get_profile_schema(self) -> dict:
        return {
            "config": DEFAULT_CONFIG,
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3),
        }

    def get_system_schema(self) -> dict:
        return {
            "config": self.acm.confs["default"],
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(
                CONFIG_METADATA_3_SYSTEM
            ),
        }

    def get_system_config(self) -> dict:
        """Return the system configuration with the server's effective time.

        Returns:
            System configuration metadata, an aware UTC timestamp, and the
            effective UTC offset in minutes.
        """
        data = self.get_system_schema()
        server_utc_time = datetime.now(timezone.utc)
        timezone_name = str(data["config"].get("timezone") or "").strip()
        if timezone_name:
            try:
                configured_time = server_utc_time.astimezone(ZoneInfo(timezone_name))
            except (ValueError, ZoneInfoNotFoundError):
                configured_time = server_utc_time.astimezone()
        else:
            configured_time = server_utc_time.astimezone()
        utc_offset = configured_time.utcoffset()
        data["server_utc_time"] = server_utc_time.isoformat()
        data["server_utc_offset_minutes"] = (
            int(utc_offset.total_seconds() / 60) if utc_offset else 0
        )
        return data

    def list_profiles(self) -> dict:
        return {"info_list": self.acm.get_conf_list()}

    async def create_profile(
        self,
        name: str | None,
        config: dict | None,
        *,
        allow_admin_id_change: bool = True,
    ) -> dict:
        """Create a config profile with explicit admin-ID permission.

        Args:
            name: Display name for the new profile.
            config: Optional initial config content.
            allow_admin_id_change: Whether caller may define non-default admin IDs.

        Returns:
            Identifier of the created config profile.

        Raises:
            ApiError: If caller attempts to define administrator IDs without scope.
            ValueError: If configuration validation fails.
        """
        if (
            not allow_admin_id_change
            and isinstance(config, dict)
            and config.get("admins_id", DEFAULT_CONFIG.get("admins_id"))
            != DEFAULT_CONFIG.get("admins_id")
        ):
            raise ApiError(
                "config:edit_admin scope is required to change admins_id",
                status_code=403,
            )
        profile_config = copy.deepcopy(config or DEFAULT_CONFIG)
        errors, profile_config = validate_config(
            profile_config, CONFIG_METADATA_2, is_core=True, runtime=self.runtime
        )
        if errors:
            raise ValueError(f"Configuration validation failed: {errors}")
        conf_id = await self.acm.create_conf(
            name=name,
            config=profile_config,
        )
        await self.core_lifecycle.reload_pipeline_scheduler(conf_id)
        return {"conf_id": conf_id}

    async def create_profile_from_dashboard_payload(
        self,
        payload: object,
    ) -> dict:
        data = payload if isinstance(payload, dict) else {}
        if not data:
            raise ValueError("缺少配置数据")
        return await self.create_profile(data.get("name"), data.get("config"))

    def get_profile(self, config_id: str) -> dict:
        if config_id not in self.acm.confs:
            raise ValueError(f"Config file {config_id} does not exist")
        return {
            "config": self.acm.confs[config_id],
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3),
        }

    def get_profile_from_dashboard_query(
        self,
        *,
        config_id: str | None,
        system_config: bool,
    ) -> dict:
        if not config_id and not system_config:
            raise ValueError("缺少配置文件 ID")
        if system_config:
            return self.get_system_schema()
        if config_id is None:
            raise ValueError("abconf_id cannot be None")
        return self.get_profile(config_id)

    def get_profile_from_dashboard_args(self, args) -> dict:
        system_config = str(args.get("system_config", "0")).lower() == "1"
        return self.get_profile_from_dashboard_query(
            config_id=args.get("id"),
            system_config=system_config,
        )

    async def update_profile(
        self,
        config_id: str,
        config: dict,
        *,
        two_factor_code: str | None = None,
        allow_admin_id_change: bool = True,
    ) -> str | None:
        """Update a config profile with explicit admin-ID permission.

        Args:
            config_id: Identifier of the profile to update.
            config: Complete replacement config content.
            two_factor_code: Optional TOTP code for protected dashboard changes.
            allow_admin_id_change: Whether caller may change administrator IDs.

        Returns:
            Success message, optionally including a connectivity warning.

        Raises:
            ApiError: If admin IDs change without permission or TOTP is invalid.
            ValueError: If the profile does not exist or validation fails.
        """
        if config_id not in self.acm.confs:
            raise ValueError(f"Config file {config_id} does not exist")
        config = copy.deepcopy(config)
        if config_id == "default":
            default_conf = getattr(self.acm, "default_conf", self.acm.confs["default"])
            for key in ("provider_sources", "provider", "platform"):
                config[key] = default_conf.get(key, [])

        current_config = self.acm.confs[config_id]
        if (
            not allow_admin_id_change
            and "admins_id" in config
            and config.get("admins_id") != current_config.get("admins_id")
        ):
            raise ApiError(
                "config:edit_admin scope is required to change admins_id",
                status_code=403,
            )
        protected_2fa_changed = _protected_2fa_config_changed(current_config, config)
        if (
            is_totp_enabled(current_config)
            and protected_2fa_changed
            and not await self._verify_config_2fa(current_config, two_factor_code)
        ):
            raise ApiError(
                "需要 TOTP 验证",
                status_code=401,
                data={"totp_required": True},
            )

        if not _get_nested_value(config, ("dashboard", "totp", "enable")):
            _set_nested_value(config, ("dashboard", "totp", "secret"), "")
            _set_nested_value(config, ("dashboard", "totp", "recovery_code_hash"), "")

        set_pending_totp_secret(None)
        save_config(
            config, self.acm.confs[config_id], is_core=True, runtime=self.runtime
        )
        if protected_2fa_changed and self.db is not None:
            await revoke_user_trusted_devices(self.db)
        await self.core_lifecycle.reload_pipeline_scheduler(config_id)
        return "保存成功~"

    async def update_profile_from_dashboard_payload(
        self,
        payload: object,
        *,
        two_factor_code: str | None = None,
    ) -> str | None:
        data = payload if isinstance(payload, dict) else {}
        if not isinstance(payload, dict):
            raise ValueError("Invalid request payload")
        config = data.get("config")
        conf_id = data.get("conf_id")
        if not isinstance(config, dict):
            raise ValueError("Invalid config payload")
        return await self.update_profile(
            str(conf_id),
            config,
            two_factor_code=two_factor_code,
        )

    @staticmethod
    async def _verify_config_2fa(
        current_config: dict,
        two_factor_code: str | None,
    ) -> bool:
        code = (two_factor_code or "").strip()
        if not code:
            return False
        return bool(
            await verify_configured_2fa_code(
                current_config,
                code,
                include_pending=True,
                allow_recovery=False,
            )
        )

    async def rename_profile(self, config_id: str, name: str | None) -> None:
        if not await self.acm.update_conf_info(config_id, name=name):
            raise ValueError("Failed to update config profile")

    async def rename_profile_from_dashboard_payload(self, payload: object) -> str:
        data = payload if isinstance(payload, dict) else {}
        if not data:
            raise ValueError("缺少配置数据")
        conf_id = data.get("id")
        if not conf_id:
            raise ValueError("缺少配置文件 ID")
        await self.rename_profile(str(conf_id), name=data.get("name"))
        return "更新成功"

    async def delete_profile(self, config_id: str) -> None:
        if not await self.acm.delete_conf(config_id):
            raise ValueError("Failed to delete config profile")
        self.core_lifecycle.pipeline_scheduler_mapping.pop(config_id, None)

    async def delete_profile_from_dashboard_payload(self, payload: object) -> str:
        data = payload if isinstance(payload, dict) else {}
        if not data:
            raise ValueError("缺少配置数据")
        conf_id = data.get("id")
        if not conf_id:
            raise ValueError("缺少配置文件 ID")
        await self.delete_profile(str(conf_id))
        return "删除成功"


class ConfigRoutingService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.ucr = core_lifecycle.umop_config_router

    def list_routes(self) -> dict:
        return {"routing": self.ucr.umop_to_conf_id}

    async def replace_route_mapping(self, routing: dict[str, str]) -> None:
        await self.ucr.update_routing_data(routing)

    async def replace_routes(self, data: object) -> None:
        payload = data if isinstance(data, dict) else {}
        new_routing = payload.get("routing")
        if not isinstance(new_routing, dict):
            raise ValueError("缺少或错误的路由表数据")
        await self.replace_route_mapping(new_routing)

    async def replace_routes_from_dashboard_payload(self, payload: object) -> str:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("缺少配置数据")
        await self.replace_routes(payload)
        return "更新成功"

    async def upsert_route(self, data: object) -> None:
        payload = data if isinstance(data, dict) else {}
        umo = payload.get("umo")
        conf_id = payload.get("conf_id")
        if not umo or not conf_id:
            raise ValueError("缺少 UMO 或配置文件 ID")
        await self.set_route(str(umo), str(conf_id))

    async def set_route(self, umo: str, config_id: str) -> None:
        if config_id == "default":
            await self.delete_route_by_umo(umo)
            return
        await self.ucr.update_route(umo, config_id)

    async def upsert_route_from_dashboard_payload(self, payload: object) -> str:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("缺少配置数据")
        await self.upsert_route(payload)
        return "更新成功"

    async def delete_route(self, data: object) -> None:
        payload = data if isinstance(data, dict) else {}
        umo = payload.get("umo")
        if not umo:
            raise ValueError("缺少 UMO")
        await self.delete_route_by_umo(str(umo))

    async def delete_route_by_umo(self, umo: str) -> None:
        if umo in self.ucr.umop_to_conf_id:
            del self.ucr.umop_to_conf_id[umo]
            await self.ucr.update_routing_data(self.ucr.umop_to_conf_id)

    async def delete_route_from_dashboard_payload(self, payload: object) -> str:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("缺少配置数据")
        await self.delete_route(payload)
        return "删除成功"


class ConfigDisplayService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self._logo_token_cache: dict[str, str] = {}

    async def get_configs(self, plugin_name: str | None = None) -> dict:
        if not plugin_name:
            return await self.get_astrbot_config()
        return self.get_plugin_config(plugin_name)

    async def get_configs_from_dashboard_args(self, args) -> dict:
        return await self.get_configs(args.get("plugin_name", None))

    async def get_astrbot_config(self) -> dict:
        metadata = copy.deepcopy(CONFIG_METADATA_2)
        platform_i18n = ConfigMetadataI18n.convert_to_i18n_keys(
            {
                "platform_group": {
                    "metadata": {
                        "platform": metadata["platform_group"]["metadata"]["platform"]
                    }
                }
            }
        )
        metadata["platform_group"]["metadata"]["platform"] = platform_i18n[
            "platform_group"
        ]["metadata"]["platform"]

        platform_default_tmpl = metadata["platform_group"]["metadata"]["platform"][
            "config_template"
        ]
        platform_i18n_translations = {}
        logo_registration_tasks = []

        for platform in platform_registry:
            if not platform.default_config_tmpl:
                continue

            platform_default_tmpl[platform.name] = copy.deepcopy(
                platform.default_config_tmpl
            )
            if platform.config_metadata:
                self.inject_platform_metadata_with_i18n(
                    platform,
                    metadata,
                    platform_i18n_translations,
                )
            if platform.logo_path:
                logo_registration_tasks.append(
                    self.register_platform_logo(platform, platform_default_tmpl),
                )

        if logo_registration_tasks:
            await asyncio.gather(*logo_registration_tasks, return_exceptions=True)

        return {
            "metadata": metadata,
            "config": self.config,
            "platform_i18n_translations": platform_i18n_translations,
        }

    def get_plugin_config(self, plugin_name: str) -> dict:
        result: dict = {"metadata": None, "config": None, "i18n": {}}

        for plugin_md in star_registry:
            if plugin_md.name != plugin_name:
                continue
            if not plugin_md.config:
                break
            result["config"] = plugin_md.config
            result["metadata"] = {
                plugin_name: {
                    "description": f"{plugin_name} 配置",
                    "type": "object",
                    "items": plugin_md.config.schema,
                },
            }
            result["i18n"] = plugin_md.i18n
            break

        return result

    async def register_platform_logo(self, platform, platform_default_tmpl) -> None:
        """Attach a reusable logo token to a platform's configuration template.

        Args:
            platform: Registered adapter metadata including its logo path.
            platform_default_tmpl: Configuration templates updated with the token.
        """
        if not platform.logo_path:
            return

        try:
            cache_key = f"{platform.name}:{platform.logo_path}"
            if cached_token := self._logo_token_cache.get(cache_key):
                if not await file_token_service.check_token_expired(cached_token):
                    self._set_platform_logo_token(
                        platform_default_tmpl,
                        platform.name,
                        cached_token,
                    )
                    logger.debug(
                        f"Using cached logo token for platform {platform.name}"
                    )
                    return
                self._logo_token_cache.pop(cache_key, None)

            platform_cls = platform_cls_map.get(platform.name)
            if not platform_cls:
                logger.warning(f"Platform class not found for {platform.name}")
                return

            logo_file_path = (
                Path(inspect.getfile(platform_cls)).parent / platform.logo_path
            )

            if not logo_file_path.exists():
                logger.warning(
                    f"Platform {platform.name} logo file not found: {logo_file_path}",
                )
                return

            logo_token = await file_token_service.register_file(
                str(logo_file_path),
                timeout=3600,
                single_use=False,
            )
            self._set_platform_logo_token(
                platform_default_tmpl,
                platform.name,
                logo_token,
            )
            self._logo_token_cache[cache_key] = logo_token
            logger.debug(f"Logo token registered for platform {platform.name}")

        except (ImportError, AttributeError) as exc:
            logger.warning(
                f"Failed to import required modules for platform {platform.name}: {exc}",
            )
        except OSError as exc:
            logger.warning(
                f"File system error for platform {platform.name} logo: {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"Unexpected error registering logo for platform {platform.name}: {exc}",
            )

    @staticmethod
    def _set_platform_logo_token(
        platform_default_tmpl: dict,
        platform_name: str,
        logo_token: str,
    ) -> None:
        if platform_name not in platform_default_tmpl or not isinstance(
            platform_default_tmpl[platform_name],
            dict,
        ):
            platform_default_tmpl[platform_name] = {}
        platform_default_tmpl[platform_name]["logo_token"] = logo_token

    @staticmethod
    def inject_platform_metadata_with_i18n(
        platform,
        metadata,
        platform_i18n_translations: dict,
    ) -> None:
        metadata["platform_group"]["metadata"]["platform"].setdefault("items", {})
        platform_items_to_inject = copy.deepcopy(platform.config_metadata)

        if platform.i18n_resources:
            i18n_prefix = f"platform_group.platform.{platform.name}"

            for lang, lang_data in platform.i18n_resources.items():
                platform_i18n_translations.setdefault(lang, {}).setdefault(
                    "platform_group", {}
                ).setdefault("platform", {})[platform.name] = lang_data

            for field_key, field_value in platform_items_to_inject.items():
                for key in ("description", "hint", "labels"):
                    if key in field_value:
                        field_value[key] = f"{i18n_prefix}.{field_key}.{key}"

        metadata["platform_group"]["metadata"]["platform"]["items"].update(
            platform_items_to_inject
        )


class ConfigFileService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    def get_plugin_metadata_by_name(self, plugin_name: str):
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                return plugin_md
        return None

    def resolve_config_file_scope(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
    ):
        scope = scope or "plugin"
        if scope != "plugin":
            raise ValueError(f"Unsupported scope: {scope}")
        if not name or not key_path:
            raise ValueError("Missing name or key parameter")

        metadata = self.get_plugin_metadata_by_name(name)
        if not metadata or not metadata.config:
            raise ValueError(f"Plugin {name} not found or has no config")

        return scope, name, key_path, metadata, metadata.config

    async def save_plugin_configs(
        self,
        post_configs: dict,
        plugin_name: str,
    ) -> None:
        metadata = self.get_plugin_metadata_by_name(plugin_name)
        if not metadata:
            raise ValueError(f"插件 {plugin_name} 不存在")
        if not metadata.config:
            raise ValueError(f"插件 {plugin_name} 没有注册配置")

        errors, post_configs = validate_config(
            post_configs,
            getattr(metadata.config, "schema", {}),
            is_core=False,
        )
        if errors:
            raise ValueError(f"格式校验未通过: {errors}")
        metadata.config.save_config(post_configs)
        await self.core_lifecycle.plugin_manager.reload(plugin_name)

    async def save_plugin_configs_from_dashboard_payload(
        self,
        payload: object,
        *,
        plugin_name: str,
    ) -> str:
        post_configs = payload if isinstance(payload, dict) else {}
        await self.save_plugin_configs(post_configs, plugin_name)
        return f"保存插件 {plugin_name} 成功~ 机器人正在热重载插件。"

    async def upload_config_file(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
        files,
    ) -> dict:
        _, name, key_path, _, config = self.resolve_config_file_scope(
            scope=scope,
            name=name,
            key_path=key_path,
        )
        meta = _get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            raise ValueError("Config item not found or not file type")
        if not files:
            raise ValueError("No files uploaded")

        allowed_exts = self._allowed_file_extensions(meta)
        plugin_root_path = self._plugin_root_path(name)
        plugin_root_path.mkdir(parents=True, exist_ok=True)

        uploaded: list[str] = []
        errors: list[str] = []
        folder = _config_key_to_folder(key_path)

        for file in files.values():
            filename = _sanitize_filename(file.filename or "")
            if not filename:
                errors.append("Invalid filename")
                continue

            file_size = getattr(file, "content_length", None)
            if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
                errors.append(f"File too large: {filename}")
                continue

            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if allowed_exts and ext not in allowed_exts:
                errors.append(f"Unsupported file type: {filename}")
                continue

            rel_path = f"files/{folder}/{filename}"
            save_path = self._safe_plugin_path(plugin_root_path, rel_path)
            if save_path is None:
                errors.append(f"Invalid path: {filename}")
                continue

            save_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                await file.save(str(save_path), max_bytes=MAX_FILE_BYTES)
            except UploadTooLargeError:
                errors.append(f"File too large: {filename}")
                continue
            uploaded.append(rel_path)

        if not uploaded:
            raise ValueError(
                "Upload failed: " + ", ".join(errors) if errors else "Upload failed"
            )

        return {"uploaded": uploaded, "errors": errors}

    async def upload_config_file_from_dashboard_request(self, args, files) -> dict:
        return await self.upload_config_file(
            scope=args.get("scope"),
            name=args.get("name"),
            key_path=args.get("key"),
            files=files,
        )

    def delete_config_file(
        self,
        *,
        scope: str | None,
        name: str | None,
        rel_path: str | None,
    ) -> None:
        if not name:
            raise ValueError("Missing name parameter")
        if (scope or "plugin") != "plugin":
            raise ValueError(f"Unsupported scope: {scope}")

        rel_path = _normalize_rel_path(rel_path)
        if not rel_path or not rel_path.startswith("files/"):
            raise ValueError("Invalid path parameter")

        metadata = self.get_plugin_metadata_by_name(name)
        if not metadata:
            raise ValueError(f"Plugin {name} not found")

        plugin_root_path = self._plugin_root_path(name)
        target_path = self._safe_plugin_path(plugin_root_path, rel_path)
        if target_path is None:
            raise ValueError("Invalid path parameter")
        if target_path.is_file():
            target_path.unlink()

    def delete_config_file_from_dashboard_payload(
        self,
        *,
        scope: str | None,
        name: str | None,
        payload: object,
    ) -> str:
        data = payload if isinstance(payload, dict) else {}
        self.delete_config_file(
            scope=scope,
            name=name,
            rel_path=data.get("path"),
        )
        return "Deleted"

    def delete_config_file_from_dashboard_request(
        self,
        args,
        payload: object,
    ) -> str:
        return self.delete_config_file_from_dashboard_payload(
            scope=args.get("scope") or "plugin",
            name=args.get("name"),
            payload=payload,
        )

    def list_config_files(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
    ) -> dict:
        _, name, key_path, _, config = self.resolve_config_file_scope(
            scope=scope,
            name=name,
            key_path=key_path,
        )
        meta = _get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            raise ValueError("Config item not found or not file type")

        plugin_root_path = self._plugin_root_path(name)
        target_dir = self._safe_plugin_path(
            plugin_root_path,
            f"files/{_config_key_to_folder(key_path)}",
        )
        if target_dir is None:
            raise ValueError("Invalid path parameter")
        if not target_dir.exists() or not target_dir.is_dir():
            return {"files": []}

        files: list[str] = []
        for path in target_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel_path = path.relative_to(plugin_root_path).as_posix()
            except ValueError:
                continue
            if rel_path.startswith("files/"):
                files.append(rel_path)
        return {"files": files}

    def list_config_files_from_dashboard_args(self, args) -> dict:
        return self.list_config_files(
            scope=args.get("scope"),
            name=args.get("name"),
            key_path=args.get("key"),
        )

    @staticmethod
    def _allowed_file_extensions(meta: dict) -> list[str]:
        file_types = meta.get("file_types")
        if not isinstance(file_types, list):
            return []
        return [str(ext).lstrip(".").lower() for ext in file_types if str(ext).strip()]

    @staticmethod
    def _plugin_root_path(name: str) -> Path:
        storage_root_path = Path(get_astrbot_plugin_data_path()).resolve(strict=False)
        plugin_root_path = (storage_root_path / name).resolve(strict=False)
        try:
            plugin_root_path.relative_to(storage_root_path)
        except ValueError as exc:
            raise ValueError("Invalid name parameter") from exc
        return plugin_root_path

    @staticmethod
    def _safe_plugin_path(plugin_root_path: Path, rel_path: str) -> Path | None:
        target_path = (plugin_root_path / rel_path).resolve(strict=False)
        try:
            target_path.relative_to(plugin_root_path)
        except ValueError:
            return None
        return target_path


class BotConfigService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config

    def list_bot_types(self) -> dict:
        bot_types = []
        for platform in platform_registry:
            bot_types.append(
                {
                    "type": platform.name,
                    "id": platform.id,
                    "description": platform.description,
                    "display_name": platform.adapter_display_name or platform.name,
                    "default_config": copy.deepcopy(platform.default_config_tmpl),
                    "schema": copy.deepcopy(platform.config_metadata or {}),
                    "support_streaming_message": platform.support_streaming_message,
                    "support_proactive_message": platform.support_proactive_message,
                }
            )
        return {"bot_types": bot_types}

    def list_bots(
        self, *, enabled: bool | None = None, type_: str | None = None
    ) -> dict:
        bots = []
        for bot in self.config.get("platform", []):
            if enabled is not None and bool(bot.get("enable", False)) != enabled:
                continue
            if type_ and bot.get("type") != type_:
                continue
            bots.append(copy.deepcopy(bot))
        return {"bots": bots}

    def get_bot(self, bot_id: str) -> dict:
        bot = self._find_bot(bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        return {"bot": copy.deepcopy(bot)}

    def get_bot_stats(self) -> dict:
        return self.core_lifecycle.platform_manager.get_all_stats()

    async def create_bot(self, config: dict) -> None:
        bot_id = config.get("id")
        if not bot_id:
            raise ValueError("Bot config must have an 'id' field")
        if self._find_bot(bot_id) is not None:
            raise ValueError(f"Bot {bot_id} already exists")
        ensure_platform_webhook_config(config)
        self.config["platform"].append(config)
        save_config(self.config, self.config, is_core=True)
        if event_bus := getattr(self.core_lifecycle, "event_bus", None):
            event_bus.stopped_platforms.discard(bot_id)
        await self.core_lifecycle.platform_manager.load_platform(config)

    async def update_bot(self, bot_id: str, config: dict) -> None:
        if config.get("id") != bot_id:
            raise ValueError("Bot id cannot be changed")
        ensure_platform_webhook_config(config)
        for idx, bot in enumerate(self.config.get("platform", [])):
            if bot.get("id") == bot_id:
                self.config["platform"][idx] = config
                save_config(self.config, self.config, is_core=True)
                await self.core_lifecycle.platform_manager.reload(config)
                return
        raise ValueError(f"Bot {bot_id} not found")

    async def set_bot_enabled(self, bot_id: str, enabled: bool) -> None:
        bot = self._find_bot(bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        new_config = copy.deepcopy(bot)
        new_config["enable"] = enabled
        await self.update_bot(bot_id, new_config)

    async def delete_bot(
        self, bot_id: str, *, cleanup: list[BotCleanupTarget] | None = None
    ) -> None:
        """Stop an adapter and delete only explicitly selected associated data.

        Args:
            bot_id: Exact platform instance ID.
            cleanup: Data categories to remove; omitted categories are retained.

        Raises:
            ValueError: The bot or a cleanup category is invalid.
            Exception: Cleanup or configuration persistence fails.
        """
        bot = self._find_bot(bot_id)
        if bot is None:
            raise ValueError(f"Bot {bot_id} not found")
        targets = set(cleanup or [])
        if targets - set(get_args(BotCleanupTarget)):
            raise ValueError("Invalid bot cleanup category")
        event_bus = getattr(self.core_lifecycle, "event_bus", None)
        await self.core_lifecycle.platform_manager.terminate_platform(bot_id)
        try:
            if event_bus:
                await event_bus.stop_platform(bot_id)
            if targets:
                await delete_bot_data(self.core_lifecycle, bot_id, targets)
            self.config["platform"].remove(bot)
            try:
                save_config(self.config, self.config, is_core=True)
            except Exception:
                self.config["platform"].append(bot)
                raise
        except Exception:
            # Keep the adapter available for inspection or retry after a failure.
            if event_bus:
                event_bus.stopped_platforms.discard(bot_id)
            if bot.get("enable"):
                await self.core_lifecycle.platform_manager.load_platform(bot)
            raise

    def list_platforms_for_dashboard(self) -> dict:
        return {"platforms": self.list_bots()["bots"]}

    async def create_bot_from_dashboard_payload(self, payload: object) -> str:
        if not isinstance(payload, dict):
            raise ValueError("参数错误")
        await self.create_bot(payload)
        return "新增平台配置成功~"

    async def update_bot_from_dashboard_payload(self, payload: object) -> str:
        data = payload if isinstance(payload, dict) else {}
        origin_platform_id = data.get("id")
        new_config = data.get("config")
        if not origin_platform_id or not isinstance(new_config, dict):
            raise ValueError("参数错误")
        if origin_platform_id != new_config.get("id"):
            raise ValueError("机器人名称不允许修改")

        try:
            await self.update_bot(origin_platform_id, new_config)
        except ValueError as exc:
            if "not found" in str(exc):
                raise ValueError("未找到对应平台") from exc
            raise
        return "更新平台配置成功~"

    async def delete_bot_from_dashboard_payload(self, payload: object) -> str:
        data = payload if isinstance(payload, dict) else {}
        platform_id = data.get("id")
        if not platform_id:
            raise ValueError("缺少平台 ID")
        try:
            await self.delete_bot(str(platform_id))
        except ValueError as exc:
            if "not found" in str(exc):
                raise ValueError("未找到对应平台") from exc
            raise
        return "删除平台配置成功~"

    def _find_bot(self, bot_id: str) -> dict | None:
        for bot in self.config.get("platform", []):
            if bot.get("id") == bot_id:
                return bot
        return None
