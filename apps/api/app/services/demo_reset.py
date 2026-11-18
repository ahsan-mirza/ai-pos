"""Reset a production demo tenant back to its seeded baseline.

The control database and the operational database use different engines and
sessions. Nothing here pretends those two commits are one transaction. The
control row carries the operation id and phase. A crash leaves demo_status at
resetting or reset_failed, and recover_interrupted_reset resumes from that row.

Operational deletes are Core statements with an explicit tenant_id predicate
inside use_tenant. They never use include_all_tenants. Domain services are not
used for the wipe: no service deletes a whole tenant's history, and several
ledgers are append-only through their own API. audit_logs stay, because
Postgres rejects DELETE on that table. users, roles, role_permissions,
business_settings, and stores stay so the Super Admin, the Demo Explorer, the
profile, and the branch survive. Catalog and history seeding then rebuilds the
baseline. Provisioning is not called, so the Free subscription is left as it is.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Base
from app.models.product import Product
from app.models.role import Role
from app.models.sale import Sale
from app.models.user import User
from app.services import audit, demo_validate
from app.services.demo_catalog import (
    EXPLORER_USERNAME,
    DemoSeedError,
    _ref,
    _session,
    demo_tenants,
    load_spec,
    seed_catalog,
    tenant_spec,
)
from app.services.demo_history import seed_history
from app.tenancy import registry
from app.tenancy.context import use_tenant
from app.tenancy.models import Tenant

logger = logging.getLogger("ai_pos.demo_reset")

# Configuration and the two human accounts. audit_logs cannot be deleted on Postgres.
_PRESERVE = frozenset({"users", "roles", "role_permissions", "business_settings", "stores", "audit_logs"})
_STARTABLE = frozenset({"active", "reset_failed"})
_RESUMABLE = frozenset({"resetting", "reset_failed"})


class DemoResetError(RuntimeError):
    """The reset was refused, or it stopped before the tenant was marked active again."""


@dataclass(frozen=True)
class ResetLock:
    operation_id: uuid.UUID
    code: str
    slug: str
    tenant_id: uuid.UUID


def _spec(code: str) -> dict:
    try:
        return tenant_spec(code)
    except DemoSeedError as exc:
        raise DemoResetError(str(exc)) from exc


def _codes(codes: list[str] | None) -> list[str]:
    known = [spec["code"] for spec in demo_tenants()]
    if codes is None:
        return known
    unknown = [code for code in codes if code not in known]
    if unknown:
        raise DemoResetError(f"Unknown demo business code: {', '.join(unknown)}.")
    return list(codes)


def validate_reset_eligibility(tenant: Tenant, spec: dict, *, recover: bool) -> None:
    """Refuse anything that is not this catalog's demo tenant in a resettable state."""
    if not tenant.is_demo:
        raise DemoResetError(f"{tenant.slug} is not a demo tenant.")
    if tenant.demo_business_type != spec["code"]:
        raise DemoResetError(f"{tenant.slug} is not the {spec['code']} demo.")
    version = int(load_spec()["version"])
    if tenant.demo_seed_version is not None and int(tenant.demo_seed_version) > version:
        raise DemoResetError(f"{tenant.slug} was seeded with catalog version {tenant.demo_seed_version}.")
    status = tenant.demo_status or "active"
    if status == "disabled":
        raise DemoResetError(f"{tenant.slug} is deactivated. Reactivate it before resetting.")
    allowed = _RESUMABLE if recover else _STARTABLE
    if status not in allowed:
        raise DemoResetError(f"{tenant.slug} is {status}. Recovery can resume a reset already in progress.")


def _postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _load_for_update(db: Session, slugs: list[str]) -> list[Tenant]:
    statement = select(Tenant).where(Tenant.slug.in_(slugs)).order_by(Tenant.slug)
    if _postgres(db):
        statement = statement.with_for_update()
    rows = list(db.scalars(statement).all())
    found = {row.slug for row in rows}
    missing = [slug for slug in slugs if slug not in found]
    if missing:
        raise DemoResetError(f"Unknown demo tenant: {', '.join(missing)}.")
    return rows


def acquire_reset_lock(settings: Settings, codes: list[str], *, recover: bool = False) -> list[ResetLock]:
    """Mark each tenant resetting under one operation id. The row lock lasts only for this commit."""
    specs = {spec["code"]: spec for spec in demo_tenants() if spec["code"] in codes}
    slugs = [specs[code]["slug"] for code in codes]
    operation_id = uuid.uuid4()
    locks: list[ResetLock] = []
    with registry.control_session(settings) as db:
        rows = _load_for_update(db, slugs)
        by_slug = {row.slug: row for row in rows}
        for code in codes:
            validate_reset_eligibility(by_slug[specs[code]["slug"]], specs[code], recover=recover)
        allowed = ("resetting", "reset_failed") if recover else ("active", "reset_failed")
        for code in codes:
            row = by_slug[specs[code]["slug"]]
            status_match = Tenant.demo_status.in_(allowed)
            if not recover:
                status_match = or_(status_match, Tenant.demo_status.is_(None))
            result = db.execute(
                update(Tenant)
                .where(Tenant.id == row.id, status_match)
                .values(
                    demo_status="resetting",
                    demo_reset_operation_id=operation_id,
                    demo_reset_phase="queued",
                )
            )
            if result.rowcount != 1:
                raise DemoResetError(f"{row.slug} is already being reset.")
            locks.append(ResetLock(operation_id, code, row.slug, row.id))
        db.commit()
    logger.info("demo reset %s acquired for %s", operation_id, ", ".join(codes))
    return locks


def release_reset_lock(settings: Settings, lock: ResetLock, *, failed: bool) -> None:
    """Finish or abandon one operation. The control update is its own commit."""
    with registry.control_session(settings) as db:
        statement = update(Tenant).where(
            Tenant.id == lock.tenant_id,
            Tenant.demo_reset_operation_id == lock.operation_id,
        )
        if failed:
            statement = statement.values(demo_status="reset_failed", demo_reset_phase="failed")
        else:
            statement = statement.values(
                demo_status="active",
                demo_reset_phase=None,
                demo_reset_operation_id=None,
                demo_last_reset_at=datetime.now(UTC),
                demo_seed_version=int(load_spec()["version"]),
            )
        result = db.execute(statement)
        if result.rowcount != 1:
            raise DemoResetError(f"Reset {lock.operation_id} no longer owns {lock.slug}.")
        db.commit()
    logger.info("demo reset %s %s for %s", lock.operation_id, "failed" if failed else "finished", lock.slug)


def _phase(settings: Settings, lock: ResetLock, phase: str) -> None:
    with registry.control_session(settings) as db:
        result = db.execute(
            update(Tenant)
            .where(Tenant.id == lock.tenant_id, Tenant.demo_reset_operation_id == lock.operation_id)
            .values(demo_reset_phase=phase)
        )
        if result.rowcount != 1:
            raise DemoResetError(f"Reset {lock.operation_id} no longer owns {lock.slug}.")
        db.commit()


def _detached(settings: Settings, slug: str) -> Tenant:
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if row is None:
            raise DemoResetError(f"Unknown demo tenant: {slug}.")
        db.expunge(row)
        return row


def invalidate_demo_sessions(db: Session) -> int:
    """Bump the Demo Explorer token version. The Super Admin session is left as it is."""
    user = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
    if user is None:
        raise DemoResetError("The Demo Explorer user is missing.")
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    return int(user.token_version)


def wipe_operational_data(db: Session, tenant_id: uuid.UUID) -> int:
    """Delete this tenant's operational rows, children first, with an explicit tenant predicate.

    A savepoint per table lets a foreign key decide the order when the metadata sort is not enough.
    """
    import app.models  # noqa: F401  (register every operational table)

    targets = [
        table
        for table in reversed(list(Base.metadata.sorted_tables))
        if "tenant_id" in table.c and table.name not in _PRESERVE
    ]
    if any(table.name == "tenants" for table in targets):
        raise DemoResetError("The control-plane tenant table was included in the operational wipe.")
    remaining = list(targets)
    deleted = 0
    for _ in range(len(remaining) + 1):
        if not remaining:
            return deleted
        progressed = False
        for table in list(remaining):
            try:
                with db.begin_nested():
                    result = db.execute(delete(table).where(table.c.tenant_id == tenant_id))
                deleted += int(result.rowcount or 0)
                remaining.remove(table)
                progressed = True
            except IntegrityError:
                continue
        if not progressed:
            blocked = ", ".join(table.name for table in remaining)
            raise DemoResetError(f"Tenant-scoped delete stopped at: {blocked}.")
    return deleted


def _audit(db: Session, lock: ResetLock, report: dict) -> None:
    owner = db.scalar(select(User).join(Role).where(Role.name == "Super Admin", Role.is_system.is_(True)))
    audit.record(
        db,
        action_type="UPDATE",
        action="demo.reset",
        target_entity="Tenant",
        target_entity_id=lock.tenant_id,
        user=owner,
        client_device="system",
        details={"operation_id": str(lock.operation_id), "code": lock.code, "ok": report["ok"]},
    )
    db.commit()


def restore_demo_baseline(settings: Settings, lock: ResetLock) -> dict:
    """Wipe, seed, and validate. Each step is its own operational commit."""
    spec = _spec(lock.code)
    tenant = _detached(settings, lock.slug)
    ref = _ref(tenant, settings)
    _phase(settings, lock, "invalidate")
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            invalidate_demo_sessions(db)
            from app.services.demo_pos import revoke_demo_registers

            revoke_demo_registers(db)
    finally:
        db.close()
    _phase(settings, lock, "wipe")
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            wipe_operational_data(db, lock.tenant_id)
            db.commit()
    finally:
        db.close()
    _phase(settings, lock, "seed")
    seed_catalog(settings, spec, tenant)
    seed_history(settings, spec, tenant)
    _phase(settings, lock, "validate")
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            report = demo_validate.validate_demo(db, spec)
            if not report["ok"]:
                failed = [check["name"] for check in report["checks"] if not check["ok"]]
                raise DemoResetError(f"{lock.code} failed validation: {', '.join(failed)}.")
            _audit(db, lock, report)
    finally:
        db.close()
    return report


def _execute(settings: Settings, lock: ResetLock) -> dict:
    try:
        report = restore_demo_baseline(settings, lock)
    except Exception:
        release_reset_lock(settings, lock, failed=True)
        logger.exception("demo reset %s failed for %s", lock.operation_id, lock.slug)
        raise
    release_reset_lock(settings, lock, failed=False)
    return report


def _summary(settings: Settings, spec: dict) -> dict:
    tenant = _detached(settings, spec["slug"])
    ref = _ref(tenant, settings)
    db = _session(settings, tenant)
    try:
        with use_tenant(ref):
            sales = int(db.scalar(select(func.count()).select_from(Sale)) or 0)
            products = int(db.scalar(select(func.count()).select_from(Product)) or 0)
    finally:
        db.close()
    return {
        "code": spec["code"],
        "slug": spec["slug"],
        "demo_status": tenant.demo_status,
        "sales": sales,
        "products": products,
        "dry_run": True,
    }


def validate_demo_data(settings: Settings, codes: list[str] | None = None) -> list[dict]:
    """Read-only reconciliation for one configured demo, or all four."""
    reports = []
    for code in _codes(codes):
        spec = _spec(code)
        tenant = _detached(settings, spec["slug"])
        if not tenant.is_demo or tenant.demo_business_type != code:
            raise DemoResetError(f"{spec['slug']} is not a demo tenant.")
        db = _session(settings, tenant)
        try:
            with use_tenant(_ref(tenant, settings)):
                reports.append(demo_validate.validate_demo(db, spec))
        finally:
            db.close()
    return reports


def reset_demo_tenant(settings: Settings, code: str, *, dry_run: bool = False) -> dict:
    spec = _spec(code)
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
        if row is None:
            raise DemoResetError(f"Unknown demo tenant: {spec['slug']}.")
        validate_reset_eligibility(row, spec, recover=False)
    if dry_run:
        return _summary(settings, spec)
    lock = acquire_reset_lock(settings, [code])[0]
    report = _execute(settings, lock)
    return {"code": code, "slug": spec["slug"], "operation_id": str(lock.operation_id), "ok": report["ok"]}


def reset_all_demo_tenants(settings: Settings, *, dry_run: bool = False) -> list[dict]:
    codes = _codes(None)
    if dry_run:
        return [_summary(settings, _spec(code)) for code in codes]
    locks = acquire_reset_lock(settings, codes)
    finished: list[dict] = []
    for index, lock in enumerate(locks):
        try:
            report = _execute(settings, lock)
        except Exception:
            _release_queued(settings, locks[index + 1 :])
            raise
        finished.append(
            {"code": lock.code, "slug": lock.slug, "operation_id": str(lock.operation_id), "ok": report["ok"]}
        )
    return finished


def _release_queued(settings: Settings, locks: list[ResetLock]) -> None:
    """Return tenants that have not been wiped to active. The failed tenant stays reset_failed."""
    if not locks:
        return
    with registry.control_session(settings) as db:
        for lock in locks:
            db.execute(
                update(Tenant)
                .where(
                    Tenant.id == lock.tenant_id,
                    Tenant.demo_reset_operation_id == lock.operation_id,
                    Tenant.demo_reset_phase == "queued",
                )
                .values(demo_status="active", demo_reset_phase=None, demo_reset_operation_id=None)
            )
        db.commit()


def recover_interrupted_reset(settings: Settings, code: str | None = None) -> list[dict]:
    """Resume every demo left in resetting or reset_failed. An active tenant is left alone."""
    codes = _codes([code] if code else None)
    recovered: list[dict] = []
    for business in codes:
        spec = _spec(business)
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == spec["slug"]))
            if row is None:
                raise DemoResetError(f"Unknown demo tenant: {spec['slug']}.")
            if not row.is_demo or row.demo_business_type != business:
                raise DemoResetError(f"{spec['slug']} is not a demo tenant.")
            status = row.demo_status or "active"
            if status not in _RESUMABLE:
                continue
        locks = acquire_reset_lock(settings, [business], recover=True)
        report = _execute(settings, locks[0])
        recovered.append(
            {"code": business, "slug": spec["slug"], "operation_id": str(locks[0].operation_id), "ok": report["ok"]}
        )
    return recovered


def deactivate_demo_account(settings: Settings, code: str, *, operator_id: uuid.UUID | None = None) -> dict:
    """Disable access and revoke the explorer session. Operational rows stay.

    The token is revoked before the control row is marked disabled. A crash between the two
    commits leaves the session dead, and running the command again finishes the status change.
    """
    spec = _spec(code)
    with registry.control_session(settings) as db:
        row = _load_for_update(db, [spec["slug"]])[0]
        if not row.is_demo or row.demo_business_type != code:
            raise DemoResetError(f"{spec['slug']} is not a demo tenant.")
        if (row.demo_status or "active") == "resetting":
            raise DemoResetError(f"{spec['slug']} is being reset.")
        already = row.demo_status == "disabled" and not row.demo_access_enabled
        tenant_id = row.id
        db.rollback()
    if already:
        return {"code": code, "slug": spec["slug"], "demo_status": "disabled", "token_version": None}
    tenant = _detached(settings, spec["slug"])
    db = _session(settings, tenant)
    try:
        with use_tenant(_ref(tenant, settings)):
            version = invalidate_demo_sessions(db)
            from app.services.demo_pos import revoke_demo_registers

            revoke_demo_registers(db)
            owner = db.scalar(select(User).join(Role).where(Role.name == "Super Admin", Role.is_system.is_(True)))
            audit.record(
                db,
                action_type="UPDATE",
                action="demo.deactivate",
                target_entity="Tenant",
                target_entity_id=tenant_id,
                user=owner,
                client_device="system",
                details={
                    "operator_id": str(operator_id) if operator_id else "cli",
                    "at": datetime.now(UTC).isoformat(),
                },
            )
            db.commit()
    finally:
        db.close()
    with registry.control_session(settings) as db:
        row = _load_for_update(db, [spec["slug"]])[0]
        if (row.demo_status or "active") == "resetting":
            raise DemoResetError(f"{spec['slug']} is being reset.")
        row.demo_status = "disabled"
        row.demo_access_enabled = False
        db.commit()
    return {"code": code, "slug": spec["slug"], "demo_status": "disabled", "token_version": version}


def reactivate_demo_account(settings: Settings, code: str) -> dict:
    """Return a deactivated demo to active. Public access stays off until a later stage enables it."""
    spec = _spec(code)
    with registry.control_session(settings) as db:
        row = _load_for_update(db, [spec["slug"]])[0]
        if not row.is_demo or row.demo_business_type != code:
            raise DemoResetError(f"{spec['slug']} is not a demo tenant.")
        if row.demo_status != "disabled":
            raise DemoResetError(f"{spec['slug']} is {row.demo_status or 'active'}, not deactivated.")
        row.demo_status = "active"
        row.demo_access_enabled = False
        db.commit()
    return {"code": code, "slug": spec["slug"], "demo_status": "active", "demo_access_enabled": False}
