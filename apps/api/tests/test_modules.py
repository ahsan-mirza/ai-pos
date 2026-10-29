"""Add-on catalogue stays the registered capability list. Mapping an add-on does not enable a store."""

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import ensure_catalog, require_module_keys, update_addon
from app.console.modules import catalogue, explain, summary
from app.console.security import OperatorPrincipal
from app.core.capabilities import resolve
from app.core.errors import ApiError
from app.schemas.billing import AddonIn
from app.schemas.console import ModuleState
from app.tenancy.models import BillingAddon, ControlBase, Operator


def _db() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    session = Session(engine)
    ensure_catalog(session)
    session.commit()
    return session


def _operator(db: Session) -> OperatorPrincipal:
    row = Operator(email="ops@example.com", full_name="Ops", password_hash="x", totp_secret_enc="x", role="ADMIN")
    db.add(row)
    db.commit()
    return OperatorPrincipal(id=row.id, email=row.email, full_name=row.full_name, role=row.role, ip=None)


def test_catalogue_uses_registered_modules_only():
    db = _db()
    rows = catalogue(db)
    serial = next(row for row in rows if row.key == "serial_tracking")
    assert serial.available is True
    assert "electronics_wholesale" in serial.business_types
    assert "grocery" not in serial.business_types
    assert serial.addon_codes == ["serial_tracking"]
    warranty = next(row for row in rows if row.key == "warranty")
    assert warranty.addon_codes == []
    counted = summary(db)
    assert counted.catalogue_total == len(rows)
    assert counted.implemented == sum(1 for row in rows if row.available)
    assert counted.addon_mrr_fils == 0
    assert counted.pending_payments == 0


def test_unknown_module_and_missing_dependency_are_rejected():
    try:
        require_module_keys(["not_a_module"], with_dependencies=False)
    except ApiError as error:
        assert error.code == "unknown_module"
    else:
        raise AssertionError("unknown module was accepted")
    try:
        require_module_keys(["tables"], with_dependencies=True)
    except ApiError as error:
        assert error.code == "capability_dependencies"
    else:
        raise AssertionError("tables was accepted without open orders")


def test_mapping_an_addon_does_not_enable_the_module():
    db = _db()
    operator = _operator(db)
    addon = db.scalar(select(BillingAddon).where(BillingAddon.code == "extra_register"))
    assert addon is not None
    update_addon(
        db,
        operator,
        addon.id,
        AddonIn(
            name=addon.name,
            description=addon.description,
            monthly_fils=addon.monthly_fils,
            one_time_fils=addon.one_time_fils,
            refundable=addon.refundable,
            active=True,
            module_keys=["repairs", "warranty"],
            sort_order=addon.sort_order,
            reason="Sell repairs with this add-on",
        ),
    )
    mapped = next(row for row in catalogue(db) if row.key == "repairs")
    assert mapped.addon_codes == ["extra_register", "repairs"]
    resolved = resolve("grocery", None, None)
    assert "repairs" not in {capability.value for capability in resolved.enabled}


def test_a_verified_subscription_grants_its_modules_and_cancellation_removes_them():
    from datetime import UTC, datetime, timedelta

    from app.console.entitlements import subscription_module_keys
    from app.tenancy.models import BillingCycle, BillingPlan, Subscription, SubscriptionItem

    db = _db()
    addon = db.scalar(select(BillingAddon).where(BillingAddon.code == "extra_register"))
    assert addon is not None
    addon.module_keys = ["sales_orders", "gift_cards"]
    plan = db.scalar(select(BillingPlan).limit(1))
    cycle = db.scalar(select(BillingCycle).limit(1))
    assert plan is not None and cycle is not None
    subscription = Subscription(
        tenant_id=uuid.uuid4(),
        plan_id=plan.id,
        cycle_id=cycle.id,
        status="active",
        current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(subscription)
    db.flush()
    db.add(SubscriptionItem(subscription_id=subscription.id, addon_code="extra_register", quantity=1))
    db.commit()
    keys, until = subscription_module_keys(db, subscription.tenant_id)
    assert keys == ["sales_orders", "gift_cards"]
    assert until is not None and until > datetime.now(UTC)
    subscription.status = "canceled"
    db.commit()
    cleared, end = subscription_module_keys(db, subscription.tenant_id)
    assert cleared == [] and end is None


def test_entitlement_reason_names_the_override_and_the_mapping():
    lines = explain(
        [
            ModuleState(
                key="repairs",
                label="Repairs",
                available=True,
                enabled=False,
                selected=False,
                fits_type=True,
                override=None,
            )
        ],
        {"repairs": ["extra_register"]},
    )
    assert lines[0].enabled is False
    assert "does not turn it on" in lines[0].reason
    assert lines[0].addon_codes == ["extra_register"]
