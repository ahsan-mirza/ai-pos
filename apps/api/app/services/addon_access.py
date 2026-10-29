"""Who may use a paid add-on.

Precedence, in order. Every layer that applies has to pass.

1. Subscription. The module must be an active purchased add-on (inside entitlement_until).
   A stored grant does not keep an expired, switched-off, or unpaid module available.
2. Business fit. Purchased keys are already limited to modules that fit the business type.
3. User access.
   - An explicit revoked row wins. A role that contains the module's permissions cannot override it.
   - An explicit granted row allows the module. Its permission list is the action set for this
     module: role permissions do not add actions the grant left out.
   - With no row, the role grants the module only when it actually contains one of the module's
     permissions. The role name (Cashier, Manager, …) grants nothing by itself.
   - The unrestricted Super Admin role may use every active add-on. That is the system role,
     not a generic staff role.
4. Action. A request still needs the permission for that operation. A grant can add a module
     permission the role does not have. A shared permission (used by more than one module) is
     never removed, so revoking one add-on does not take away an unrelated job.
5. Store scope. A manager pinned to one store can change access only for users in that store.
     Tenant isolation is the database tenant filter. Nobody can grant an add-on the store has
     not paid for, or give themselves a permission their own role does not hold.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import get_value, increment, set_value
from app.core.errors import ApiError
from app.core.permissions import ALL_PERMISSIONS, Permission
from app.models.addon_access import UserAddonAccess
from app.models.audit_log import AuditLog
from app.models.base import utcnow
from app.models.role import Role
from app.models.user import User
from app.services import audit
from app.tenancy.context import current_tenant

# Permission key and the action label shown in the admin. Only permissions that belong to the module.
MODULE_ACTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "serial_tracking": (
        (Permission.PORTAL_INVENTORY_MANAGE.value, "View"),
        (Permission.INVENTORY_ADJUST_STOCK.value, "Delete"),
    ),
    "repairs": (
        (Permission.REPAIRS_CREATE.value, "Create"),
        (Permission.REPAIRS_UPDATE.value, "Edit"),
    ),
    "warranty": ((Permission.WARRANTY_MANAGE.value, "Edit"),),
    "cheques": ((Permission.CHEQUES_MANAGE.value, "Edit"),),
    "promotions": ((Permission.PROMOTIONS_MANAGE.value, "Edit"),),
    "sales_orders": ((Permission.SALES_ORDERS.value, "Edit"),),
    "gift_cards": ((Permission.GIFT_CARDS_MANAGE.value, "Edit"),),
    "tax_free": ((Permission.TAX_FREE_MANAGE.value, "Export"),),
    "trade_in": ((Permission.POS_TRADE_IN.value, "Create"),),
    "kds": ((Permission.KDS_OPERATE.value, "Edit"),),
    "online_store": ((Permission.ONLINE_ORDERS.value, "Edit"),),
    "wholesale_pricing": ((Permission.PORTAL_PRICING_MANAGE.value, "Edit"),),
    "deep_analytics": ((Permission.PORTAL_REPORTS_READ.value, "View"),),
    "fashion_rental": (
        (Permission.PORTAL_INVENTORY_MANAGE.value, "View"),
        (Permission.POS_ACCESS.value, "Create"),
    ),
}

_CACHE_TTL = 30


@dataclass(frozen=True)
class Decision:
    allowed: bool
    source: str
    permissions: frozenset[str]
    entitlement: str


def catalog(module_key: str) -> tuple[tuple[str, str], ...]:
    return MODULE_ACTIONS.get(module_key, ())


def catalog_permissions(module_key: str) -> frozenset[str]:
    return frozenset(permission for permission, _label in catalog(module_key))


def _exclusive() -> frozenset[str]:
    """Permissions that belong to one add-on, so a grant or revoke can narrow them safely."""
    seen: dict[str, int] = {}
    for actions in MODULE_ACTIONS.values():
        for permission, _label in actions:
            seen[permission] = seen.get(permission, 0) + 1
    return frozenset(permission for permission, count in seen.items() if count == 1)


def _super(user: User) -> bool:
    return bool(user.role is not None and user.role.is_system and user.role.name == "Super Admin")


def _raw_purchased(db: Session) -> list[str]:
    from app.services.settings_service import load_settings

    row = load_settings(db)
    return [str(key) for key in (row.purchased_capabilities or [])]


def _active_purchased(db: Session) -> set[str]:
    from app.services.settings_service import cached_settings

    return set(cached_settings(db).purchased_capabilities)


def entitlement_status(db: Session, module_key: str) -> str:
    """active, expired, suspended, or unavailable. Assignments do not change this."""
    from app.core.capabilities import enabled_capabilities

    raw = set(_raw_purchased(db))
    active = _active_purchased(db)
    enabled = {capability.value for capability in enabled_capabilities(db)}
    if module_key in active and module_key in enabled:
        return "active"
    if module_key in raw and module_key not in active:
        return "expired"
    if module_key in active and module_key not in enabled:
        return "suspended"
    return "unavailable"


def _rows_for(db: Session, user_id: uuid.UUID) -> dict[str, UserAddonAccess]:
    rows = db.scalars(select(UserAddonAccess).where(UserAddonAccess.user_id == user_id)).all()
    return {row.module_key: row for row in rows}


def decide(user: User, module_key: str, entitlement: str, row: UserAddonAccess | None) -> Decision:
    if entitlement != "active":
        return Decision(False, "inactive", frozenset(), entitlement)
    actions = catalog_permissions(module_key)
    if _super(user):
        return Decision(True, "role", actions, entitlement)
    if row is not None and row.status == "revoked":
        return Decision(False, "revoked", frozenset(), entitlement)
    if row is not None and row.status == "granted":
        chosen = frozenset(str(item) for item in (row.permissions or [])) & actions
        return Decision(True, "grant", chosen, entitlement)
    role_hit = frozenset(user.permissions) & actions
    if role_hit:
        return Decision(True, "role", role_hit, entitlement)
    return Decision(False, "none", frozenset(), entitlement)


def is_purchased(db: Session, module_key: str) -> bool:
    return module_key in set(_raw_purchased(db)) or module_key in _active_purchased(db)


def user_may_use(db: Session, user: User, module_key: str) -> bool:
    if not is_purchased(db, module_key):
        return True
    status = entitlement_status(db, module_key)
    row = _rows_for(db, user.id).get(module_key)
    return decide(user, module_key, status, row).allowed


def enforce_user(db: Session, principal, module_key: str) -> None:
    """403 when a signed-in user may not use this paid add-on. Registers and unpaid modules are unchanged."""
    if getattr(principal, "kind", None) != "user" or principal.user is None:
        return
    if not is_purchased(db, module_key):
        return
    if user_may_use(db, principal.user, module_key):
        return
    from app.core.capabilities import SPECS, Capability

    try:
        label = SPECS[Capability(module_key)].label
    except ValueError:
        label = module_key
    raise ApiError(
        403,
        "addon_access_denied",
        f"You do not have access to {label}. A store administrator can grant it.",
    )


def _generation(tenant_id: uuid.UUID) -> str:
    return get_value(f"tenant:{tenant_id}:addon-generation") or "0"


def invalidate_access_cache(tenant_id: uuid.UUID) -> None:
    """Drops cached effective permissions for the tenant. The next request reads the database."""
    increment(f"tenant:{tenant_id}:addon-generation")


def effective_permissions(db: Session, user: User) -> set[str]:
    """Role permissions, plus granted add-on actions, minus exclusive actions a grant or revoke removed."""
    tenant = current_tenant()
    tenant_id = tenant.id if tenant is not None else user.tenant_id
    generation = _generation(tenant_id)
    paid = ",".join(sorted(_active_purchased(db)))
    cache_key = f"tenant:{tenant_id}:addon:{generation}:paid:{paid}:user:{user.id}:v{user.token_version}"
    cached = get_value(cache_key)
    if cached:
        try:
            return set(json.loads(cached))
        except json.JSONDecodeError:
            pass
    base = set(user.permissions)
    if not _super(user):
        exclusive = _exclusive()
        rows = _rows_for(db, user.id)
        for module_key in paid.split(",") if paid else []:
            decision = decide(user, module_key, entitlement_status(db, module_key), rows.get(module_key))
            actions = catalog_permissions(module_key)
            if decision.source == "grant":
                for permission in actions:
                    if permission in exclusive and permission not in decision.permissions:
                        base.discard(permission)
                base.update(permission for permission in decision.permissions if permission in ALL_PERMISSIONS)
            elif not decision.allowed:
                for permission in actions:
                    if permission in exclusive:
                        base.discard(permission)
    set_value(cache_key, json.dumps(sorted(base)), _CACHE_TTL)
    return base


def addon_modules(db: Session, user: User) -> list[str]:
    """Active purchased modules this user may use. Preset modules are not listed here."""
    allowed: list[str] = []
    rows = _rows_for(db, user.id)
    for module_key in sorted(_active_purchased(db)):
        if decide(user, module_key, "active", rows.get(module_key)).allowed:
            allowed.append(module_key)
    return allowed


def _actor_user(actor) -> User:
    if actor.user is None or Permission.USERS_UPDATE.value not in actor.permissions:
        raise ApiError(403, "forbidden", "You do not have permission to manage add-on access.")
    return actor.user


def _in_store(actor, target: User) -> None:
    if actor.store_id is not None and target.store_id != actor.store_id:
        raise ApiError(403, "store_scope", "You can only manage users in your own store.")


def _check_grant(actor_user: User, target: User, permissions: set[str]) -> None:
    if target.id != actor_user.id:
        return
    role_permissions = set(actor_user.role.permissions)
    extra = sorted(permissions - role_permissions)
    if extra:
        raise ApiError(
            403,
            "privilege_escalation",
            "You cannot grant yourself a permission your role does not hold.",
            details={"permissions": extra},
        )


def _check_delegate(actor_user: User, permissions: set[str]) -> None:
    if _super(actor_user):
        return
    extra = sorted(permissions - set(actor_user.role.permissions))
    if extra:
        raise ApiError(
            403,
            "privilege_escalation",
            "You cannot grant a permission you do not hold.",
            details={"permissions": extra},
        )


def apply_changes(db: Session, actor, changes: list[dict]) -> list[UserAddonAccess]:
    """Grants or revokes add-on access. One row per user and module. The last change in the batch wins."""
    actor_user = _actor_user(actor)
    saved: list[UserAddonAccess] = []
    for change in changes:
        target = db.get(User, change["user_id"])
        if target is None:
            raise ApiError(404, "not_found", "User was not found.")
        _in_store(actor, target)
        module_key = str(change["module_key"])
        if entitlement_status(db, module_key) != "active":
            raise ApiError(409, "addon_inactive", "That add-on is not active for this store.")
        actions = catalog_permissions(module_key)
        requested = set(change.get("permissions") or [])
        unknown = sorted(requested - actions)
        if unknown:
            raise ApiError(
                422,
                "invalid_permission",
                "That action is not part of this add-on.",
                details={"permissions": unknown},
            )
        status = change["status"]
        if status == "granted":
            _check_delegate(actor_user, requested)
            _check_grant(actor_user, target, requested)
        row = db.scalar(
            select(UserAddonAccess).where(
                UserAddonAccess.user_id == target.id,
                UserAddonAccess.module_key == module_key,
            )
        )
        before = None if row is None else {"status": row.status, "permissions": list(row.permissions or [])}
        if row is None:
            row = UserAddonAccess(
                user_id=target.id,
                module_key=module_key,
                store_id=target.store_id,
                permissions=[],
            )
            db.add(row)
        row.status = status
        row.store_id = target.store_id
        if status == "granted":
            row.permissions = sorted(requested)
            row.granted_by_id = actor_user.id
            row.revoked_by_id = None
            row.revoked_at = None
        else:
            row.revoked_by_id = actor_user.id
            row.revoked_at = utcnow()
        audit.record(
            db,
            action_type="UPDATE",
            action="addon_access.grant" if status == "granted" else "addon_access.revoke",
            target_entity="UserAddonAccess",
            target_entity_id=row.id,
            user=actor_user,
            old_values=before,
            new_values={
                "user_id": str(target.id),
                "module_key": module_key,
                "status": status,
                "permissions": list(row.permissions or []),
            },
        )
        saved.append(row)
    db.commit()
    invalidate_access_cache(actor_user.tenant_id)
    for row in saved:
        db.refresh(row)
    return saved


def list_modules(db: Session) -> list[dict]:
    from app.core.capabilities import SPECS, Capability

    raw = _raw_purchased(db)
    seen: list[str] = []
    for key in raw:
        if key not in seen:
            seen.append(key)
    modules: list[dict] = []
    for key in seen:
        try:
            label = SPECS[Capability(key)].label
        except ValueError:
            label = key
        modules.append(
            {
                "key": key,
                "label": label,
                "entitlement": entitlement_status(db, key),
                "actions": [{"permission": permission, "label": label} for permission, label in catalog(key)],
            }
        )
    return modules


def list_users(
    db: Session,
    actor,
    module_key: str,
    *,
    query: str,
    role_id: uuid.UUID | None,
    status: str | None,
    access: str | None,
) -> list[dict]:
    if actor.user is None or not (
        Permission.USERS_READ.value in actor.permissions or Permission.USERS_UPDATE.value in actor.permissions
    ):
        raise ApiError(403, "forbidden", "You do not have permission to view add-on access.")
    statement = select(User).join(Role, User.role_id == Role.id).order_by(User.full_name)
    if actor.store_id is not None:
        statement = statement.where(User.store_id == actor.store_id)
    if role_id is not None:
        statement = statement.where(User.role_id == role_id)
    if status == "active":
        statement = statement.where(User.is_active.is_(True))
    elif status == "inactive":
        statement = statement.where(User.is_active.is_(False))
    entitlement = entitlement_status(db, module_key)
    needle = query.strip().lower()
    rows = []
    assignments = {
        row.user_id: row
        for row in db.scalars(select(UserAddonAccess).where(UserAddonAccess.module_key == module_key)).all()
    }
    for user in db.scalars(statement).unique().all():
        if needle and needle not in " ".join((user.full_name, user.username, user.email, user.role.name)).lower():
            continue
        row = assignments.get(user.id)
        # Classify the row as if the add-on were active, then turn access off when the subscription is not.
        decision = decide(user, module_key, "active", row)
        if entitlement != "active":
            decision = Decision(False, decision.source, decision.permissions, entitlement)
        if access is not None and decision.source != access:
            continue
        rows.append(
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "username": user.username,
                "role_name": user.role.name,
                "is_active": user.is_active,
                "store_id": user.store_id,
                "source": decision.source,
                "allowed": decision.allowed,
                "permissions": sorted(decision.permissions),
                "granted_by_id": None if row is None else row.granted_by_id,
                "revoked_by_id": None if row is None else row.revoked_by_id,
                "revoked_at": None if row is None else row.revoked_at,
                "updated_at": None if row is None else row.updated_at,
            }
        )
    return rows


def history(db: Session, module_key: str | None, user_id: uuid.UUID | None, limit: int) -> list[dict]:
    statement = (
        select(AuditLog)
        .where(AuditLog.action.in_(("addon_access.grant", "addon_access.revoke")))
        .order_by(AuditLog.occurred_at.desc())
        .limit(limit)
    )
    found = []
    for entry in db.scalars(statement).all():
        payload = entry.new_values or {}
        if module_key is not None and payload.get("module_key") != module_key:
            continue
        if user_id is not None and payload.get("user_id") != str(user_id):
            continue
        found.append(
            {
                "id": entry.id,
                "action": entry.action,
                "user_name": entry.user_name,
                "occurred_at": entry.occurred_at if entry.occurred_at.tzinfo else entry.occurred_at.replace(tzinfo=UTC),
                "module_key": payload.get("module_key"),
                "target_user_id": payload.get("user_id"),
                "status": payload.get("status"),
                "permissions": payload.get("permissions") or [],
            }
        )
    return found


def console_snapshot(db: Session) -> dict:
    """Read-only view for the platform console. It does not change subscriptions or grants."""
    modules = []
    for module in list_modules(db):
        rows = db.scalars(select(UserAddonAccess).where(UserAddonAccess.module_key == module["key"])).all()
        granted = sum(1 for row in rows if row.status == "granted")
        modules.append({**module, "assignments": len(rows), "granted": granted})
    recent = history(db, None, None, 20)
    return {"modules": modules, "history": recent}
