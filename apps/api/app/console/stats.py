"""Tenant size and activity, read from each store's own database and kept in the control database's tenant_stats.

Collected on demand from the console, after module changes and migrations, and by
`python -m app.tenancy.cli collect-stats` (schedule it daily)."""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.console.entitlements import tenant_session
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.device import Device
from app.models.product import Product
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.console import TenantStatsOut
from app.services.settings_service import load_settings, snapshot_of
from app.tenancy import registry
from app.tenancy.models import Tenant, TenantStats

logger = logging.getLogger("ai_pos.console.stats")
POSTED = ("completed", "partially_refunded", "refunded")


def stats_out(row: TenantStats | None) -> TenantStatsOut:
    if row is None:
        return TenantStatsOut()
    return TenantStatsOut(
        onboarded=row.onboarded,
        business_profile=row.business_profile,
        enabled_modules=list(row.enabled_modules or []),
        stores=row.stores,
        registers=row.registers,
        users=row.users,
        customers=row.customers,
        products=row.products,
        sales_30d_count=row.sales_30d_count,
        sales_30d_cents=row.sales_30d_cents,
        currency=row.currency,
        last_sale_at=row.last_sale_at,
        db_size_bytes=row.db_size_bytes,
        collected_at=row.collected_at,
    )


def _size(db: Session, url: str) -> int | None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "postgresql":
        return int(db.scalar(select(func.pg_database_size(func.current_database()))) or 0)
    if parsed.get_backend_name() == "sqlite" and parsed.database and os.path.exists(parsed.database):
        return os.path.getsize(parsed.database)
    return None


def _measure(db: Session, url: str) -> dict:
    snapshot = snapshot_of(load_settings(db))
    since = datetime.now(UTC) - timedelta(days=30)
    count, total = db.execute(
        select(func.count(Sale.id), func.coalesce(func.sum(Sale.total_cents), 0)).where(
            Sale.status.in_(POSTED), Sale.is_quote_proforma.is_(False), Sale.created_at >= since
        )
    ).one()
    return {
        "onboarded": snapshot.onboarded,
        "business_profile": snapshot.business_profile,
        "enabled_modules": [capability.value for capability in snapshot.capabilities],
        "stores": int(db.scalar(select(func.count(Store.id)).where(Store.is_active.is_(True))) or 0),
        "registers": int(db.scalar(select(func.count(Device.id)).where(Device.revoked_at.is_(None))) or 0),
        "users": int(db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0),
        "customers": int(db.scalar(select(func.count(Customer.id)).where(Customer.is_sample.is_(False))) or 0),
        "products": int(db.scalar(select(func.count(Product.id)).where(Product.is_sample.is_(False))) or 0),
        "sales_30d_count": int(count or 0),
        "sales_30d_cents": int(total or 0),
        "currency": snapshot.currency,
        "last_sale_at": db.scalar(
            select(func.max(Sale.created_at)).where(Sale.status.in_(POSTED), Sale.is_quote_proforma.is_(False))
        ),
        "db_size_bytes": _size(db, url),
    }


def collect(control: Session, tenant: Tenant, settings: Settings) -> TenantStatsOut:
    """Measures one tenant and stores the snapshot on the caller's control session (committed by the caller)."""
    ref = registry.ref_for(tenant, settings)
    with tenant_session(tenant, settings) as db:
        measured = _measure(db, ref.database_url)
    row = control.get(TenantStats, tenant.id)
    if row is None:
        row = TenantStats(tenant_id=tenant.id)
        control.add(row)
    for name, value in measured.items():
        setattr(row, name, value)
    row.collected_at = datetime.now(UTC)
    control.flush()
    return stats_out(row)


def collect_one(settings: Settings, tenant_id: uuid.UUID) -> TenantStatsOut:
    with registry.control_session(settings) as control:
        tenant = control.get(Tenant, tenant_id)
        if tenant is None:
            raise ApiError(404, "not_found", "Tenant was not found.")
        out = collect(control, tenant, settings)
        control.commit()
        return out


def collect_all(settings: Settings) -> tuple[int, int]:
    """(measured, failed). A store whose database is unreachable is logged and skipped."""
    done = failed = 0
    with registry.control_session(settings) as control:
        tenants = list(control.scalars(select(Tenant).order_by(Tenant.slug)))
        for tenant in tenants:
            try:
                collect(control, tenant, settings)
                control.commit()
                done += 1
            except Exception:
                control.rollback()
                failed += 1
                logger.warning("Could not measure tenant %s", tenant.slug, exc_info=True)
    return done, failed
