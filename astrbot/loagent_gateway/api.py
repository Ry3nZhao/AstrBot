"""HTTP API of the gateway, on AstrBot's dashboard server under ``/api/v1/loagent``.

Every call needs ``Authorization: Bearer <LOAGENT_GATEWAY_TOKEN>``; without a
configured token every call is refused (503 ``not_configured``). Errors are
``{"error": {"code", "message", "retryable"}}``.

While the gateway is on, the dashboard's self-update endpoints are refused:
an update would replace this fork with upstream AstrBot (pit 3 in bots.md).
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from . import protocol as P
from .gateway import LoAgentGateway
from .outbound import OutboundError

router = APIRouter(prefix=P.API_PREFIX, include_in_schema=False)

_UPDATE_PATHS = ("/api/v1/updates/", "/api/update/")


def _error(code: str, message: str, retryable: bool = False) -> JSONResponse:
    body = P.ErrorResponse(
        error=P.ErrorDetail(code=code, message=message, retryable=retryable)
    )
    return JSONResponse(body.to_json(), status_code=P.HTTP_STATUS[code])


def _gateway(request: Request) -> LoAgentGateway | None:
    core = getattr(request.app.state, "core_lifecycle", None)
    for candidate in (
        getattr(core, "loagent_gateway", None),
        getattr(request.app.state, "loagent_gateway", None),
    ):
        if isinstance(candidate, LoAgentGateway):
            return candidate
    return None


async def _guarded(request: Request, call):
    gateway = _gateway(request)
    if gateway is None:
        return _error("not_configured", "the LoAgent gateway is not running")
    denied = gateway.check_token(request.headers.get("authorization"))
    if denied == "not_configured":
        return _error(denied, "LOAGENT_GATEWAY_TOKEN is not set")
    if denied:
        return _error(denied, "missing or wrong bearer token")
    try:
        result = await call(gateway)
    except OutboundError as exc:
        return _error(exc.code, exc.message, exc.retryable)
    if isinstance(result, P._Model):
        return JSONResponse(result.to_json())
    return result


def _required(request: Request, *names: str) -> list[str]:
    values = []
    for name in names:
        value = request.query_params.get(name, "").strip()
        if not value:
            raise OutboundError("invalid_request", f"missing query parameter {name!r}")
        values.append(value)
    return values


@router.get("/health")
async def health(request: Request):
    async def call(gw: LoAgentGateway):
        return gw.health()

    return await _guarded(request, call)


@router.get("/accounts")
async def accounts(request: Request):
    async def call(gw: LoAgentGateway):
        return gw.accounts()

    return await _guarded(request, call)


@router.post("/send")
async def send(request: Request):
    async def call(gw: LoAgentGateway):
        try:
            body = await request.json()
        except ValueError as exc:
            raise OutboundError("invalid_request", f"body is not JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise OutboundError("invalid_request", "body must be an object")
        if body.get("v") != P.PROTOCOL_VERSION:
            raise OutboundError(
                "unsupported_version", f"protocol v{body.get('v')} is not supported"
            )
        try:
            req = P.SendRequest.model_validate(body)
        except ValidationError as exc:
            raise OutboundError("invalid_request", str(exc)[:1000]) from exc
        return await gw.send(req)

    return await _guarded(request, call)


@router.get("/conversations")
async def conversations(request: Request):
    async def call(gw: LoAgentGateway):
        instance, self_id = _required(request, "instance", "self_id")
        return await gw.conversations(instance, self_id)

    return await _guarded(request, call)


@router.get("/members")
async def members(request: Request):
    async def call(gw: LoAgentGateway):
        instance, self_id, group_id = _required(
            request, "instance", "self_id", "group_id"
        )
        return await gw.members(instance, self_id, group_id)

    return await _guarded(request, call)


@router.get("/profile")
async def profile(request: Request):
    async def call(gw: LoAgentGateway):
        instance, self_id, user_id = _required(
            request, "instance", "self_id", "user_id"
        )
        return await gw.profile(
            instance, self_id, user_id, request.query_params.get("group_id") or None
        )

    return await _guarded(request, call)


@router.get("/history")
async def history(request: Request):
    async def call(gw: LoAgentGateway):
        instance, self_id, kind, conv_id = _required(
            request, "instance", "self_id", "kind", "id"
        )
        if kind not in ("group", "private"):
            raise OutboundError("invalid_request", "kind must be group or private")
        try:
            count = int(request.query_params.get("count") or 20)
        except ValueError as exc:
            raise OutboundError("invalid_request", "count must be a number") from exc
        return await gw.history(
            instance,
            self_id,
            kind,
            conv_id,
            count,
            request.query_params.get("before") or None,
        )

    return await _guarded(request, call)


@router.post("/media")
async def upload_media(request: Request):
    async def call(gw: LoAgentGateway):
        data = await request.body()
        if not data:
            raise OutboundError("invalid_request", "empty body")
        name = unquote(request.headers.get("x-media-name", "")) or None
        mime = request.headers.get("content-type", "").split(";")[0].strip() or None
        if mime in ("application/octet-stream", "application/x-www-form-urlencoded"):
            mime = None
        try:
            media = gw.media.put(data, name=name, mime=mime)
        except ValueError as exc:
            raise OutboundError("invalid_request", str(exc)) from exc
        return P.MediaUploadResponse(media=media)

    return await _guarded(request, call)


@router.get("/media/{sha256}")
async def download_media(request: Request, sha256: str):
    async def call(gw: LoAgentGateway):
        path = gw.media.path_of(sha256)
        if path is None:
            raise OutboundError("media_unavailable", f"no media {sha256}")
        meta = gw.media.meta_of(sha256)
        return FileResponse(
            path, media_type=meta.get("mime") or "application/octet-stream"
        )

    return await _guarded(request, call)


def install(app: FastAPI) -> None:
    """Mount the gateway API and refuse self-updates while the gateway is on."""
    app.include_router(router)

    @app.middleware("http")
    async def refuse_self_update(request: Request, call_next):
        gateway = _gateway(request)
        if (
            gateway is not None
            and gateway.enabled
            and request.method == "POST"
            and request.url.path.startswith(_UPDATE_PATHS)
        ):
            return JSONResponse(
                {
                    "status": "error",
                    "message": "LoAgent gateway build: update by rebuilding the image, not from the dashboard.",
                    "data": None,
                },
                status_code=403,
            )
        return await call_next(request)
