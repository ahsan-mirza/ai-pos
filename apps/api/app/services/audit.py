"""Audit trail: automatic before/after capture for every user-driven change, plus explicit handlers for
sensitive actions that must carry a reason.

How the automatic part works:
- `audit_context` middleware records the caller's IP and device; `get_principal` binds the signed-in user.
- After each flush, changed rows in AUDITED_TABLES become pending entries holding a JSON diff.
- Before commit, pending entries are written. An explicit entry for the same record absorbs the diff
  instead of producing a duplicate.
- A mutating request that changed only unaudited tables still leaves one generic entry for the endpoint.
"""

from __future__ import annotations

import enum
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core import audit_context
from app.core.errors import ApiError
from app.models.audit_log import AuditLog
from app.models.base import utcnow
from app.models.user import User
from app.tenancy.context import CONTROL_SESSION

AUDITED_TABLES: dict[str, str] = {
    "products": "Product",
    "categories": "Category",
    "sub_categories": "SubCategory",
    "stores": "Store",
    "users": "User",
    "roles": "Role",
    "business_settings": "Settings",
    "customers": "Customer",
    "product_prices": "ProductPrice",
    "purchase_orders": "PurchaseOrder",
    "stock_transfers": "Transfer",
    "repair_tickets": "RepairTicket",
    "suppliers": "Supplier",
    "import_mapping_templates": "ImportTemplate",
    "purchase_batches": "PurchaseBatch",
    "user_addon_access": "UserAddonAccess",
}

# Columns that change as a side effect of normal use and would only add noise to a diff.
IGNORED_COLUMNS = frozenset({"created_at", "updated_at", "last_login_at", "failed_login_attempts", "locked_until"})
REDACTED = "[redacted]"
_SECRET = re.compile(r"(password|hashed|_hash|secret|encrypted|pin$|token)", re.IGNORECASE)

PATH_ENTITIES: dict[str, str] = {
    "products": "Product",
    "categories": "Category",
    "inventory": "Inventory",
    "stores": "Store",
    "users": "User",
    "roles": "Role",
    "settings": "Settings",
    "returns": "SaleReturn",
    "repairs": "RepairTicket",
    "sales": "Sale",
    "customers": "Customer",
    "pricing": "ProductPrice",
    "quotes": "Quote",
}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_PENDING = "audit_pending"
_EXPLICIT = "audit_explicit"

Key = tuple[str, str]


# --- Serialisation -------------------------------------------------------------------------------


def to_json(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, enum.Enum):
        return to_json(value.value)
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        items = [to_json(item) for item in value]
        return sorted(items, key=str) if isinstance(value, set | frozenset) else items
    if isinstance(value, bytes):
        return "[binary]"
    return str(value)


def _clean(column: str, value: Any) -> Any:
    return REDACTED if _SECRET.search(column) and value is not None else to_json(value)


def _snapshot(instance: Any) -> dict[str, Any]:
    """Loaded column values only; never triggers a lazy load (the row may already be gone)."""
    state = inspect(instance)
    return {
        column.key: _clean(column.key, state.dict[column.key])
        for column in state.mapper.column_attrs
        if column.key not in IGNORED_COLUMNS and column.key in state.dict
    }


def _diff(instance: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    state = inspect(instance)
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for column in state.mapper.column_attrs:
        if column.key in IGNORED_COLUMNS:
            continue
        history = state.attrs[column.key].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        if to_json(before) == to_json(after):
            continue
        old[column.key] = _clean(column.key, before)
        new[column.key] = _clean(column.key, after)
    return old, new


# --- Automatic capture ---------------------------------------------------------------------------


def _store_of(instance: Any) -> uuid.UUID | None:
    value = getattr(instance, "store_id", None)
    return value if isinstance(value, uuid.UUID) else None


def _pending(session: Session) -> dict[Key, dict[str, Any]]:
    return session.info.setdefault(_PENDING, {})


def _queue(
    session: Session,
    *,
    entity: str,
    entity_id: Any,
    action_type: str,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
    store_id: uuid.UUID | None,
) -> None:
    key = (entity, str(entity_id))
    pending = _pending(session)
    existing = pending.get(key)
    if existing is None:
        pending[key] = {
            "entity": entity,
            "entity_id": entity_id,
            "action_type": action_type,
            "old": old,
            "new": new,
            "store_id": store_id,
        }
        return
    # Several flushes in one transaction: keep the first "before" and the latest "after".
    if existing["action_type"] in {"DELETE", "CREATE_DELETED"}:
        return
    if action_type == "DELETE":
        existing["action_type"] = "CREATE_DELETED" if existing["action_type"] == "CREATE" else "DELETE"
        existing["old"] = {**(old or {}), **(existing["old"] or {})}
        existing["new"] = None
        return
    if existing["action_type"] == "CREATE":
        existing["new"] = {**(existing["new"] or {}), **(new or {})}
        return
    if existing["action_type"] == "UPDATE":
        existing["action_type"] = action_type
    merged_old = dict(old or {})
    merged_old.update(existing["old"] or {})
    existing["old"] = merged_old
    existing["new"] = {**(existing["new"] or {}), **(new or {})}


def _classify(entity: str, changed: dict[str, Any]) -> str:
    if entity == "User" and "role_id" in changed:
        return "ROLE_CHANGE"
    if entity == "Customer" and "credit_limit_cents" in changed:
        return "CREDIT_LIMIT_OVERRIDE"
    return "UPDATE"


@event.listens_for(Session, "after_flush")
def _capture(session: Session, _flush_context: Any) -> None:
    context = audit_context.current()
    if context is None or session.info.get(CONTROL_SESSION):
        return
    touched = [*session.new, *session.dirty, *session.deleted]
    if any(getattr(instance, "__tablename__", None) != "audit_logs" for instance in touched):
        context.changed = True
    if context.user_id is None:
        return

    permission_changes: dict[uuid.UUID, dict[str, set[str]]] = {}
    for instance in session.new:
        table = getattr(instance, "__tablename__", None)
        if table == "role_permissions":
            permission_changes.setdefault(instance.role_id, {"added": set(), "removed": set()})["added"].add(
                instance.permission
            )
        elif table in AUDITED_TABLES:
            _queue(
                session,
                entity=AUDITED_TABLES[table],
                entity_id=instance.id,
                action_type="CREATE",
                old=None,
                new=_snapshot(instance),
                store_id=_store_of(instance),
            )
    for instance in session.dirty:
        table = getattr(instance, "__tablename__", None)
        if table not in AUDITED_TABLES or not session.is_modified(instance, include_collections=False):
            continue
        old, new = _diff(instance)
        if not new:
            continue
        entity = AUDITED_TABLES[table]
        _queue(
            session,
            entity=entity,
            entity_id=instance.id,
            action_type=_classify(entity, new),
            old=old,
            new=new,
            store_id=_store_of(instance),
        )
    for instance in session.deleted:
        table = getattr(instance, "__tablename__", None)
        if table == "role_permissions":
            permission_changes.setdefault(instance.role_id, {"added": set(), "removed": set()})["removed"].add(
                instance.permission
            )
        elif table in AUDITED_TABLES:
            _queue(
                session,
                entity=AUDITED_TABLES[table],
                entity_id=instance.id,
                action_type="DELETE",
                old=_snapshot(instance),
                new=None,
                store_id=_store_of(instance),
            )

    from app.models.role import Role

    for role_id, change in permission_changes.items():
        role = session.get(Role, role_id)
        if role is None:
            continue
        after = sorted(role.permissions)
        entry = _pending(session).get(("Role", str(role_id)))
        if entry is not None and entry["action_type"] in {"DELETE", "CREATE_DELETED"}:
            continue
        if entry is not None and entry["action_type"] == "CREATE":
            entry["new"] = {**(entry["new"] or {}), "permissions": after}
            continue
        before = sorted((set(after) - change["added"]) | change["removed"])
        _queue(
            session,
            entity="Role",
            entity_id=role_id,
            action_type="ROLE_CHANGE",
            old={"permissions": before},
            new={"permissions": after},
            store_id=None,
        )


@event.listens_for(Session, "before_commit")
def _write(session: Session) -> None:
    if session.info.get(CONTROL_SESSION):
        return
    # before_commit runs ahead of the final flush; flush now so this commit's changes are captured.
    session.flush()
    pending: dict[Key, dict[str, Any]] = session.info.pop(_PENDING, {})
    explicit: dict[Key, AuditLog] = session.info.pop(_EXPLICIT, {})
    context = audit_context.current()

    written = 0
    for key, entry in pending.items():
        if entry["action_type"] == "CREATE_DELETED":
            continue
        target = explicit.get(key)
        if target is not None:
            if target.old_values is None and entry["old"]:
                target.old_values = entry["old"]
            if target.new_values is None and entry["new"]:
                target.new_values = entry["new"]
            continue
        session.add(
            _build(
                action_type=entry["action_type"],
                action=f"{entry['entity'].lower()}.{entry['action_type'].lower()}",
                target_entity=entry["entity"],
                target_entity_id=entry["entity_id"],
                old_values=entry["old"],
                new_values=entry["new"],
                store_id=entry["store_id"],
            )
        )
        written += 1
    for entry in explicit.values():
        session.add(entry)

    if context is None:
        return
    context.entries += written + len(explicit)
    if context.user_id is not None and context.mutating and context.changed and context.entries == 0:
        session.add(_endpoint_entry(context))
        context.entries += 1
    context.changed = False


@event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_EXPLICIT, None)


def _endpoint_entry(context: audit_context.RequestContext) -> AuditLog:
    segments = [part for part in context.path.split("/") if part]
    resource = segments[2] if len(segments) > 2 and segments[:2] == ["api", "v1"] else (segments or ["api"])[0]
    match = _UUID.search(context.path)
    action_type = {"POST": "CREATE", "DELETE": "DELETE"}.get(context.method, "UPDATE")
    return _build(
        action_type=action_type,
        action=f"request.{context.method.lower()}",
        target_entity=PATH_ENTITIES.get(resource, resource.replace("-", " ").title().replace(" ", "")[:40]),
        target_entity_id=uuid.UUID(match.group(0)) if match else None,
        details={"method": context.method, "path": context.path},
    )


# --- Explicit entries ----------------------------------------------------------------------------


def _build(
    *,
    action_type: str,
    action: str,
    target_entity: str,
    target_entity_id: Any = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    reason_notes: str | None = None,
    store_id: uuid.UUID | None = None,
    user: User | None = None,
    user_id: uuid.UUID | None = None,
    approver_id: uuid.UUID | None = None,
    client_device: str | None = None,
    ip_address: str | None = None,
    occurred_at: datetime | None = None,
    client_event_id: uuid.UUID | None = None,
) -> AuditLog:
    context = audit_context.current()
    if user is not None:
        actor_id, name, role, home = user.id, user.full_name, user.role.name if user.role else None, user.store_id
    elif user_id is None and context is not None:
        actor_id, name, role, home = context.user_id, context.user_name, context.user_role, context.store_id
    else:
        actor_id, name, role, home = user_id, None, None, None
    now = utcnow()
    entity_id = target_entity_id if isinstance(target_entity_id, uuid.UUID) or target_entity_id is None else None
    if entity_id is None and isinstance(target_entity_id, str):
        try:
            entity_id = uuid.UUID(target_entity_id)
        except ValueError:
            entity_id = None
    return AuditLog(
        user_id=actor_id,
        user_name=name,
        user_role=role,
        approver_id=approver_id,
        store_id=store_id if store_id is not None else home,
        action_type=action_type,
        action=action[:64],
        target_entity=target_entity[:40],
        target_entity_id=entity_id,
        old_values=to_json(old_values) if old_values is not None else None,
        new_values=to_json(new_values) if new_values is not None else None,
        details=to_json(details or {}),
        reason_notes=reason_notes.strip() if reason_notes else None,
        ip_address=ip_address if ip_address is not None else (context.ip_address if context else None),
        client_device=client_device or (context.client_device if context else "system"),
        request_path=(context.path[:255] if context else None),
        client_event_id=client_event_id,
        occurred_at=occurred_at or now,
        created_at=now,
    )


def record(db: Session, **fields: Any) -> AuditLog:
    """Queues an explicit entry; it is written on commit, absorbing the automatic diff for the same record.

    Entries are held back until commit because a written entry can no longer be amended.
    """
    entry = _build(**fields)
    queued: dict[Key, AuditLog] = db.info.setdefault(_EXPLICIT, {})
    key = (entry.target_entity, str(entry.target_entity_id) if entry.target_entity_id else f"new:{id(entry)}")
    if key in queued:
        key = (entry.target_entity, f"{key[1]}:{id(entry)}")
    queued[key] = entry
    return entry


def require_reason(reason: str | None, what: str) -> str:
    cleaned = (reason or "").strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reason_required", f"A reason of at least 3 characters is required for {what}.")
    return cleaned


def log_login(db: Session, user: User, method: str, *, client_device: str | None = None) -> AuditLog:
    return record(
        db,
        action_type="LOGIN_PIN" if method == "pin" else "LOGIN_PASSWORD",
        action=f"auth.login_{method}",
        target_entity="User",
        target_entity_id=user.id,
        user=user,
        client_device=client_device,
        details={"username": user.username},
    )


def log_stock_adjustment(
    db: Session,
    *,
    level_id: uuid.UUID,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    quantity_before: int,
    quantity_after: int,
    reason: str | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    return record(
        db,
        action_type="MANUAL_STOCK_ADJUSTMENT",
        action="inventory.adjust",
        target_entity="Inventory",
        target_entity_id=level_id,
        store_id=store_id,
        old_values={"quantity_on_hand": quantity_before},
        new_values={"quantity_on_hand": quantity_after},
        reason_notes=require_reason(reason, "a manual stock adjustment"),
        details={"product_id": product_id, "delta": quantity_after - quantity_before, **(details or {})},
    )


def log_price_override(
    db: Session,
    *,
    sale_id: uuid.UUID,
    product_id: uuid.UUID,
    store_id: uuid.UUID | None,
    list_price_cents: int,
    charged_price_cents: int,
    reason: str | None,
    approver_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AuditLog:
    return record(
        db,
        action_type="PRICE_OVERRIDE",
        action="sale.price_override",
        target_entity="Sale",
        target_entity_id=sale_id,
        store_id=store_id,
        user_id=user_id,
        approver_id=approver_id,
        old_values={"unit_price_cents": list_price_cents},
        new_values={"unit_price_cents": charged_price_cents},
        reason_notes=require_reason(reason, "a price override"),
        details={"product_id": product_id},
    )


def log_credit_limit_override(
    db: Session,
    *,
    customer_id: uuid.UUID,
    limit_cents: int,
    balance_after_cents: int,
    reason: str | None,
    approver_id: uuid.UUID | None = None,
    sale_id: uuid.UUID | None = None,
) -> AuditLog:
    """A sale on account that takes a customer past their credit limit."""
    return record(
        db,
        action_type="CREDIT_LIMIT_OVERRIDE",
        action="customer.credit_override",
        target_entity="Customer",
        target_entity_id=customer_id,
        approver_id=approver_id,
        old_values={"credit_limit_cents": limit_cents},
        new_values={"balance_after_cents": balance_after_cents},
        reason_notes=require_reason(reason, "a credit limit override"),
        details={"sale_id": sale_id, "over_by_cents": balance_after_cents - limit_cents},
    )


def log_role_change(
    db: Session,
    *,
    user: User,
    old_role: str,
    new_role: str,
    reason: str | None = None,
) -> AuditLog:
    return record(
        db,
        action_type="ROLE_CHANGE",
        action="user.role_change",
        target_entity="User",
        target_entity_id=user.id,
        store_id=user.store_id,
        old_values={"role": old_role},
        new_values={"role": new_role},
        reason_notes=reason,
    )


def log_export(db: Session, *, dataset: str, row_count: int, filters: dict[str, Any], file_format: str) -> AuditLog:
    return record(
        db,
        action_type="EXPORT_DATA",
        action=f"export.{dataset}",
        target_entity="AuditLog" if dataset == "audit_logs" else dataset.title(),
        details={"rows": row_count, "format": file_format, "filters": filters},
    )
