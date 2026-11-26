"""Signed permanent offline entitlements.

The server holds the Ed25519 seed. Responses carry the payload, the signature, and the key id.
They never carry the seed. A disconnected register cannot learn about a later revocation until it syncs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.device import Device
from app.models.store import Store
from app.schemas.devices import SignedEntitlement
from app.services import audit
from app.tenancy.scoping import active_tenant_id

logger = logging.getLogger("ai_pos.entitlement")

SCHEMA_VERSION = 1
ISSUER = "axizpos"
AUDIENCE = "axizpos-register"
LIMIT_NAMES = ("branches", "products", "registers", "staff")


def canonical_payload(document: dict[str, object]) -> str:
    """Deterministic JSON. The signature covers these exact UTF-8 bytes."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def decode_device_public_key(value: str) -> bytes:
    raw = "".join(value.split())
    if not raw:
        raise ApiError(422, "invalid_device_key", "The device key is not valid.")
    padded = raw + ("=" * (-len(raw) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
    except Exception:
        try:
            decoded = base64.urlsafe_b64decode(padded)
        except Exception as exc:
            raise ApiError(422, "invalid_device_key", "The device key is not valid.") from exc
    if len(decoded) != 32:
        raise ApiError(422, "invalid_device_key", "The device key is not valid.")
    try:
        Ed25519PublicKey.from_public_bytes(decoded)
    except Exception as exc:
        raise ApiError(422, "invalid_device_key", "The device key is not valid.") from exc
    return decoded


def thumbprint(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


def _signing_key() -> tuple[str, Ed25519PrivateKey]:
    settings = get_settings()
    seed_b64 = settings.entitlement_signing_seed.strip()
    key_id = settings.entitlement_signing_key_id.strip()
    if not seed_b64 or not key_id:
        raise ApiError(503, "entitlement_unconfigured", "Permanent entitlement signing is not configured.")
    try:
        seed = base64.b64decode(seed_b64)
        if len(seed) != 32:
            raise ValueError("seed length")
        key = Ed25519PrivateKey.from_private_bytes(seed)
    except Exception:
        logger.error("entitlement signing key is unusable")
        raise ApiError(503, "entitlement_unconfigured", "Permanent entitlement signing is not configured.") from None
    return key_id, key


def _limits() -> dict[str, int | None]:
    from app.console.plan_limits import limit_value

    values: dict[str, int | None] = {}
    for name in LIMIT_NAMES:
        try:
            values[name] = limit_value(name)
        except Exception:
            logger.info("plan limit %s was not read", name)
            values[name] = None
    return values


def _plan_id() -> str:
    """Control-plane plan when it can be read. `local` means this process has no plan row."""
    from app.tenancy.context import current_tenant

    settings = get_settings()
    ref = current_tenant()
    if ref is None or not settings.tenancy_enabled or not ref.id:
        return "local"
    try:
        from sqlalchemy import select

        from app.tenancy.models import Subscription
        from app.tenancy.registry import control_session

        control = control_session(settings)
        try:
            plan = control.scalar(select(Subscription.plan_id).where(Subscription.tenant_id == uuid.UUID(str(ref.id))))
        finally:
            control.close()
        return str(plan) if plan is not None else "local"
    except Exception:
        logger.info("subscription plan was not read for tenant %s", ref.id)
        return "local"


def _profile_and_capabilities(db: Session) -> tuple[str, list[str]]:
    from app.core.capabilities import enabled_capabilities
    from app.services.settings_service import cached_settings

    snapshot = cached_settings(db)
    capabilities = sorted(item.value for item in enabled_capabilities(db))
    return snapshot.business_profile, capabilities


def issue(
    db: Session,
    device: Device,
    store: Store,
    device_public_key: str,
    *,
    rebind: bool,
) -> SignedEntitlement:
    """Signs a permanent entitlement for this device. `rebind` is only for a fresh activation key."""
    public = decode_device_public_key(device_public_key)
    digest = thumbprint(public)
    taken = db.scalar(
        select(Device.id).where(
            Device.device_public_key_thumbprint == digest,
            Device.id != device.id,
        )
    )
    if taken is not None:
        raise ApiError(
            409,
            "device_binding",
            "This device identity is already registered to another till.",
        )
    current = device.device_public_key_thumbprint
    if current and current != digest and not rebind:
        raise ApiError(
            409,
            "device_binding",
            "This register is bound to a different device key. Use a new activation key to replace it.",
        )
    key_id, private = _signing_key()
    profile, capabilities = _profile_and_capabilities(db)
    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "entitlement_id": str(uuid.uuid4()),
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "tenant_id": str(active_tenant_id()),
        "branch_id": str(store.id),
        "terminal_id": str(device.id),
        "device_binding": digest,
        "device_public_key_thumbprint": digest,
        "plan_id": _plan_id(),
        "business_profile": profile,
        # Not a permission grant. The register keeps its existing user and capability checks.
        "capabilities": [],
        "server_capabilities": capabilities,
        "limits": _limits(),
        "issued_at": issued_at,
        "permanent": True,
        "subscription_status": "informational",
        "key_id": key_id,
    }
    payload = canonical_payload(document)
    signature = base64.b64encode(private.sign(payload.encode("utf-8"))).decode("ascii")
    device.device_public_key_thumbprint = digest
    audit.record(
        db,
        action_type="UPDATE",
        action="device.entitlement",
        target_entity="Device",
        target_entity_id=device.id,
        new_values={"entitlement_id": document["entitlement_id"], "key_id": key_id, "thumbprint": digest},
    )
    logger.info("issued entitlement terminal=%s key_id=%s", device.id, key_id)
    return SignedEntitlement(schema_version=SCHEMA_VERSION, key_id=key_id, payload=payload, signature=signature)
