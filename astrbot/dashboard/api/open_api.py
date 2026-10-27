from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import ImMessageRequest
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
)

from .auth import AuthContext, ScopeDependency

# LoAgent channel gateway: the Open API keeps the IM endpoints that LoAgent
# uses to speak proactively (/im/messages) and to list bots (/im/bots). The
# ChatUI endpoints (/chat, /chat/ws, /file, /configs) were removed with WebChat.

router = APIRouter(tags=["Open API"])


require_im_scope = ScopeDependency("im")


def get_service(request: Request) -> OpenApiService:
    return request.app.state.services.open_api


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True, exclude_none=False)
    return payload if isinstance(payload, dict) else {}


@router.post("/im/messages")
async def send_im_message(
    payload: ImMessageRequest,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    body = _model_dict(payload)
    try:
        await service.send_message(body)
    except OpenApiServiceError as exc:
        raise ApiError(str(exc)) from exc

    return ok()


@router.post("/im/message", include_in_schema=False)
async def send_im_message_alias(
    payload: ImMessageRequest,
    auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    return await send_im_message(payload, auth, service)


@router.get("/im/bots")
async def list_im_bots(
    _request: Request,
    _auth: AuthContext = Depends(require_im_scope),
    service: OpenApiService = Depends(get_service),
):
    return ok(service.get_bots())
