"""Short-lived tickets that enroll a demo register and then issue the existing device token.

The business code selects the tenant. Host, X-Tenant-Domain, and any client tenant id are ignored.
The ticket is single-use. Only its SHA-256 is stored. The device token uses the same key format
as terminal activation and is returned once.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.device import DemoPosTicket, Device
from app.models.store import Store
from app.schemas.auth import TokenResponse
from app.schemas.devices import PosEnrollResponse, TerminalActivation
from app.services import audit, device_service, rbac_service
from app.services.demo_access import DemoAccessError, _category, _explorer, _load, _session, _unavailable
from app.tenancy.context import current_tenant, use_tenant
from app.tenancy.models import Tenant
from app.tenancy.registry import control_session, current_identity, ref_for

logger = logging.getLogger("ai_pos.demo_pos")

APPLICATION_SCOPE = "pos"
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _digest(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _code_from_ticket(ticket: str) -> str | None:
    code, separator, _secret = ticket.partition(".")
    if separator != "." or code == "" or _secret == "":
        return None
    return code


def _refuse(code: str, category: str, client_host: str) -> DemoAccessError:
    logger.info("demo pos refused code=%s category=%s client=%s", code, category, client_host)
    return _unavailable(code, category, client_host)


def _open(settings: Settings, code: str, client_host: str):
    normalized = code.strip().lower()
    row, spec, category = _load(settings, normalized)
    if row is None or spec is None or category is not None:
        raise _refuse(normalized, category or "unknown_code", client_host)
    return normalized, row, spec


def _record(
    db: Session,
    tenant_id: uuid.UUID,
    code: str,
    action: str,
    result: str,
    device_id: uuid.UUID | None,
) -> None:
    audit.record(
        db,
        action_type="UPDATE",
        action=action,
        target_entity="Device" if device_id is not None else "Tenant",
        target_entity_id=device_id or tenant_id,
        client_device="desktop",
        details={"business_code": code, "result": result},
    )


def _active_store(db: Session) -> Store | None:
    return db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.code))


def _explorer_can_sell(db: Session):
    user, problem = _explorer(db)
    if user is None or problem is not None:
        return None, problem or "explorer_missing"
    permissions = set(user.permissions)
    if Permission.POS_ACCESS.value not in permissions or not user.has_pos_access:
        return user, "pos_permission"
    if Permission.DEVICES_MANAGE.value in permissions or Permission.USERS_CREATE.value in permissions:
        return user, "pos_permission"
    return user, None


def _provision_device(db: Session, store: Store) -> Device:
    """One demo register per enrollment. The initial key is discarded and replaced at exchange."""
    for _ in range(5):
        code = "D" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        token, digest = device_service._new_key()
        del token
        device = Device(
            store_id=store.id,
            code=code,
            name="Demo Register",
            key_hash=digest,
            key_hint="demo",
            is_demo=True,
        )
        try:
            with db.begin_nested():
                db.add(device)
                db.flush()
            return device
        except IntegrityError:
            continue
    raise _refuse("demo", "device_code", "unknown")


def enroll_pos_demo(settings: Settings, code: str, *, client_host: str) -> PosEnrollResponse:
    normalized, row, _spec = _open(settings, code, client_host)
    ref = ref_for(row, settings)
    db = _session(settings, row)
    try:
        with use_tenant(ref):
            store = _active_store(db)
            user, problem = _explorer_can_sell(db)
            if store is None or user is None or problem is not None:
                _record(db, row.id, normalized, "demo.pos_enroll", problem or "store_inactive", None)
                db.commit()
                raise _refuse(normalized, problem or "store_inactive", client_host)
            device = _provision_device(db, store)
            secret = secrets.token_urlsafe(32)
            ticket = f"{normalized}.{secret}"
            expires = datetime.now(UTC) + timedelta(seconds=settings.demo_pos_ticket_ttl_seconds)
            row_ticket = DemoPosTicket(
                device_id=device.id,
                code_hash=_digest(ticket),
                application_scope=APPLICATION_SCOPE,
                expires_at=expires,
            )
            db.add(row_ticket)
            db.flush()
            _record(db, row.id, normalized, "demo.pos_enroll", "issued", device.id)
            db.commit()
            logger.info("demo pos ticket issued code=%s device=%s client=%s", normalized, device.id, client_host)
            return PosEnrollResponse(
                enrollment_ticket=ticket,
                expires_in=settings.demo_pos_ticket_ttl_seconds,
                business_code=normalized,
            )
    finally:
        db.close()


def exchange_pos_ticket(settings: Settings, ticket: str, machine_name: str, *, client_host: str) -> TerminalActivation:
    code = _code_from_ticket(ticket.strip())
    if code is None:
        raise _refuse("invalid", "ticket", client_host)
    normalized, row, _spec = _open(settings, code, client_host)
    ref = ref_for(row, settings)
    db = _session(settings, row)
    try:
        with use_tenant(ref):
            now = datetime.now(UTC)
            digest = _digest(ticket.strip())
            consumed = db.execute(
                update(DemoPosTicket)
                .where(
                    DemoPosTicket.code_hash == digest,
                    DemoPosTicket.used_at.is_(None),
                    DemoPosTicket.expires_at > now,
                    DemoPosTicket.application_scope == APPLICATION_SCOPE,
                )
                .values(used_at=now, used_by_machine=(machine_name.strip() or None))
            )
            if consumed.rowcount != 1:
                _record(db, row.id, normalized, "demo.pos_exchange", "ticket", None)
                db.commit()
                raise _refuse(normalized, "ticket", client_host)
            found = db.scalar(select(DemoPosTicket).where(DemoPosTicket.code_hash == digest))
            device = db.get(Device, found.device_id) if found is not None else None
            store = db.get(Store, device.store_id) if device is not None else None
            if (
                device is None
                or store is None
                or not device.is_demo
                or device.revoked_at is not None
                or not store.is_active
            ):
                _record(db, row.id, normalized, "demo.pos_exchange", "terminal", None)
                db.commit()
                raise _refuse(normalized, "terminal", client_host)
            token = device_service.replace_device_token(db, device)
            _record(db, row.id, normalized, "demo.pos_exchange", "issued", device.id)
            db.commit()
            identity = current_identity()
            logger.info("demo pos exchange issued code=%s device=%s client=%s", normalized, device.id, client_host)
            return TerminalActivation(
                tenant_slug=identity.slug,
                tenant_name=identity.name,
                tenant_domain=identity.domain,
                tenant_url=identity.url,
                store_id=store.id,
                store_code=store.code,
                store_name=store.name,
                register_id=device.id,
                register_code=device.code,
                register_name=device.name,
                device_token=token,
            )
    finally:
        db.close()


def issue_demo_pos_session(db: Session, settings: Settings, device: Device) -> TokenResponse:
    """POS session for the Demo Explorer. The caller must already hold this demo register's device token."""
    if not device.is_demo or device.revoked_at is not None:
        raise ApiError(403, "pos_demo_unavailable", "This register cannot open a demo session.")
    tenant = current_tenant()
    if tenant is None:
        raise ApiError(403, "pos_demo_unavailable", "This register cannot open a demo session.")
    with control_session(settings) as control:
        row = control.get(Tenant, uuid.UUID(tenant.id))
        if row is None or _category(row, row.demo_business_type or "") is not None:
            raise ApiError(403, "pos_demo_unavailable", "This register cannot open a demo session.")
    user, problem = _explorer_can_sell(db)
    if user is None or problem is not None:
        raise ApiError(403, "pos_demo_unavailable", "This register cannot open a demo session.")
    return rbac_service.issue_session(db, settings, user, "pos-demo", demo=True)


def revoke_demo_registers(db: Session) -> int:
    """Stops demo register keys and unused tickets. Shared catalog rows are left in place."""
    now = datetime.now(UTC)
    devices = db.scalars(select(Device).where(Device.is_demo.is_(True), Device.revoked_at.is_(None))).all()
    for device in devices:
        device.revoked_at = now
    db.execute(
        update(DemoPosTicket)
        .where(DemoPosTicket.used_at.is_(None))
        .values(used_at=now, expires_at=now)
    )
    db.commit()
    return len(devices)
