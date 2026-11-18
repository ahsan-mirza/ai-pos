"""Issues a portal session for one public demo business code.

The code is not a secret. The control database decides which tenant it names.
The request's host and X-Tenant-Domain are ignored: this runs only after the
exchange path has been left out of normal tenant binding. The session is the
existing portal token for the Demo Explorer user, with a server-set demo claim.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import DemoAccessResponse
from app.services import audit, rbac_service
from app.services.demo_catalog import EXPLORER_USERNAME, DemoSeedError, _session, tenant_spec
from app.tenancy import registry
from app.tenancy.context import use_tenant
from app.tenancy.models import Tenant

logger = logging.getLogger("ai_pos.demo_access")

_PUBLIC = "This demo is not available."


class DemoAccessError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "demo_unavailable", _PUBLIC)


def _unavailable(code: str, category: str, client_host: str) -> DemoAccessError:
    logger.info("demo exchange refused code=%s category=%s client=%s", code, category, client_host)
    return DemoAccessError()


def _expired(value: datetime | None) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def _category(row: Tenant, code: str) -> str | None:
    if not row.is_demo or row.demo_business_type != code:
        return "not_demo"
    if not row.demo_access_enabled:
        return "access_disabled"
    if _expired(row.demo_expires_at):
        return "expired"
    status = row.demo_status or ""
    if status == "disabled":
        return "disabled"
    if status == "resetting":
        return "resetting"
    if status == "reset_failed":
        return "reset_failed"
    if status != "active" or row.status != "active":
        return "not_active"
    return None


def _load(settings: Settings, code: str) -> tuple[Tenant | None, dict | None, str | None]:
    try:
        spec = tenant_spec(code)
    except DemoSeedError:
        return None, None, "unknown_code"
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if row is None:
            return None, spec, "unknown_tenant"
        category = _category(row, code)
        db.expunge(row)
        return row, spec, category


def _record(db: Session, tenant_id: uuid.UUID, code: str, category: str, user: User | None, client_host: str) -> None:
    audit.record(
        db,
        action_type="LOGIN_PASSWORD" if category == "issued" else "UPDATE",
        action="demo.exchange",
        target_entity="Tenant",
        target_entity_id=tenant_id,
        user=user,
        client_device="web",
        details={
            "business_code": code,
            "result": "success" if category == "issued" else "refused",
            "category": category,
            "client": client_host,
        },
    )
    db.commit()


def _explorer(db: Session) -> tuple[User | None, str | None]:
    user = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
    if user is None:
        return None, "explorer_missing"
    if not user.is_active:
        return user, "explorer_inactive"
    role = user.role
    # Later stores copy the system role, so the shared UUID is not the id on every tenant.
    permissions = set() if role is None else set(role.permissions)
    if (
        role is None
        or not role.is_system
        or role.name != "Demo Explorer"
        or Permission.PORTAL_ACCESS.value not in permissions
        or Permission.USERS_CREATE.value in permissions
    ):
        return user, "explorer_role"
    return user, None


def exchange_demo_access(settings: Settings, code: str, *, client_host: str) -> DemoAccessResponse:
    """Resolves one catalog demo and signs in its Demo Explorer. Every refusal looks the same."""
    normalized = code.strip().lower()
    row, spec, category = _load(settings, normalized)
    if row is None or spec is None or category is not None:
        if row is not None and row.is_demo and row.demo_business_type == normalized:
            refused = category or "refused"
            ref = registry.ref_for(row, settings)
            db = _session(settings, row)
            try:
                with use_tenant(ref):
                    _record(db, row.id, normalized, refused, None, client_host)
            finally:
                db.close()
        raise _unavailable(normalized, category or "unknown_code", client_host)
    ref = registry.ref_for(row, settings)
    db = _session(settings, row)
    response: DemoAccessResponse | None = None
    try:
        with use_tenant(ref):
            user, problem = _explorer(db)
            if user is None or problem is not None:
                _record(db, row.id, normalized, problem or "explorer_missing", None, client_host)
                raise _unavailable(normalized, problem or "explorer_missing", client_host)
            owner = db.scalar(select(User).join(Role).where(Role.name == "Super Admin", Role.is_system.is_(True)))
            if owner is not None and user.id == owner.id:
                _record(db, row.id, normalized, "super_admin", None, client_host)
                raise _unavailable(normalized, "super_admin", client_host)
            issued = rbac_service.issue_session(db, settings, user, "demo", demo=True)
            _record(db, row.id, normalized, "issued", user, client_host)
            response = DemoAccessResponse(
                access_token=issued.access_token,
                token_type=issued.token_type,
                scope=issued.scope,
                expires_in=issued.expires_in,
                user=issued.user,
                demo=True,
                business_code=normalized,
                business_name=spec["name"],
            )
    finally:
        db.close()
    if response is None:
        raise _unavailable(normalized, "explorer_missing", client_host)
    logger.info("demo exchange issued code=%s tenant=%s client=%s", normalized, row.id, client_host)
    return response


def set_demo_access(settings: Settings, code: str, *, enabled: bool) -> dict:
    """Turns the public door on or off. It does not change demo status or the subscription."""
    try:
        spec = tenant_spec(code)
    except DemoSeedError as exc:
        raise DemoAccessError() from exc
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if row is None or not row.is_demo or row.demo_business_type != code:
            raise DemoAccessError()
        if enabled and (row.demo_status != "active" or row.status != "active" or _expired(row.demo_expires_at)):
            raise DemoAccessError()
        row.demo_access_enabled = enabled
        db.commit()
    return {"code": code, "slug": spec["slug"], "demo_access_enabled": enabled}
