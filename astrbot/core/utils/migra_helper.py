from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger("astrbot")


def migrate_config_on_load(config: dict[str, Any], config_path: Path) -> bool:
    """Run core configuration migrations before integrity cleanup.

    Args:
        config: Mutable AstrBot configuration loaded from disk.
        config_path: Path of the configuration being loaded.

    Returns:
        Whether the configuration changed.
    """
    changed = False
    legacy = config.get("log_file")
    legacy = legacy if isinstance(legacy, dict) else {}
    old_keys = ("trace_log_enable", "trace_log_path", "trace_log_max_mb")
    if any(key in config for key in old_keys) or any(
        key in legacy for key in ("trace_enable", "trace_path", "trace_max_mb")
    ):
        old_size = config.get("trace_log_max_mb", legacy.get("trace_max_mb", 20))
        if "trace_db_max_mb" not in config:
            config["trace_db_max_mb"] = (
                old_size * 4
                if isinstance(old_size, int)
                and not isinstance(old_size, bool)
                and old_size > 0
                else 80
            )
        config.setdefault("trace_db_path", "logs/traces.db")
        config.setdefault("trace_retention_days", 7)
        for key in old_keys:
            config.pop(key, None)
        for key in ("trace_enable", "trace_path", "trace_max_mb"):
            legacy.pop(key, None)
        logger.warning(
            "Trace file settings migrated to SQLite in %s. Recording now persists when trace_enable is on; old files are untouched and not imported.",
            config_path,
        )
        changed = True
    config_version = config.get("config_version")
    if not isinstance(config_version, int) or config_version < 5:
        config["config_version"] = 5
        changed = True
    return changed


async def migra(
    db: Any, astrbot_config_mgr: Any, umop_config_router: Any, acm: Any
) -> None:
    """Run migrations that require initialized configuration or database state.

    Args:
        db: Initialized AstrBot database.
        astrbot_config_mgr: Configuration manager used by legacy migrations.
        umop_config_router: Initialized UMOP configuration router.
        acm: Initialized AstrBot configuration manager.
    """
    from astrbot.core.db.migration.migra_45_to_46 import migrate_45_to_46
    from astrbot.core.db.migration.migra_token_usage import migrate_token_usage
    from astrbot.core.db.migration.migra_webchat_session import (
        migrate_webchat_session,
    )

    try:
        await migrate_45_to_46(astrbot_config_mgr, umop_config_router)
    except Exception as exc:
        logger.error("Migration from version 4.5 to 4.6 failed: %s", exc)
        logger.error(traceback.format_exc())

    try:
        await migrate_webchat_session(db)
    except Exception as exc:
        logger.error("Migration for webchat session failed: %s", exc)
        logger.error(traceback.format_exc())

    try:
        await migrate_token_usage(db)
    except Exception as exc:
        logger.error("Migration for token_usage column failed: %s", exc)
        logger.error(traceback.format_exc())
