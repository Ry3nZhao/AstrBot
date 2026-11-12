"""Gateway settings: the ``loagent_gateway`` section of the default config,
overridden by environment variables (LoAgent manages AstrBot through env and
the ``/bots`` API; the dashboard is not for people any more).

| Setting | Env | Default |
|---|---|---|
| ``enabled`` | ``LOAGENT_GATEWAY`` (``1``/``true``) | off |
| ``endpoint`` | ``LOAGENT_GATEWAY_ENDPOINT`` | none (events wait in the outbox) |
| ``token`` | ``LOAGENT_GATEWAY_TOKEN`` | none (the gateway API answers 503) |
| ``heartbeat_grace`` | — | 3 (heartbeat intervals before ``heartbeat_timeout``) |
| ``media_retention_days`` | — | 7 |

The platform instances can be declared the same way: ``LOAGENT_GATEWAY_PLATFORMS``
is a JSON list of platform configs (each with ``id`` and ``type``, like an entry of
``platform`` in ``cmd_config.json``). In gateway mode they replace the configured
instances with the same ``id`` and the others are added, every start, without
writing the config file: LoAgent's Bot service says which protocol sides it runs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


@dataclass
class GatewaySettings:
    enabled: bool = False
    endpoint: str = ""
    token: str = ""
    data_dir: Path = Path("data/loagent_gateway")
    heartbeat_grace: float = 3.0
    default_heartbeat_ms: int = 30_000
    media_retention_days: float = 7.0
    send_retention_days: float = 7.0
    batch_size: int = 50
    request_timeout: float = 15.0

    @classmethod
    def resolve(
        cls, config: dict | None, env: dict[str, str] | None = None
    ) -> GatewaySettings:
        env = os.environ if env is None else env
        conf = config.get("loagent_gateway") if isinstance(config, dict) else None
        if not isinstance(conf, dict):
            conf = {}
        flag = env.get("LOAGENT_GATEWAY")
        enabled = (
            flag.strip().lower() in {"1", "true", "yes", "on"}
            if flag is not None
            else bool(conf.get("enabled", False))
        )
        data_dir = conf.get("data_dir") or os.path.join(
            get_astrbot_data_path(), "loagent_gateway"
        )
        return cls(
            enabled=enabled,
            endpoint=(
                env.get("LOAGENT_GATEWAY_ENDPOINT") or conf.get("endpoint") or ""
            ).rstrip("/"),
            token=env.get("LOAGENT_GATEWAY_TOKEN") or conf.get("token") or "",
            data_dir=Path(data_dir),
            heartbeat_grace=float(conf.get("heartbeat_grace") or 3.0),
            media_retention_days=float(conf.get("media_retention_days") or 7.0),
        )


PLATFORMS_ENV = "LOAGENT_GATEWAY_PLATFORMS"


def declared_platforms(env: dict[str, str] | None = None) -> list[dict]:
    """The platform instances in ``LOAGENT_GATEWAY_PLATFORMS``; ``ValueError`` when
    it is not a JSON list of objects with a string ``id`` and ``type``."""
    env = os.environ if env is None else env
    raw = (env.get(PLATFORMS_ENV) or "").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{PLATFORMS_ENV}: {e}") from e
    if not isinstance(value, list):
        raise ValueError(f"{PLATFORMS_ENV}: not a list")
    for item in value:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) and item.get(k) for k in ("id", "type")
        ):
            raise ValueError(f"{PLATFORMS_ENV}: every entry needs an id and a type")
    ids = [item["id"] for item in value]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{PLATFORMS_ENV}: an id appears twice")
    return value


def apply_platforms(platforms: list, declared: list[dict]) -> None:
    """Puts the declared instances into ``platforms`` (the config's list, changed in
    place): one with the same ``id`` is replaced, the rest are added."""
    for item in declared:
        entry = {"enable": True, **item}
        for i, existing in enumerate(platforms):
            if isinstance(existing, dict) and existing.get("id") == item["id"]:
                platforms[i] = entry
                break
        else:
            platforms.append(entry)
