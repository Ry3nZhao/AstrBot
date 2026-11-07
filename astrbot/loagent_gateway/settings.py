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
"""

from __future__ import annotations

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
