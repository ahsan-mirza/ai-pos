"""Campaign files on the tenant disk. Product photos keep their own webp keys."""

from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.services.media_storage import ROOT, tenant_slug
from reach.models import ReachMediaAsset

_KINDS = {
    "image/jpeg": ("image", "jpg"),
    "image/png": ("image", "png"),
    "image/webp": ("image", "webp"),
    "video/mp4": ("video", "mp4"),
    "application/pdf": ("document", "pdf"),
}
_NAME = re.compile(r"^reach/[0-9a-f]{32}\.(jpg|png|webp|mp4|pdf)$")


def _limit(settings: Settings, kind: str) -> int:
    if kind == "image":
        return settings.reach_media_max_image_bytes
    if kind == "video":
        return settings.reach_media_max_video_bytes
    return settings.reach_media_max_document_bytes


def _magic_ok(mime: str, data: bytes) -> bool:
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if mime == "application/pdf":
        return data.startswith(b"%PDF")
    if mime == "video/mp4":
        return len(data) > 12 and data[4:8] == b"ftyp"
    return False


def _path(key: str) -> Path:
    if not _NAME.fullmatch(key):
        raise ApiError(422, "invalid_media", "That file reference is not valid.")
    slug = tenant_slug()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug):
        raise ApiError(422, "invalid_media", "This store cannot store files.")
    return ROOT / slug / "reach-media" / key


def save_upload(db: Session, settings: Settings, file_name: str, mime: str, data: bytes) -> ReachMediaAsset:
    spec = _KINDS.get(mime)
    if spec is None:
        raise ApiError(422, "unsupported_media", "Use a JPG, PNG, WebP, MP4, or PDF file.")
    kind, ext = spec
    if not data or not _magic_ok(mime, data):
        raise ApiError(422, "corrupt_media", "The file contents do not match its type.")
    limit = _limit(settings, kind)
    if len(data) > limit:
        raise ApiError(422, "media_too_large", f"This {kind} file is over the {limit} byte limit.")
    key = f"reach/{uuid.uuid4().hex}.{ext}"
    target = _path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(target)
    row = ReachMediaAsset(
        file_name=(file_name or f"file.{ext}")[:160],
        mime_type=mime,
        kind=kind,
        size_bytes=len(data),
        storage_key=key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def read_bytes(row: ReachMediaAsset) -> bytes:
    path = _path(row.storage_key)
    if not path.is_file():
        raise ApiError(404, "media_missing", "The uploaded file is no longer on disk.")
    return path.read_bytes()


def file_path(row: ReachMediaAsset) -> Path:
    path = _path(row.storage_key)
    if not path.is_file():
        raise ApiError(404, "media_missing", "The uploaded file is no longer on disk.")
    return path


def remove(db: Session, asset_id: uuid.UUID) -> None:
    row = db.get(ReachMediaAsset, asset_id)
    if row is None:
        raise ApiError(404, "not_found", "File not found.")
    try:
        _path(row.storage_key).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(row)
    db.commit()


def payload_for(db: Session, media_id: str) -> dict | None:
    try:
        asset_id = uuid.UUID(str(media_id))
    except ValueError:
        return None
    row = db.get(ReachMediaAsset, asset_id)
    if row is None:
        return None
    return {
        "mediatype": row.kind,
        "mimetype": row.mime_type,
        "file_name": row.file_name,
        "data_b64": base64.b64encode(read_bytes(row)).decode("ascii"),
    }
