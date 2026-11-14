"""Read-only resource counts for the subscription overview.

The counts match the checks that block a new row (`assert_room`):

- Branches: every `stores` row, including inactive branches and warehouses. The branch cap uses
  `count_of(Store)` and does not exclude those rows.
- Registers: `devices` whose `revoked_at` is null. Hardware catalog items, activation codes, and
  revoked registers are not registers.
- Staff: `users` with `is_active` true. Disabled users are excluded. Console operators live in the
  control database and are not tenant users.
- Products: every `products` row, including inactive rows and variants. Stock rows are not products.
- Customers: every `customers` row, including inactive and sample accounts. There is no archive flag.

Each table is tenant-scoped by the request session. A null cap in `effective_limits` means the plan
does not enforce that resource (unlimited). A missing key, or no resolvable plan, is unconfigured.
It is not treated as unlimited and it is not treated as zero.

Near-limit is a presentation threshold of 80 percent. It does not change `assert_room`, which still
blocks only when usage has reached the cap.

The five counts share one tenant transaction. The plan caps are read from the control database in a
separate session, so a plan edit that lands between the two reads can pair a new cap with the
previous counts. No usage row is written.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.billing import UsageMetricOut, UsageOut

RESOURCES = ("branches", "registers", "staff", "products", "customers")
LABELS = {
    "branches": "Branches",
    "registers": "Registers",
    "staff": "Staff",
    "products": "Products",
    "customers": "Customers",
}
# Presentation only. Entitlement blocking stays at 100 percent inside assert_room.
NEAR_LIMIT_RATIO = 0.8


def count_resources(db: Session) -> dict[str, int]:
    """Five aggregate counts. Rows are not loaded."""
    from app.models.customer import Customer
    from app.models.device import Device
    from app.models.product import Product
    from app.models.store import Store
    from app.models.user import User

    def total(*criteria: object) -> int:
        model = criteria[0]
        filters = criteria[1:]
        statement = select(func.count()).select_from(model)
        if filters:
            statement = statement.where(*filters)  # type: ignore[arg-type]
        return int(db.scalar(statement) or 0)

    return {
        "branches": total(Store),
        "registers": total(Device, Device.revoked_at.is_(None)),
        "staff": total(User, User.is_active.is_(True)),
        "products": total(Product),
        "customers": total(Customer),
    }


def _finite(used: int, limit: int) -> UsageMetricOut:
    remaining = max(0, limit - used)
    exceeded = used > limit
    if limit <= 0 or used >= limit:
        status = "limit_reached"
        percentage = 100
    elif used / limit >= NEAR_LIMIT_RATIO:
        status = "near_limit"
        percentage = min(100, round(used * 100 / limit))
    else:
        status = "available"
        percentage = 0 if limit == 0 else min(100, round(used * 100 / limit))
    return UsageMetricOut(
        label=LABELS["branches"],
        used=used,
        limit=limit,
        available=remaining,
        percentage=percentage,
        status=status,  # type: ignore[arg-type]
        usage_available=True,
        exceeded=exceeded,
    )


def present_metric(key: str, used: int | None, limits: dict | None) -> UsageMetricOut:
    label = LABELS[key]
    if used is None:
        return UsageMetricOut(label=label, status="unavailable", usage_available=False)
    if limits is None or key not in limits:
        return UsageMetricOut(label=label, used=used, status="unconfigured", usage_available=True)
    raw = limits.get(key)
    if raw is None:
        return UsageMetricOut(label=label, used=used, status="unlimited", usage_available=True)
    metric = _finite(used, int(raw))
    return metric.model_copy(update={"label": label})


def present_usage(plan_code: str | None, limits: dict | None, counts: dict[str, int] | None) -> UsageOut:
    metrics = {
        key: present_metric(key, None if counts is None else counts.get(key), limits)
        for key in RESOURCES
    }
    return UsageOut(plan_code=plan_code, measured_at=datetime.now(UTC), metrics=metrics)


def usage_for(control: Session, tenant_id: uuid.UUID, store: Session) -> UsageOut:
    """Reads caps and counts. Rolls the tenant session back so a later flush cannot persist anything."""
    from app.console.promotional_trial import effective_limits
    from app.tenancy.models import BillingPlan, Subscription

    subscription = control.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    plan = control.get(BillingPlan, subscription.plan_id) if subscription is not None else None
    limits = effective_limits(control, tenant_id)
    if store.new or store.dirty or store.deleted:
        store.rollback()
    counts = count_resources(store)
    if store.new or store.dirty or store.deleted:
        store.rollback()
        raise RuntimeError("Usage measurement changed tenant rows.")
    store.rollback()
    return present_usage(plan.code if plan is not None else None, limits, counts)
