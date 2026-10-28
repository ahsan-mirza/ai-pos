"""Profile photos reuse product-media storage: a random WebP key per tenant, served at /media/{tenant}/{key}."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.user import User
from app.schemas.auth import UserOut
from app.services import media_storage
from app.services.product_image_service import MAX_BYTES, reencode
from app.services.rbac_service import user_out

CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_PX = 320


def _kind(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def set_avatar(db: Session, user: User, data: bytes, content_type: str | None) -> UserOut:
    kind = _kind(content_type)
    if kind and kind not in CONTENT_TYPES:
        raise ApiError(415, "unsupported_file", "Profile photos must be a JPEG, PNG, or WebP.")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "Profile photos must be 5 MB or smaller.")
    encoded = reencode(data, AVATAR_PX)
    key = f"avatars/{uuid.uuid4().hex}.webp"
    previous = user.avatar_key
    media_storage.storage_for().put(key, encoded)
    user.avatar_key = key
    db.commit()
    db.refresh(user)
    if previous and previous != key:
        media_storage.storage_for().delete(previous)
    return user_out(user, db)


def clear_avatar(db: Session, user: User) -> UserOut:
    previous = user.avatar_key
    user.avatar_key = None
    db.commit()
    db.refresh(user)
    if previous:
        media_storage.storage_for().delete(previous)
    return user_out(user, db)
