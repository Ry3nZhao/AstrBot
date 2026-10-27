from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from astrbot.dashboard.services.file_service import FileService, FileServiceError

router = APIRouter(tags=["Files"])
legacy_router = APIRouter(prefix="/api", include_in_schema=False)

# LoAgent channel gateway: only the short-lived file token routes remain. They
# serve media that platform adapters hand out through the file token service.
# The ChatUI attachment upload routes were removed together with WebChat.


def get_service(request: Request) -> FileService:
    return request.app.state.services.files


async def _serve_token_file(file_token: str, service: FileService):
    try:
        return FileResponse(await service.resolve_token_file(file_token))
    except FileServiceError as exc:
        raise HTTPException(status_code=404) from exc


@router.get("/files/tokens/{file_token}")
async def get_token_file(
    file_token: str,
    service: FileService = Depends(get_service),
):
    return await _serve_token_file(file_token, service)


@legacy_router.get("/file/{file_token}")
async def get_dashboard_token_file(
    file_token: str,
    service: FileService = Depends(get_service),
):
    return await _serve_token_file(file_token, service)
