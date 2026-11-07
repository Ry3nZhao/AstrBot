"""LoAgent gateway: AstrBot as the platform access layer of LoAgent's Bot service.

Protocol and wiring: ``LOAGENT.md`` (「LoAgent 网关协议 v1」). This package is
self-contained; AstrBot's own code only calls it from three seams
(``EventBus.observer``, ``AstrBotCoreLifecycle``, ``create_dashboard_asgi_app``).
"""

from .gateway import LoAgentGateway
from .settings import GatewaySettings

__all__ = ["GatewaySettings", "LoAgentGateway"]
