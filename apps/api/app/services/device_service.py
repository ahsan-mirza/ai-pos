"""Register credentials. Keys are 256-bit random tokens; only their SHA-256 is stored (a slow hash adds nothing
for keys with this much entropy and would run on every request)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import Principal, hash_device_key
from app.core.errors import ApiError
from app.models.device import Device, DeviceActivation
from app.models.document_sequence import DocumentSequence
from app.models.store import Store
from app.schemas.devices import (
    ActivationKeyOut,
    DeviceCreate,
    DeviceKeyOut,
    DeviceOut,
    DeviceSelfOut,
    DeviceSeries,
    RegisterCapacity,
    TerminalActivate,
    TerminalActivation,
)
from app.services import audit, entitlement_service
from app.services.numbering import DEVICE_SUFFIX, device_prefix
from app.tenancy.registry import current_identity

DEVICE_DOCS = ("INV", "CN", "Z")
ONLINE_WINDOW = timedelta(minutes=10)


def _active_register_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.revoked_at.is_(None), Device.deleted_at.is_(None))
        )
        or 0
    )


def _require_register_seat(db: Session) -> None:
    """The plan cap counts tills that are not revoked. A released till frees its seat only after commit."""
    from app.console.plan_limits import limit_value

    cap = limit_value("registers")
    if cap is None or _active_register_count(db) < cap:
        return
    raise ApiError(
        409,
        "plan_limit",
        f"This plan includes {cap} registers. Delete an existing till or upgrade the package.",
    )


def _activation_status(device: Device) -> str:
    if device.revoked_at is not None:
        return "revoked"
    seen = device.last_seen_at
    if seen is None:
        return "pending"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    if seen >= datetime.now(UTC) - ONLINE_WINDOW:
        return "active"
    return "offline"


def _machine_name(db: Session, device_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(DeviceActivation.used_by_machine)
        .where(DeviceActivation.device_id == device_id, DeviceActivation.used_by_machine.is_not(None))
        .order_by(DeviceActivation.used_at.desc())
        .limit(1)
    )


def _new_key() -> tuple[str, str]:
    key = f"aipos_{secrets.token_urlsafe(32)}"
    return key, hash_device_key(key)


def _last_value(db: Session, prefix: str) -> int:
    value = db.scalar(select(DocumentSequence.last_value).where(DocumentSequence.prefix == prefix))
    return int(value or 0)


def device_out(db: Session, device: Device) -> DeviceOut:
    store = db.get(Store, device.store_id)
    assert store is not None
    prefix = device_prefix(store, device, "INV")
    return DeviceOut(
        id=device.id,
        store_id=device.store_id,
        store_code=store.code,
        code=device.code,
        name=device.name,
        key_hint=device.key_hint,
        invoice_prefix=prefix,
        last_invoice_value=_last_value(db, prefix),
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
        created_at=device.created_at,
        activation_status=_activation_status(device),
        machine_name=_machine_name(db, device.id),
    )


def _scoped(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only manage registers in your own store.")


def _get(db: Session, principal: Principal, device_id: uuid.UUID) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise ApiError(404, "not_found", "Register was not found.")
    _scoped(principal, device.store_id)
    return device


def list_devices(db: Session, principal: Principal, store_id: uuid.UUID | None) -> list[DeviceOut]:
    statement = select(Device).where(Device.deleted_at.is_(None)).order_by(Device.store_id, Device.code)
    scope = principal.store_id or store_id
    if scope is not None:
        statement = statement.where(Device.store_id == scope)
    return [device_out(db, row) for row in db.scalars(statement).all()]


def register_capacity(db: Session) -> RegisterCapacity:
    from app.console.plan_limits import limit_value

    used = _active_register_count(db)
    cap = limit_value("registers")
    available = None if cap is None else max(cap - used, 0)
    return RegisterCapacity(used=used, limit=cap, available=available)


def create_device(db: Session, principal: Principal, data: DeviceCreate) -> DeviceKeyOut:
    _require_register_seat(db)
    _scoped(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(422, "unknown_store", "Store does not exist.")
    key, digest = _new_key()
    device = Device(
        store_id=data.store_id,
        code=data.code.upper(),
        name=data.name.strip(),
        key_hash=digest,
        key_hint=key[-6:],
        created_by_id=principal.user.id if principal.user is not None else None,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", f"Register {data.code.upper()} already exists at this store.") from exc
    audit.record(
        db,
        action_type="CREATE",
        action="device.register",
        target_entity="Device",
        target_entity_id=device.id,
        user=principal.user,
        new_values={"code": device.code, "name": device.name, "store_id": str(device.store_id)},
    )
    db.commit()
    db.refresh(device)
    return DeviceKeyOut(device=device_out(db, device), key=key)


def rotate_key(db: Session, principal: Principal, device_id: uuid.UUID) -> DeviceKeyOut:
    device = _get(db, principal, device_id)
    if device.deleted_at is not None:
        raise ApiError(404, "not_found", "Register was not found.")
    if device.revoked_at is not None:
        _require_register_seat(db)
    key, digest = _new_key()
    device.key_hash = digest
    device.key_hint = key[-6:]
    device.revoked_at = None
    audit.record(
        db,
        action_type="UPDATE",
        action="device.rotate_key",
        target_entity="Device",
        target_entity_id=device.id,
        user=principal.user,
    )
    db.commit()
    db.refresh(device)
    return DeviceKeyOut(device=device_out(db, device), key=key)


def _block_if_unsynced(device: Device, verb: str) -> None:
    from app.services.settings_service import offline_pending_for

    if offline_pending_for(str(device.id)) > 0:
        raise ApiError(
            409,
            "pending_offline",
            f"This till still has unsynced transactions. Sync it before {verb} it.",
        )


def _retire(db: Session, principal: Principal, device_id: uuid.UUID, *, action: str) -> DeviceOut:
    """Stops the till and frees its package seat. Sales, sequences, and the device row stay."""
    device = _get(db, principal, device_id)
    if device.deleted_at is not None:
        raise ApiError(404, "not_found", "Register was not found.")
    if device.revoked_at is None:
        verb = "releasing" if action == "device.release" else "revoking"
        _block_if_unsynced(device, verb)
        now = datetime.now(UTC)
        device.revoked_at = now
        db.execute(
            update(DeviceActivation)
            .where(DeviceActivation.device_id == device.id, DeviceActivation.used_at.is_(None))
            .values(expires_at=now)
        )
        audit.record(
            db,
            action_type="UPDATE",
            action=action,
            target_entity="Device",
            target_entity_id=device.id,
            user=principal.user,
            store_id=device.store_id,
            new_values={
                "code": device.code,
                "store_id": str(device.store_id),
                "revoked_at": now.isoformat(),
            },
        )
        db.commit()
        db.refresh(device)
    return device_out(db, device)


def revoke(db: Session, principal: Principal, device_id: uuid.UUID) -> DeviceOut:
    return _retire(db, principal, device_id, action="device.revoke")


def release_device(db: Session, principal: Principal, device_id: uuid.UUID) -> DeviceOut:
    return _retire(db, principal, device_id, action="device.release")


def delete_device(db: Session, principal: Principal, device_id: uuid.UUID) -> DeviceOut:
    """Frees the package seat and the till code. Sales, cash, and invoice numbers stay on this row."""
    device = _get(db, principal, device_id)
    if device.deleted_at is not None:
        raise ApiError(404, "not_found", "Register was not found.")
    now = datetime.now(UTC)
    if device.revoked_at is None:
        _block_if_unsynced(device, "deleting")
        device.revoked_at = now
        db.execute(
            update(DeviceActivation)
            .where(DeviceActivation.device_id == device.id, DeviceActivation.used_at.is_(None))
            .values(expires_at=now)
        )
    original = device.code
    device.deleted_at = now
    device.code = f"Z{device.id.hex[:11]}"
    audit.record(
        db,
        action_type="UPDATE",
        action="device.delete",
        target_entity="Device",
        target_entity_id=device.id,
        user=principal.user,
        store_id=device.store_id,
        new_values={
            "code": original,
            "store_id": str(device.store_id),
            "revoked_at": device.revoked_at.isoformat() if device.revoked_at is not None else None,
            "deleted_at": now.isoformat(),
        },
    )
    db.commit()
    db.refresh(device)
    return device_out(db, device)


ACTIVATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread
ACTIVATION_TTL = timedelta(hours=24)


def normalize_activation_key(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _hash_activation(value: str) -> str:
    return hashlib.sha256(normalize_activation_key(value).encode("utf-8")).hexdigest()


def issue_activation_key(db: Session, principal: Principal, device_id: uuid.UUID) -> ActivationKeyOut:
    """A fresh one-time key for this register; any earlier unused key stops working."""
    device = _get(db, principal, device_id)
    if device.deleted_at is not None:
        raise ApiError(404, "not_found", "Register was not found.")
    now = datetime.now(UTC)
    db.execute(
        update(DeviceActivation)
        .where(DeviceActivation.device_id == device.id, DeviceActivation.used_at.is_(None))
        .values(expires_at=now)
    )
    raw = "".join(secrets.choice(ACTIVATION_ALPHABET) for _ in range(12))
    key = "-".join(raw[index : index + 4] for index in range(0, 12, 4))
    activation = DeviceActivation(
        device_id=device.id,
        code_hash=_hash_activation(key),
        expires_at=now + ACTIVATION_TTL,
        created_by_id=principal.user.id if principal.user is not None else None,
    )
    db.add(activation)
    audit.record(
        db,
        action_type="CREATE",
        action="device.activation_key",
        target_entity="Device",
        target_entity_id=device.id,
        user=principal.user,
    )
    db.commit()
    return ActivationKeyOut(
        device_id=device.id,
        activation_key=key,
        expires_at=activation.expires_at,
        tenant_domain=current_identity().domain,
    )


def replace_device_token(db: Session, device: Device) -> str:
    """Rotates the register key and returns the new token. The caller commits."""
    token, digest = _new_key()
    device.key_hash = digest
    device.key_hint = token[-6:]
    return token


def activate_terminal(db: Session, data: TerminalActivate) -> TerminalActivation:
    """Exchanges a one-time key for the register's device token (the key is rotated, so old installs stop)."""
    now = datetime.now(UTC)
    activation = db.scalar(
        select(DeviceActivation).where(DeviceActivation.code_hash == _hash_activation(data.activation_key))
    )
    expires = activation.expires_at if activation is not None else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if activation is None or activation.used_at is not None or expires is None or expires <= now:
        raise ApiError(401, "activation_invalid", "This activation key is wrong, already used, or expired.")
    device = db.get(Device, activation.device_id)
    store = db.get(Store, device.store_id) if device is not None else None
    if device is None or store is None or device.deleted_at is not None:
        raise ApiError(401, "activation_invalid", "This activation key is wrong, already used, or expired.")
    from app.services.settings_service import offline_pending_for

    if offline_pending_for(str(device.id)) > 0:
        raise ApiError(
            409,
            "pending_offline",
            "This till still has unsynced transactions. Sync it before activating a replacement.",
        )
    if device.revoked_at is not None:
        _require_register_seat(db)
    entitlement = None
    if data.device_public_key.strip():
        # Sign before the one-time key is consumed. A missing signing seed must not burn the key.
        entitlement = entitlement_service.issue(db, device, store, data.device_public_key, rebind=True)
    token, digest = _new_key()
    device.key_hash = digest
    device.key_hint = token[-6:]
    device.revoked_at = None
    activation.used_at = now
    activation.used_by_machine = data.machine_name.strip() or None
    audit.record(
        db,
        action_type="UPDATE",
        action="device.activate",
        target_entity="Device",
        target_entity_id=device.id,
        new_values={"machine": activation.used_by_machine},
    )
    db.commit()
    identity = current_identity()
    from app.tenancy.scoping import active_tenant_id

    return TerminalActivation(
        tenant_slug=identity.slug,
        tenant_name=identity.name,
        tenant_domain=identity.domain,
        tenant_url=identity.url,
        tenant_id=str(active_tenant_id()),
        store_id=store.id,
        store_code=store.code,
        store_name=store.name,
        register_id=device.id,
        register_code=device.code,
        register_name=device.name,
        device_token=token,
        entitlement=entitlement,
    )


def self_info(db: Session, device: Device) -> DeviceSelfOut:
    store = db.get(Store, device.store_id)
    assert store is not None
    series = []
    for doc in DEVICE_DOCS:
        prefix = device_prefix(store, device, doc)
        series.append(DeviceSeries(doc_type=doc, prefix=prefix, last_value=_last_value(db, prefix)))
    assert set(DEVICE_DOCS) <= set(DEVICE_SUFFIX)
    return DeviceSelfOut(
        id=device.id, code=device.code, name=device.name, store_id=device.store_id, store_code=store.code, series=series
    )
