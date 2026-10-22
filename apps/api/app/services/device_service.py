"""Register credentials. Keys are 256-bit random tokens; only their SHA-256 is stored (a slow hash adds nothing
for keys with this much entropy and would run on every request)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
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
    TerminalActivate,
    TerminalActivation,
)
from app.services import audit
from app.services.numbering import DEVICE_SUFFIX, device_prefix
from app.tenancy.registry import current_identity

DEVICE_DOCS = ("INV", "CN", "Z")


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
    statement = select(Device).order_by(Device.store_id, Device.code)
    scope = principal.store_id or store_id
    if scope is not None:
        statement = statement.where(Device.store_id == scope)
    return [device_out(db, row) for row in db.scalars(statement).all()]


def create_device(db: Session, principal: Principal, data: DeviceCreate) -> DeviceKeyOut:
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


def revoke(db: Session, principal: Principal, device_id: uuid.UUID) -> DeviceOut:
    device = _get(db, principal, device_id)
    if device.revoked_at is None:
        device.revoked_at = datetime.now(UTC)
        audit.record(
            db,
            action_type="UPDATE",
            action="device.revoke",
            target_entity="Device",
            target_entity_id=device.id,
            user=principal.user,
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
    if device is None or store is None:
        raise ApiError(401, "activation_invalid", "This activation key is wrong, already used, or expired.")
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
