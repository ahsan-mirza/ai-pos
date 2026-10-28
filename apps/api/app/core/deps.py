import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Header
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import audit_context
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.core.security import decode_access_token, secrets_equal
from app.models.device import Device
from app.models.user import User
from app.tenancy.context import current_tenant


@dataclass(frozen=True)
class Principal:
    """Who is calling: a registered POS device (X-Api-Key) or a signed-in user (Bearer token).

    A device authenticated with its own key is bound to its branch; the legacy shared key is not."""

    kind: Literal["device", "user"]
    scope: Literal["device", "portal", "pos"]
    user: User | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    device: Device | None = None

    @property
    def store_id(self) -> uuid.UUID | None:
        if self.user is not None:
            return self.user.store_id
        return self.device.store_id if self.device is not None else None

    def has(self, *required: Permission) -> bool:
        return all(item.value in self.permissions for item in required)


LAST_SEEN_RESOLUTION = timedelta(minutes=1)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def device_from_key(db: Session, settings: Settings, key: str) -> Principal | None:
    device = db.scalar(select(Device).where(Device.key_hash == hash_device_key(key)))
    if device is not None:
        if device.revoked_at is not None:
            raise ApiError(401, "device_revoked", "This register's key was revoked. Register it again.")
        now = datetime.now(UTC)
        seen = device.last_seen_at
        if seen is None or (seen.replace(tzinfo=UTC) if seen.tzinfo is None else seen) < now - LAST_SEEN_RESOLUTION:
            db.execute(update(Device).where(Device.id == device.id).values(last_seen_at=now))
            db.commit()
        return Principal(kind="device", scope="device", device=device)
    if settings.allow_shared_api_key and secrets_equal(key, settings.api_key):
        return Principal(kind="device", scope="device")
    return None


TerminalToken = Annotated[str | None, Header(alias="X-Terminal-Token")]


def require_device(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    x_terminal_token: TerminalToken = None,
) -> Principal:
    """Registers send their device token as X-Terminal-Token (activated) or X-Api-Key (legacy)."""
    key = x_terminal_token or x_api_key
    principal = device_from_key(db, settings, key) if key else None
    if principal is None:
        raise ApiError(401, "unauthorized", "A valid terminal token is required.")
    return principal


def require_api_key(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    x_terminal_token: TerminalToken = None,
) -> None:
    require_device(db, settings, x_api_key, x_terminal_token)


def _user_from_token(token: str, db: Session, settings: Settings) -> tuple[User, str]:
    try:
        claims = decode_access_token(token, settings=settings)
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ApiError(401, "invalid_token", "The access token is invalid or expired.") from exc
    tenant = current_tenant()
    if tenant is not None and claims.get("tid") != tenant.id:
        raise ApiError(401, "invalid_token", "This access token belongs to another store. Sign in again.")
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != claims.get("ver"):
        raise ApiError(401, "invalid_token", "The access token is no longer valid.")
    scope = str(claims.get("scope"))
    if scope == "portal" and not user.has_portal_access:
        raise ApiError(401, "invalid_token", "Web portal access was revoked.")
    if scope == "pos" and not user.has_pos_access:
        raise ApiError(401, "invalid_token", "POS access was revoked.")
    if scope not in {"portal", "pos"}:
        raise ApiError(401, "invalid_token", "The access token scope is invalid.")
    return user, scope


def verify_user_token(token: str, db: Session, settings: Settings) -> User:
    user, _ = _user_from_token(token, db, settings)
    return user


def get_principal(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    x_terminal_token: TerminalToken = None,
) -> Principal:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise ApiError(401, "invalid_token", "Use a Bearer access token.")
        user, scope = _user_from_token(token.strip(), db, settings)
        audit_context.bind_user(user.id, user.full_name, user.role.name if user.role else None, user.store_id)
        from app.services.addon_access import effective_permissions

        return Principal(
            kind="user",
            scope=scope,  # type: ignore[arg-type]
            user=user,
            permissions=frozenset(effective_permissions(db, user)),
        )
    key = x_terminal_token or x_api_key
    if key is not None:
        principal = device_from_key(db, settings, key)
        if principal is not None:
            return principal
    raise ApiError(401, "unauthorized", "Sign in or provide a valid API key.")


def authorize(
    *required: Permission,
    allow_device: bool = False,
    scopes: tuple[str, ...] = ("portal",),
) -> Callable[[Principal], Principal]:
    """Dependency factory. Users need every listed permission and a token issued for an allowed scope."""

    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.kind == "device":
            if allow_device:
                return principal
            raise ApiError(403, "forbidden", "This action requires a signed-in user.")
        if principal.scope not in scopes:
            raise ApiError(403, "forbidden", "This token cannot be used for this action.")
        if not principal.has(*required):
            missing = [item.value for item in required if item.value not in principal.permissions]
            raise ApiError(
                403,
                "forbidden",
                "You do not have permission for this action.",
                details={"missing": missing},
            )
        return principal

    return dependency


def current_user(principal: Annotated[Principal, Depends(get_principal)]) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user
