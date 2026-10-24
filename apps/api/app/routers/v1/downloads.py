import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.downloads import DownloadsOut, LatestInstaller
from app.services import downloads_service
from app.services.rbac_service import holds_super_admin

router = APIRouter()
logger = logging.getLogger("ai_pos.downloads")


def require_super_admin(principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]) -> Principal:
    if principal.user is None or not holds_super_admin(principal.user):
        raise ApiError(403, "super_admin_only", "Only a Super Admin can download the POS installer.")
    return principal


SuperAdmin = Annotated[Principal, Depends(require_super_admin)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=DownloadsOut)
def list_downloads(_: SuperAdmin, settings: Config) -> DownloadsOut:
    return downloads_service.list_releases(settings)


@router.get("/latest.json", response_model=LatestInstaller)
def latest_installer(settings: Config) -> LatestInstaller:
    """Public version feed. A register that cannot reach this stays on the installed version."""
    return downloads_service.latest_feed(settings)


@router.get("/win", response_class=FileResponse)
def latest_windows_installer(settings: Config) -> FileResponse:
    return latest_windows_file(settings)


def latest_windows_file(settings: Settings) -> FileResponse:
    _release, _chosen, path = downloads_service.latest_windows(settings)
    return FileResponse(
        path,
        media_type=downloads_service.MEDIA_TYPES["exe"],
        filename="AI-POS-Setup-latest.exe",
    )


@router.get("/pos/{version}/{filename}", response_class=FileResponse)
def download_installer(version: str, filename: str, principal: SuperAdmin, settings: Config) -> FileResponse:
    path, kind = downloads_service.installer(settings, version, filename)
    assert principal.user is not None
    logger.info("POS installer %s %s downloaded by %s", version, filename, principal.user.username)
    return FileResponse(path, media_type=downloads_service.MEDIA_TYPES[kind], filename=filename)
