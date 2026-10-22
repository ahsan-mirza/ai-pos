"""Serves tenant media (product photos) without sign-in: keys are random and the tenant is in the path, so <img>
tags work in the portal, on registers and in exported catalogues."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.core.errors import ApiError
from app.services import media_storage

router = APIRouter()


@router.get("/media/{tenant}/{folder}/{name}", include_in_schema=False)
def media(tenant: str, folder: str, name: str) -> FileResponse:
    if not media_storage.SLUG.fullmatch(tenant):
        raise ApiError(404, "not_found", "File was not found.")
    path = media_storage.storage_for(tenant).path(f"{folder}/{name}")
    if path is None:
        raise ApiError(404, "not_found", "File was not found.")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})
