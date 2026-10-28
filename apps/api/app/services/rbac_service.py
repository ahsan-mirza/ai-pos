import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import (
    ALL_PERMISSIONS,
    PERMISSION_GROUPS,
    SYSTEM_ROLES,
    Permission,
)
from app.core.security import create_access_token, hash_password, hash_pin, verify_password, verify_pin
from app.models.audit_log import AuditLog
from app.models.base import utcnow
from app.models.role import Role, RolePermission
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.user import User
from app.schemas.auth import (
    PermissionGroupOut,
    PermissionOut,
    RoleCreate,
    RoleOut,
    RoleSummary,
    RoleUpdate,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import audit
from app.tenancy.context import current_tenant
from app.tenancy.scoping import DEFAULT_TENANT_ID, active_tenant_id, include_all_tenants

INVALID_CREDENTIALS = "Invalid email, username, or password."


# --- Serialization -------------------------------------------------------------------------------


def user_out(user: User, db: Session | None = None) -> UserOut:
    modules: list[str] = []
    permissions = set(user.permissions)
    if db is not None:
        from app.services.addon_access import addon_modules, effective_permissions

        modules = addon_modules(db, user)
        permissions = effective_permissions(db, user)
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        store_id=user.store_id,
        role=RoleSummary(id=user.role.id, name=user.role.name, max_discount_bps=user.role.max_discount_bps),
        permissions=sorted(permissions),
        has_pos_access=user.has_pos_access,
        has_portal_access=user.has_portal_access,
        can_sell_open_price=user.can_sell_open_price,
        has_password=user.hashed_password is not None,
        has_pin=user.hashed_pin is not None,
        locked_until=_aware(user.locked_until),
        last_login_at=_aware(user.last_login_at),
        created_at=user.created_at,
        updated_at=user.updated_at,
        addon_modules=modules,
    )


def role_out(db: Session, role: Role) -> RoleOut:
    count = db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)) or 0
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=sorted(role.permissions),
        user_count=count,
        created_at=role.created_at,
        updated_at=role.updated_at,
        max_discount_bps=role.max_discount_bps,
    )


def permission_catalog() -> list[PermissionGroupOut]:
    return [
        PermissionGroupOut(
            group=group,
            permissions=[PermissionOut(key=item.value, label=label) for item, label in items],
        )
        for group, items in PERMISSION_GROUPS.items()
    ]


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


# --- System roles and bootstrap ------------------------------------------------------------------


def holds_super_admin_role(role: Role) -> bool:
    return role.is_system and role.name == "Super Admin"


def holds_super_admin(user: User) -> bool:
    return holds_super_admin_role(user.role)


def _anywhere(statement):
    return statement.execution_options(include_all_tenants=True)


def _same(value: object, tenant_id: uuid.UUID) -> bool:
    return str(value) == str(tenant_id)


def _claim_role(db: Session, role: Role) -> None:
    """A migration stamps the seeded roles with the default store. The first real store takes them."""
    active = active_tenant_id()
    if active == DEFAULT_TENANT_ID or not _same(role.tenant_id, DEFAULT_TENANT_ID):
        return
    with include_all_tenants(db):
        rows = db.scalars(_anywhere(select(RolePermission).where(RolePermission.role_id == role.id))).all()
        role.tenant_id = active
        loaded = {row.permission for row in role.permission_rows}
        for row in rows:
            if _same(row.tenant_id, DEFAULT_TENANT_ID):
                row.tenant_id = active
            if row.permission not in loaded:
                role.permission_rows.append(row)
        db.flush()


def ensure_system_roles(db: Session) -> None:
    """Creates this store's system roles.

    Migrations seed the fixed ids once. The first store takes those rows. The next store in the same
    database gets its own copy, so the primary key is not inserted twice.
    """
    active = active_tenant_id()
    for spec in SYSTEM_ROLES:
        fixed_id = uuid.UUID(str(spec["id"]))
        name = str(spec["name"])
        permissions = set(spec["permissions"])  # type: ignore[arg-type]
        role = db.scalar(select(Role).where(Role.is_system.is_(True), Role.name == name))
        if role is None:
            existing = db.scalar(_anywhere(select(Role).where(Role.id == fixed_id)))
            placeholder = existing is not None and _same(existing.tenant_id, DEFAULT_TENANT_ID)
            if existing is not None and (placeholder or _same(existing.tenant_id, active)):
                role = existing
                _claim_role(db, role)
            else:
                role = Role(
                    id=fixed_id if existing is None else uuid.uuid5(active, name),
                    name=name,
                    description=str(spec["description"]),
                    is_system=True,
                    max_discount_bps=spec.get("max_discount_bps"),  # type: ignore[arg-type]
                )
                role.set_permissions(permissions)
                db.add(role)
        if name == "Super Admin":
            role.set_permissions(set(ALL_PERMISSIONS))
    db.flush()


def super_admin_role_id(db: Session) -> uuid.UUID:
    ensure_system_roles(db)
    role = db.scalar(select(Role).where(Role.is_system.is_(True), Role.name == "Super Admin"))
    if role is None:
        raise RuntimeError("Super Admin role is missing.")
    return role.id


def ensure_super_admin(
    db: Session,
    settings: Settings,
    *,
    username: str,
    email: str,
    full_name: str,
    password: str,
    pin: str | None,
) -> tuple[User, bool]:
    existing = db.scalar(select(User).where(User.username == username))
    if existing is not None:
        return existing, False
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        hashed_pin=hash_pin(pin, settings) if pin is not None else None,
        is_active=True,
        store_id=None,
        role_id=super_admin_role_id(db),
        has_pos_access=pin is not None,
        has_portal_access=True,
        failed_login_attempts=0,
        token_version=0,
    )
    db.add(user)
    db.flush()
    return user, True


# --- Authentication ------------------------------------------------------------------------------


def _locked(user: User) -> bool:
    locked_until = _aware(user.locked_until)
    return locked_until is not None and locked_until > datetime.now(UTC)


def _register_failure(db: Session, user: User, settings: Settings) -> None:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= settings.login_max_attempts:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lockout_minutes)
        user.failed_login_attempts = 0
    db.commit()


def authenticate(
    db: Session,
    settings: Settings,
    *,
    username: str,
    secret: str,
    method: Literal["password", "pin"],
) -> TokenResponse:
    normalized = username.strip().lower()
    if method == "password" and "@" in normalized:
        user = db.scalar(select(User).where(func.lower(User.email) == normalized))
    else:
        user = db.scalar(select(User).where(User.username == normalized))
    stored = None if user is None else (user.hashed_password if method == "password" else user.hashed_pin)
    valid = verify_password(secret, stored) if method == "password" else verify_pin(secret, stored, settings)
    if user is None:
        raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if _locked(user):
        raise ApiError(423, "account_locked", "Too many failed attempts. Try again later.")
    if not valid:
        _register_failure(db, user, settings)
        raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)

    scope: Literal["portal", "pos"] = "portal" if method == "password" else "pos"
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account is disabled.")
    if scope == "portal" and not (user.has_portal_access and Permission.PORTAL_ACCESS.value in user.permissions):
        raise ApiError(403, "portal_access_denied", "This account cannot sign in to the web portal.")
    if scope == "pos" and not (user.has_pos_access and Permission.POS_ACCESS.value in user.permissions):
        raise ApiError(403, "pos_access_denied", "This account cannot unlock a register.")

    return issue_session(db, settings, user, method)


def issue_session(db: Session, settings: Settings, user: User, method: str) -> TokenResponse:
    """Records a successful sign-in and returns the access token; `method` is password, pin or handoff."""
    scope: Literal["portal", "pos"] = "pos" if method == "pin" else "portal"
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit.log_login(db, user, method, client_device="desktop" if method == "pin" else None)
    db.commit()
    tenant = current_tenant()
    token, expires_in = create_access_token(
        subject=str(user.id),
        scope=scope,
        token_version=user.token_version,
        settings=settings,
        tenant_id=tenant.id if tenant is not None else None,
    )
    return TokenResponse(access_token=token, scope=scope, expires_in=expires_in, user=user_out(user, db))


# --- Authorization rules -------------------------------------------------------------------------


def _assert_can_grant(actor: Principal, permissions: set[str]) -> None:
    excess = sorted(permissions - actor.permissions)
    if excess:
        raise ApiError(
            403,
            "privilege_escalation",
            "You cannot grant permissions you do not hold.",
            details={"permissions": excess},
        )


def _assert_store_scope(actor: Principal, store_id: uuid.UUID | None) -> None:
    if actor.store_id is not None and store_id != actor.store_id:
        raise ApiError(403, "store_scope", "You can only manage users in your own store.")


def _assert_can_manage(actor: Principal, target: User) -> None:
    _assert_store_scope(actor, target.store_id)
    _assert_can_grant(actor, target.permissions)


def _active_super_admins(db: Session) -> int:
    super_ids = select(Role.id).where(Role.is_system.is_(True), Role.name == "Super Admin")
    statement = select(func.count()).select_from(User).where(User.role_id.in_(super_ids), User.is_active.is_(True))
    return db.scalar(statement) or 0


def _get_role(db: Session, role_id: uuid.UUID) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise ApiError(422, "unknown_role", "Role does not exist.")
    return role


def _check_store(db: Session, store_id: uuid.UUID | None) -> None:
    if store_id is not None and db.get(Store, store_id) is None:
        raise ApiError(422, "unknown_store", "Store does not exist.")


def _commit(db: Session, conflict_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", conflict_message) from exc


# --- Users ---------------------------------------------------------------------------------------


def get_user(db: Session, actor: Principal, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or (actor.store_id is not None and user.store_id != actor.store_id):
        raise ApiError(404, "not_found", "User was not found.")
    return user


def list_users(db: Session, actor: Principal) -> list[UserOut]:
    statement = select(User).order_by(User.full_name)
    if actor.store_id is not None:
        statement = statement.where(User.store_id == actor.store_id)
    return [user_out(user) for user in db.scalars(statement).unique().all()]


def create_user(db: Session, settings: Settings, actor: Principal, data: UserCreate) -> UserOut:
    role = _get_role(db, data.role_id)
    store_id = data.store_id if actor.store_id is None else (data.store_id or actor.store_id)
    _assert_store_scope(actor, store_id)
    _assert_can_grant(actor, role.permissions)
    if data.can_sell_open_price and Permission.POS_OPEN_PRICE.value not in role.permissions:
        _assert_can_grant(actor, {Permission.POS_OPEN_PRICE.value})
    _check_store(db, store_id)
    if db.scalar(select(User).where((User.username == data.username) | (User.email == data.email))) is not None:
        raise ApiError(409, "conflict", "Username or email is already in use.")
    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password) if data.password is not None else None,
        hashed_pin=hash_pin(data.pin, settings) if data.pin is not None else None,
        is_active=data.is_active,
        store_id=store_id,
        role_id=role.id,
        has_pos_access=data.has_pos_access,
        has_portal_access=data.has_portal_access,
        can_sell_open_price=data.can_sell_open_price,
        failed_login_attempts=0,
        token_version=0,
    )
    db.add(user)
    _commit(db, "Username or email is already in use.")
    db.refresh(user)
    return user_out(user)


def update_user(db: Session, actor: Principal, user_id: uuid.UUID, data: UserUpdate) -> UserOut:
    user = get_user(db, actor, user_id)
    _assert_can_manage(actor, user)
    is_self = actor.user is not None and actor.user.id == user.id
    was_super_admin = holds_super_admin(user) and user.is_active

    if data.role_id is not None and data.role_id != user.role_id:
        if is_self:
            raise ApiError(422, "self_change", "You cannot change your own role.")
        role = _get_role(db, data.role_id)
        _assert_can_grant(actor, role.permissions)
        user.role_id = role.id
        user.role = role
    if data.store_id is not None or data.clear_store:
        new_store = None if data.clear_store else data.store_id
        _assert_store_scope(actor, new_store)
        _check_store(db, new_store)
        user.store_id = new_store
    if data.is_active is not None and data.is_active != user.is_active:
        if is_self and not data.is_active:
            raise ApiError(422, "self_change", "You cannot disable your own account.")
        user.is_active = data.is_active
        user.token_version += 1
    if data.email is not None:
        user.email = data.email
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.has_portal_access is not None:
        if data.has_portal_access and user.hashed_password is None:
            raise ApiError(422, "password_required", "Set a password before enabling web portal access.")
        if is_self and not data.has_portal_access:
            raise ApiError(422, "self_change", "You cannot remove your own web portal access.")
        user.has_portal_access = data.has_portal_access
    if data.has_pos_access is not None:
        if data.has_pos_access and user.hashed_pin is None:
            raise ApiError(422, "pin_required", "Set a PIN before enabling POS access.")
        user.has_pos_access = data.has_pos_access
    if data.can_sell_open_price is not None and data.can_sell_open_price != user.can_sell_open_price:
        if data.can_sell_open_price and Permission.POS_OPEN_PRICE.value not in user.role.permissions:
            _assert_can_grant(actor, {Permission.POS_OPEN_PRICE.value})
        user.can_sell_open_price = data.can_sell_open_price
        user.token_version += 1

    still_super_admin = holds_super_admin(user) and user.is_active
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "Email is already in use.") from exc
    if was_super_admin and not still_super_admin and _active_super_admins(db) == 0:
        db.rollback()
        raise ApiError(422, "last_super_admin", "At least one active Super Admin must remain.")
    _commit(db, "Email is already in use.")
    db.refresh(user)
    from app.services.addon_access import invalidate_access_cache

    invalidate_access_cache(user.tenant_id)
    return user_out(user)


def set_password(db: Session, actor: Principal, user_id: uuid.UUID, password: str) -> UserOut:
    user = get_user(db, actor, user_id)
    _assert_can_manage(actor, user)
    user.hashed_password = hash_password(password)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)
    return user_out(user)


def set_pin(db: Session, settings: Settings, actor: Principal, user_id: uuid.UUID, pin: str) -> UserOut:
    user = get_user(db, actor, user_id)
    _assert_can_manage(actor, user)
    user.hashed_pin = hash_pin(pin, settings)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)
    return user_out(user)


def delete_user(db: Session, actor: Principal, user_id: uuid.UUID) -> None:
    user = get_user(db, actor, user_id)
    _assert_can_manage(actor, user)
    if actor.user is not None and actor.user.id == user.id:
        raise ApiError(422, "self_change", "You cannot delete your own account.")
    if holds_super_admin(user) and user.is_active and _active_super_admins(db) <= 1:
        raise ApiError(422, "last_super_admin", "At least one active Super Admin must remain.")
    if db.scalar(select(func.count()).select_from(Sale).where(Sale.cashier_id == user.id)):
        raise ApiError(409, "user_has_sales", "This user has recorded sales. Disable the account instead.")
    involved = (SaleReturn.cashier_id == user.id) | (SaleReturn.approved_by_id == user.id)
    if db.scalar(select(func.count()).select_from(SaleReturn).where(involved)):
        raise ApiError(409, "user_has_returns", "This user has handled returns. Disable the account instead.")
    authored = (AuditLog.user_id == user.id) | (AuditLog.approver_id == user.id)
    if db.scalar(select(func.count()).select_from(AuditLog).where(authored)):
        raise ApiError(
            409, "user_has_audit_history", "This user appears in the audit trail. Disable the account instead."
        )
    db.delete(user)
    db.commit()


# --- Roles ---------------------------------------------------------------------------------------


def list_roles(db: Session) -> list[RoleOut]:
    roles = db.scalars(select(Role).order_by(Role.is_system.desc(), Role.name)).all()
    return [role_out(db, role) for role in roles]


def create_role(db: Session, actor: Principal, data: RoleCreate) -> RoleOut:
    permissions = set(data.permissions)
    _assert_can_grant(actor, permissions)
    if db.scalar(select(Role).where(func.lower(Role.name) == data.name.lower())) is not None:
        raise ApiError(409, "conflict", "A role with this name already exists.")
    role = Role(
        name=data.name,
        description=data.description.strip(),
        is_system=False,
        max_discount_bps=data.max_discount_bps,
    )
    role.set_permissions(permissions)
    db.add(role)
    _commit(db, "A role with this name already exists.")
    db.refresh(role)
    return role_out(db, role)


def update_role(db: Session, actor: Principal, role_id: uuid.UUID, data: RoleUpdate) -> RoleOut:
    role = db.get(Role, role_id)
    if role is None:
        raise ApiError(404, "not_found", "Role was not found.")
    _assert_can_grant(actor, role.permissions)
    if holds_super_admin_role(role) and data.permissions is not None and set(data.permissions) != ALL_PERMISSIONS:
        raise ApiError(422, "system_role", "Super Admin always holds every permission.")
    if data.name is not None and data.name != role.name:
        if role.is_system:
            raise ApiError(422, "system_role", "System roles cannot be renamed.")
        clash = db.scalar(select(Role).where(func.lower(Role.name) == data.name.lower(), Role.id != role.id))
        if clash is not None:
            raise ApiError(409, "conflict", "A role with this name already exists.")
        role.name = data.name
    if data.description is not None:
        role.description = data.description.strip()
    if "max_discount_bps" in data.model_fields_set:
        role.max_discount_bps = data.max_discount_bps
    if data.permissions is not None:
        permissions = set(data.permissions)
        _assert_can_grant(actor, permissions)
        if actor.user is not None and actor.user.role_id == role.id and not permissions >= actor.permissions:
            raise ApiError(422, "self_change", "You cannot remove permissions from your own role.")
        role.set_permissions(permissions)
    _commit(db, "A role with this name already exists.")
    db.refresh(role)
    from app.services.addon_access import invalidate_access_cache

    invalidate_access_cache(role.tenant_id)
    return role_out(db, role)


def delete_role(db: Session, actor: Principal, role_id: uuid.UUID) -> None:
    role = db.get(Role, role_id)
    if role is None:
        raise ApiError(404, "not_found", "Role was not found.")
    if role.is_system:
        raise ApiError(422, "system_role", "System roles cannot be deleted.")
    _assert_can_grant(actor, role.permissions)
    if db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)):
        raise ApiError(409, "role_in_use", "Reassign this role's users before deleting it.")
    db.delete(role)
    db.commit()
