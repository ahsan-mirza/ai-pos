"""Commercial payments stay unpaid until a person or a real provider verifies them."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.console.billing import ensure_catalog, ensure_module_addons
from app.console.commercial_payments import (
    UnconfiguredCardProvider,
    mark_invoice_submitted,
    mark_invoice_succeeded,
    method_availability,
    payment_for_tenant,
    record_cash,
    set_enabled,
    start_plugin_payment,
)
from app.console.security import OperatorPrincipal
from app.core.errors import ApiError
from app.schemas.billing import AddonIn
from app.tenancy.models import (
    BillingAddon,
    BillingCycle,
    BillingInvoice,
    BillingPlan,
    CommercialPayment,
    CommercialPaymentEvent,
    ControlBase,
    PlatformPaymentMethod,
    Subscription,
    SubscriptionItem,
    Tenant,
)


def _method(
    code: str, category: str, enabled: bool, purposes: list[str], instructions: str = ""
) -> PlatformPaymentMethod:
    return PlatformPaymentMethod(
        code=code,
        display_name=code,
        category=category,
        is_enabled=enabled,
        purposes=purposes,
        instructions=instructions,
    )


def test_card_stays_unavailable_even_when_the_row_is_enabled() -> None:
    row = _method("card", "CARD", True, ["PLUGIN_PURCHASE"], "No card provider is configured.")
    available, reason = method_availability(row, bank_ready=True, purpose="PLUGIN_PURCHASE")
    assert available is False
    assert reason == "No card provider is configured."


def test_cash_and_bank_follow_configuration() -> None:
    cash = _method("cash", "CASH", False, ["PLUGIN_PURCHASE"])
    assert method_availability(cash, bank_ready=True, purpose="PLUGIN_PURCHASE")[0] is False
    cash.is_enabled = True
    assert method_availability(cash, bank_ready=True, purpose="SUBSCRIPTION")[0] is False
    assert method_availability(cash, bank_ready=True, purpose="PLUGIN_PURCHASE")[0] is True
    bank = _method("bank_transfer", "BANK_TRANSFER", True, ["PLUGIN_PURCHASE"])
    assert method_availability(bank, bank_ready=False, purpose="PLUGIN_PURCHASE")[0] is False
    assert method_availability(bank, bank_ready=True, purpose="PLUGIN_PURCHASE")[0] is True


def test_unconfigured_card_provider_never_succeeds() -> None:
    payment = CommercialPayment(
        tenant_id=uuid.uuid4(),
        method_code="card",
        purpose_type="PLUGIN_PURCHASE",
        purpose_ref="uae_einvoicing",
        amount_fils=1,
        currency="AED",
        idempotency_key="card-key-01",
    )
    provider = UnconfiguredCardProvider()
    with pytest.raises(ApiError) as refused:
        provider.create_session(payment)
    assert refused.value.code == "card_not_configured"
    with pytest.raises(ApiError):
        provider.verify(b"{}", None)


def _db() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    session = Session(engine)
    ensure_catalog(session)
    session.commit()
    return session


def _priced(db: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[Tenant, object]:
    from app.console.billing import update_addon

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
    monkeypatch.setattr("app.console.billing._business_profile", lambda _settings, _tenant: "electronics_wholesale")
    monkeypatch.setattr(
        "app.console.transfers.active_bank_snapshot", lambda _db: {"holder_name": "Axiz", "iban": "AE00"}
    )
    monkeypatch.setattr("app.console.entitlements.publish_purchased", lambda *_args, **_kwargs: None)
    db.commit()
    return tenant, SimpleNamespace()


def test_checkout_reuses_one_invoice_and_one_open_payment(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, settings = _priced(db, monkeypatch)
    first = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="bank_transfer",
        idempotency_key="plugin-key-01",
    )
    second = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="bank_transfer",
        idempotency_key="plugin-key-01",
    )
    third = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="bank_transfer",
        idempotency_key="plugin-key-02",
    )
    assert first["id"] == second["id"] == third["id"]
    assert first["amount_fils"] > 0
    assert first["status"] == "PENDING"
    assert db.scalar(select(func.count()).select_from(CommercialPayment)) == 1
    assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 1
    other = Tenant(slug="other", name="Other", database_url_encrypted="x")
    db.add(other)
    db.commit()
    with pytest.raises(ApiError) as hidden:
        payment_for_tenant(db, other.id, first["id"])
    assert hidden.value.status_code == 404


def test_card_checkout_is_refused_and_cash_waits_for_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, settings = _priced(db, monkeypatch)
    with pytest.raises(ApiError) as card:
        start_plugin_payment(
            db,
            settings,
            tenant,
            tenant.id,
            purpose_type="PLUGIN_PURCHASE",
            addon_code="uae_einvoicing",
            method_code="card",
            idempotency_key="plugin-card-01",
        )
    assert card.value.code == "method_unavailable"
    with pytest.raises(ApiError) as enabling:
        set_enabled(db, "card", True)
    assert enabling.value.code == "card_not_configured"
    with pytest.raises(ApiError):
        start_plugin_payment(
            db,
            settings,
            tenant,
            tenant.id,
            purpose_type="PLUGIN_PURCHASE",
            addon_code="uae_einvoicing",
            method_code="cash",
            idempotency_key="plugin-cash-01",
        )
    set_enabled(db, "cash", True)
    started = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="cash",
        idempotency_key="plugin-cash-01",
    )
    assert started["status"] == "REVIEW_REQUIRED"
    invoice = db.get(BillingInvoice, started["invoice_id"])
    assert invoice is not None and invoice.status == "pending"
    with pytest.raises(ApiError) as short:
        record_cash(db, settings, started["id"], tenant.id, "x")
    assert short.value.code == "reference_required"
    recorded = record_cash(db, settings, started["id"], tenant.id, "CASH-100")
    again = record_cash(db, settings, started["id"], tenant.id, "CASH-100")
    assert recorded.status == again.status == "SUCCEEDED"
    assert invoice.status == "paid"
    assert db.scalar(select(func.count()).select_from(SubscriptionItem)) == 1


def test_transfer_proof_and_approval_move_the_payment_once(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, settings = _priced(db, monkeypatch)
    started = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="bank_transfer",
        idempotency_key="plugin-bank-01",
    )
    mark_invoice_submitted(db, started["invoice_id"])
    db.commit()
    payment = db.get(CommercialPayment, started["id"])
    assert payment is not None and payment.status == "SUBMITTED"
    mark_invoice_succeeded(db, started["invoice_id"])
    mark_invoice_succeeded(db, started["invoice_id"])
    db.commit()
    assert payment.status == "SUCCEEDED"
    succeeded = db.scalar(
        select(func.count())
        .select_from(CommercialPaymentEvent)
        .where(CommercialPaymentEvent.event_type == "PAYMENT_SUCCEEDED")
    )
    assert succeeded == 1
