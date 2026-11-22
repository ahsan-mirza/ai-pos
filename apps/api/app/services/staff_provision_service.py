"""Accept or reject a register's staff change. Authorization is checked again here, not trusted from the till."""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import CASHIER_ROLE_ID, STORE_MANAGER_ROLE_ID
from app.models.role import Role
from app.models.staff_provisioning import StaffProvisioningEvent
from app.models.user import User
from app.services import audit
from app.services.rbac_service import _assert_can_grant, _assert_store_scope

ALLOWED_ROLES = {"Cashier": CASHIER_ROLE_ID, "Store Manager": STORE_MANAGER_ROLE_ID}


def _digest(body: dict[str, object]) -> str:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verifier_ok(value: str) -> bool:
    return value.startswith("$argon2id$") and 20 < len(value) <= 255


def provision(
    db: Session,
    actor: Principal,
    body: dict[str, object],
) -> dict[str, object]:
    if actor.user is None:
        raise ApiError(403, "forbidden", "Staff provisioning requires a signed-in manager.")
    event_id = str(body.get("event_id") or "")
    operation = str(body.get("operation") or "")
    if len(event_id) < 8 or operation not in {"create", "disable", "update", "pin_reset"}:
        raise ApiError(422, "invalid_provisioning", "The staff event is not valid.")
    digest = _digest(body)
    existing = db.scalar(select(StaffProvisioningEvent).where(StaffProvisioningEvent.event_id == event_id))
    if existing is not None:
        if existing.payload_hash != digest:
            raise ApiError(409, "provisioning_conflict", "This staff event was already sent with a different payload.")
        return {"status": "duplicate", "event_id": event_id, "user_id": str(existing.user_id) if existing.user_id else None}

    try:
        user = _apply(db, actor, body, operation)
    except ApiError as exc:
        db.rollback()
        db.add(_event(event_id, operation, digest, "rejected", None, exc.message[:300], body))
        db.commit()
        raise
    row = _event(event_id, operation, digest, "accepted", user.id, "accepted", body)
    db.add(row)
    audit.record(
        db,
        action_type="CREATE" if operation == "create" else "UPDATE",
        action=f"staff.{operation}",
        target_entity="User",
        target_entity_id=user.id,
        store_id=user.store_id,
        user=actor.user,
        new_values={"username": user.username, "is_active": user.is_active, "event_id": event_id},
    )
    db.commit()
    return {"status": "accepted", "event_id": event_id, "user_id": str(user.id)}


def _event(
    event_id: str,
    operation: str,
    digest: str,
    status: str,
    user_id: uuid.UUID | None,
    message: str,
    body: dict[str, object],
) -> StaffProvisioningEvent:
    base = str(body.get("base_version") or "")[:64]
    return StaffProvisioningEvent(
        event_id=event_id,
        operation=operation,
        payload_hash=digest,
        status=status,
        user_id=user_id,
        safe_message=message,
        origin_terminal_id=str(body.get("origin_terminal_id") or "")[:64],
        schema_version=1,
        base_version=base or None,
    )


def accepted_staff(db: Session) -> list[dict[str, object]]:
    """Staff the server has accepted. Pending and rejected events are not in this list."""
    rows = db.scalars(
        select(User)
        .join(StaffProvisioningEvent, StaffProvisioningEvent.user_id == User.id)
        .where(StaffProvisioningEvent.status == "accepted")
    ).unique().all()
    feed: list[dict[str, object]] = []
    for user in rows:
        verifier = user.hashed_pin or ""
        if not verifier.startswith("$argon2id$"):
            continue
        feed.append(
            {
                "user_id": str(user.id),
                "username": user.username,
                "full_name": user.full_name,
                "store_id": str(user.store_id) if user.store_id else None,
                "role_name": user.role.name if user.role else "",
                "is_active": user.is_active,
                "pin_verifier": verifier,
            }
        )
    return feed


def _apply(db: Session, actor: Principal, body: dict[str, object], operation: str) -> User:
    role_name = str(body.get("role_name") or "")
    if role_name in {"Super Admin", "Platform Super Admin"} or role_name not in ALLOWED_ROLES:
        raise ApiError(403, "role_not_allowed", "This register cannot grant that role.")
    actor_role = actor.user.role.name if actor.user is not None and actor.user.role is not None else ""
    if actor_role == "Store Manager" and role_name != "Cashier":
        raise ApiError(403, "role_not_allowed", "You cannot grant that role.")
    if actor_role not in {"Store Manager", "Super Admin"}:
        raise ApiError(403, "role_not_allowed", "You cannot manage staff.")
    role = db.get(Role, uuid.UUID(ALLOWED_ROLES[role_name]))
    if role is None:
        raise ApiError(422, "unknown_role", "That role is not available.")
    _assert_can_grant(actor, set(role.permissions))
    store_id = uuid.UUID(str(body["store_id"]))
    _assert_store_scope(actor, store_id)
    user_id = uuid.UUID(str(body["user_id"]))
    if operation == "pin_reset":
        user = db.get(User, user_id)
        if user is None:
            raise ApiError(404, "not_found", "That staff member is not on the server yet.")
        _assert_store_scope(actor, user.store_id)
        verifier = str(body.get("pin_verifier") or "")
        if not _verifier_ok(verifier):
            raise ApiError(422, "invalid_verifier", "The PIN verifier is not an Argon2 hash.")
        user.hashed_pin = verifier
        user.token_version += 1
        db.flush()
        return user
    if operation == "update":
        user = db.get(User, user_id)
        if user is None:
            raise ApiError(404, "not_found", "That staff member is not on the server yet.")
        _assert_store_scope(actor, user.store_id)
        full_name = str(body.get("full_name") or "").strip()
        if full_name:
            user.full_name = full_name
        user.role_id = role.id
        user.token_version += 1
        db.flush()
        return user
    if operation == "disable":
        user = db.get(User, user_id)
        if user is None:
            raise ApiError(404, "not_found", "That staff member is not on the server yet.")
        if actor.user is not None and actor.user.id == user.id:
            raise ApiError(422, "self_change", "You cannot disable your own account.")
        user.is_active = False
        user.token_version += 1
        db.flush()
        return user

    from app.console.plan_limits import assert_room

    used = int(db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0)
    assert_room(used, "staff")
    username = str(body.get("username") or "")
    verifier = str(body.get("pin_verifier") or "")
    if not _verifier_ok(verifier):
        raise ApiError(422, "invalid_verifier", "The PIN verifier is not an Argon2 hash.")
    if db.scalar(select(User).where(User.username == username)) is not None:
        raise ApiError(409, "conflict", "Username is already in use.")
    user = User(
        id=user_id,
        username=username,
        email=str(body.get("email") or f"{username}@staff.local"),
        full_name=str(body.get("full_name") or username).strip(),
        hashed_pin=verifier,
        is_active=True,
        store_id=store_id,
        role_id=role.id,
        has_pos_access=True,
        has_portal_access=False,
    )
    db.add(user)
    db.flush()
    return user
