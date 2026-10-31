"""Optional modules are catalog add-ons. A business type's starter modules stay on without a purchase."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import (
    _activate,
    addon_module_keys,
    ensure_catalog,
    ensure_module_addons,
    quote_addon,
)
from app.core import capabilities as catalog
from app.core.errors import ApiError
from app.tenancy.models import (
    BillingAddon,
    BillingCycle,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPlan,
    ControlBase,
    Subscription,
    SubscriptionItem,
    Tenant,
)


def _db() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    session = Session(engine)
    ensure_catalog(session)
    session.commit()
    return session


def test_seeding_module_addons_keeps_a_console_price_and_records_dependencies() -> None:
    db = _db()
    ensure_module_addons(db)
    tables = db.scalar(select(BillingAddon).where(BillingAddon.code == "tables"))
    assert tables is not None
    assert tables.module_keys == addon_module_keys(catalog.Capability.TABLES)
    assert "open_orders" in tables.module_keys
    assert tables.monthly_fils == 0
    tables.monthly_fils = 2_500
    tables.name = "Floor plan"
    tables.module_keys = ["tables"]
    db.commit()
    ensure_module_addons(db)
    db.expire_all()
    kept = db.scalar(select(BillingAddon).where(BillingAddon.code == "tables"))
    assert kept is not None
    assert kept.monthly_fils == 2_500
    assert kept.name == "Floor plan"
    assert kept.module_keys == ["tables"]


def test_an_unpriced_add_on_and_the_wrong_business_type_are_refused(monkeypatch) -> None:
    db = _db()
    ensure_module_addons(db)
    tenant = Tenant(slug="demo", name="Demo", database_url_encrypted="x")
    db.add(tenant)
    db.commit()
    try:
        quote_addon(db, SimpleNamespace(), tenant, "sales_orders")  # type: ignore[arg-type]
    except ApiError as error:
        assert error.code == "price_not_set"
    else:
        raise AssertionError("a zero-price add-on was quoted")

    sales = db.scalar(select(BillingAddon).where(BillingAddon.code == "sales_orders"))
    assert sales is not None
    sales.monthly_fils = 1_000
    db.commit()
    try:
        quote_addon(db, SimpleNamespace(), tenant, "sales_orders")  # type: ignore[arg-type]
    except ApiError as error:
        assert error.code == "no_subscription"
    else:
        raise AssertionError("an add-on was quoted without a package")

    plan = db.scalar(select(BillingPlan).limit(1))
    cycle = db.scalar(select(BillingCycle).limit(1))
    assert plan is not None and cycle is not None
    db.add(Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id, status="active"))
    db.commit()
    monkeypatch.setattr("app.console.billing._business_profile", lambda _settings, _tenant: "electronics_wholesale")
    try:
        quote_addon(db, SimpleNamespace(), tenant, "tables")  # type: ignore[arg-type]
    except ApiError as error:
        assert error.code == "price_not_set"
    tables = db.scalar(select(BillingAddon).where(BillingAddon.code == "tables"))
    assert tables is not None
    tables.monthly_fils = 1_000
    db.commit()
    try:
        quote_addon(db, SimpleNamespace(), tenant, "tables")  # type: ignore[arg-type]
    except ApiError as error:
        assert error.code == "module_not_optional"
    else:
        raise AssertionError("tables was offered to an electronics store")


def test_paying_for_tables_keeps_the_hardware_item_and_the_current_period() -> None:
    db = _db()
    tenant = Tenant(slug="cafe", name="Cafe", database_url_encrypted="x")
    db.add(tenant)
    db.flush()
    plan = db.scalar(select(BillingPlan).limit(1))
    cycle = db.scalar(select(BillingCycle).limit(1))
    assert plan is not None and cycle is not None
    end = datetime.now(UTC) + timedelta(days=12)
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        cycle_id=cycle.id,
        status="trialing",
        current_period_end=end,
    )
    db.add(subscription)
    db.flush()
    db.add(SubscriptionItem(subscription_id=subscription.id, addon_code="hardware_lease", quantity=1))
    invoice = BillingInvoice(
        tenant_id=tenant.id,
        status="pending",
        plan_code=plan.code,
        cycle_code=cycle.code,
        total_fils=1_000,
        confirm_name=tenant.name,
    )
    db.add(invoice)
    db.flush()
    db.add(
        BillingInvoiceLine(
            invoice_id=invoice.id,
            code="tables",
            label="Tables & floor plan",
            quantity=1,
            unit_fils=1_000,
            amount_fils=1_000,
            recurring=True,
        )
    )
    db.commit()
    _activate(db, tenant, invoice)
    db.commit()
    codes = {
        item.addon_code
        for item in db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id))
    }
    assert codes == {"hardware_lease", "tables"}
    assert subscription.status == "trialing"
    stored_end = subscription.current_period_end
    assert stored_end is not None
    assert stored_end.replace(tzinfo=None) == end.replace(tzinfo=None)


def test_starter_modules_stay_free_and_a_paid_optional_module_turns_on(monkeypatch) -> None:
    from app.services import settings_service

    optional = {
        capability.value
        for profile in catalog.PROFILES
        for capability in catalog.catalogue(profile).optional
    }
    monkeypatch.setattr(settings_service, "commercial_module_keys", lambda: optional)
    electronics = [capability.value for capability in catalog.PROFILES["electronics_wholesale"]]
    settings_service._refuse_unpaid(
        "electronics_wholesale",
        electronics,
        SimpleNamespace(capabilities=None),
        [],
    )
    assert catalog.Capability.SERIAL_TRACKING in catalog.resolve("electronics_wholesale", None).enabled

    fashion = [capability.value for capability in catalog.PROFILES["retail_fashion"]]
    stored = SimpleNamespace(capabilities=fashion)
    try:
        settings_service._refuse_unpaid("retail_fashion", [*fashion, "serial_tracking"], stored, [])
    except ApiError as error:
        assert error.code == "payment_required"
    else:
        raise AssertionError("fashion serial tracking was switched on without payment")
    settings_service._refuse_unpaid("retail_fashion", [*fashion, "serial_tracking"], stored, ["serial_tracking"])
    paid = catalog.resolve("retail_fashion", fashion, None, ["serial_tracking"])
    assert catalog.Capability.SERIAL_TRACKING in paid.enabled


def test_marketplace_uses_the_subscription_and_hides_unpublished_rows(monkeypatch) -> None:
    from app.console.addon_listing import marketplace_for, normalize_listing

    db = _db()
    ensure_module_addons(db)
    tenant = Tenant(slug="demo", name="Demo", database_url_encrypted="x")
    db.add(tenant)
    db.commit()
    monkeypatch.setattr("app.console.billing._business_profile", lambda _settings, _tenant: "electronics_wholesale")
    hidden = db.scalar(select(BillingAddon).where(BillingAddon.code == "uae_einvoicing"))
    assert hidden is not None
    hidden.active = False
    db.commit()
    found = marketplace_for(db, SimpleNamespace(), tenant)
    states = {item.addon.code: item.state for item in found.items}
    assert states["serial_tracking"] == "included"
    assert "uae_einvoicing" not in states
    assert states["hardware_lease"] == "available"
    cleaned = normalize_listing(
        {"overview": "<b>Hello</b>", "image_url": "javascript:alert(1)", "documentation_url": "https://example.com/a"}
    )
    assert "<" not in cleaned["overview"]
    assert cleaned["image_url"] == ""
    assert cleaned["documentation_url"] == "https://example.com/a"


def test_a_price_change_is_remembered_and_a_second_checkout_reuses_the_invoice(monkeypatch) -> None:
    from app.console.billing import create_addon_checkout, update_addon
    from app.console.security import OperatorPrincipal
    from app.schemas.billing import AddonIn

    db = _db()
    ensure_module_addons(db)
    tenant = Tenant(slug="shop", name="Shop", database_url_encrypted="x")
    db.add(tenant)
    db.flush()
    plan = db.scalar(select(BillingPlan).limit(1))
    cycle = db.scalar(select(BillingCycle).limit(1))
    assert plan is not None and cycle is not None
    db.add(Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id, status="active"))
    addon = db.scalar(select(BillingAddon).where(BillingAddon.code == "uae_einvoicing"))
    assert addon is not None
    operator = OperatorPrincipal(id=addon.id, email="it@example.com", full_name="IT", role="ADMIN", ip=None)
    update_addon(
        db,
        operator,
        addon.id,
        AddonIn(
            name=addon.name,
            description=addon.description,
            monthly_fils=2_000,
            one_time_fils=0,
            refundable=False,
            active=True,
            module_keys=list(addon.module_keys or []),
            sort_order=addon.sort_order,
            reason="Set the monthly price",
        ),
    )
    db.expire_all()
    priced = db.scalar(select(BillingAddon).where(BillingAddon.code == "uae_einvoicing"))
    assert priced is not None
    assert priced.monthly_fils == 2_000
    assert priced.price_history[-1]["monthly_fils"] == 0
    monkeypatch.setattr("app.console.billing._business_profile", lambda _settings, _tenant: "electronics_wholesale")
    monkeypatch.setattr("app.console.transfers.active_bank_snapshot", lambda _db: {"holder": "Axiz"})
    first = create_addon_checkout(db, SimpleNamespace(), tenant, tenant.id, "uae_einvoicing")
    second = create_addon_checkout(db, SimpleNamespace(), tenant, tenant.id, "uae_einvoicing")
    assert first.checkout_id == second.checkout_id
    invoices = list(db.scalars(select(BillingInvoice).where(BillingInvoice.tenant_id == tenant.id)))
    assert len(invoices) == 1
    found = __import__("app.console.addon_listing", fromlist=["marketplace_for"]).marketplace_for(
        db, SimpleNamespace(), tenant
    )
    state = next(item for item in found.items if item.addon.code == "uae_einvoicing")
    assert state.state == "pending_payment"
    assert state.invoice_id == first.checkout_id
