"""The approved UAE catalog prices the four packages and the purchasable add-ons.

A second catalog init does not overwrite a console price, an invoice, or a legacy plan.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import cycle_amount, ensure_catalog, quote_addon, quote_for
from app.core.errors import ApiError
from app.schemas.billing import AddonQty
from app.tenancy.models import (
    BillingAddon,
    BillingCycle,
    BillingInvoice,
    BillingInvoiceLine,
    BillingPlan,
    CommercialCatalogRelease,
    ControlBase,
    Subscription,
    Tenant,
)


def _control() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def test_package_quotes_use_the_cycle_discount_and_add_no_tax() -> None:
    with _control() as db:
        ensure_catalog(db)
        db.commit()
        monthly = quote_for(db, "GROWTH", "MONTHLY", [])
        assert monthly.currency == "AED"
        assert monthly.recurring_fils == 12_900
        assert monthly.one_time_fils == 0
        assert monthly.total_fils == monthly.recurring_fils
        assert all(line.code != "onboarding" for line in monthly.lines)
        assisted = quote_for(db, "GROWTH", "MONTHLY", [], onboarding=True)
        assistance = next(line for line in assisted.lines if line.code == "onboarding")
        assert assistance.amount_fils == 25_000 and assistance.recurring is False
        assert assisted.recurring_fils == 12_900
        assert assisted.total_fils == 12_900 + 25_000
        assert monthly.discount_bps == 0
        assert all("tax" not in line.code and "vat" not in line.code for line in monthly.lines)
        assert all("tax" not in line.code and "vat" not in line.code for line in assisted.lines)

        assert quote_for(db, "GROWTH", "QUARTERLY", []).recurring_fils == cycle_amount(12_900, 3, 500)
        assert quote_for(db, "GROWTH", "HALF_YEARLY", []).recurring_fils == cycle_amount(12_900, 6, 1_200)
        annual = quote_for(db, "GROWTH", "ANNUAL", [])
        assert annual.discount_bps == 2_000
        assert annual.recurring_fils == cycle_amount(12_900, 12, 2_000)

        for code in ("MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUAL"):
            quoted = quote_for(db, "PRO_AI", code, [])
            assert quoted.plan_code == "PRO_AI"
            assert quoted.recurring_fils > 0
            assert quoted.total_fils == quoted.recurring_fils + quoted.one_time_fils

        free = quote_for(db, "FREE", "MONTHLY", [])
        assert free.recurring_fils == 0
        assert free.one_time_fils == 0
        with pytest.raises(ApiError) as custom:
            quote_for(db, "ENTERPRISE", "MONTHLY", [])
        assert custom.value.code == "custom_pricing"

        combined = quote_for(db, "GROWTH", "MONTHLY", [AddonQty(code="fefo", quantity=1)])
        assert combined.recurring_fils == 12_900 + 1_900
        with pytest.raises(ApiError) as included:
            quote_for(db, "GROWTH", "MONTHLY", [AddonQty(code="sales_insights", quantity=1)])
        assert included.value.code == "already_included"


def test_a_paid_onboarding_fee_is_not_quoted_again() -> None:
    with _control() as db:
        ensure_catalog(db)
        db.commit()
        tenant = Tenant(slug="paid-help", name="Paid Help", status="active", database_url_encrypted="x", plan="FREE")
        db.add(tenant)
        db.flush()
        invoice = BillingInvoice(
            tenant_id=tenant.id,
            status="paid",
            plan_code="GROWTH",
            cycle_code="MONTHLY",
            recurring_fils=12_900,
            one_time_fils=25_000,
            total_fils=37_900,
            confirm_name="Paid Help",
        )
        db.add(invoice)
        db.flush()
        db.add(
            BillingInvoiceLine(
                invoice_id=invoice.id,
                code="onboarding",
                label="Onboarding",
                quantity=1,
                unit_fils=25_000,
                amount_fils=25_000,
                recurring=False,
            )
        )
        db.commit()
        with pytest.raises(ApiError) as again:
            quote_for(db, "PRO_AI", "MONTHLY", [], onboarding=True, tenant_id=tenant.id)
        assert again.value.code == "onboarding_already_purchased"
        assert invoice.total_fils == 37_900 and invoice.plan_code == "GROWTH"


def test_unpriced_add_ons_receive_a_price_once_and_history_is_kept() -> None:
    with _control() as db:
        ensure_catalog(db)
        legacy = BillingPlan(code="LITE", name="Lite", monthly_fils=14_900, active=True, updated_at=datetime.now(UTC))
        db.add(legacy)
        db.flush()
        tenant = Tenant(slug="old", name="Old", status="active", database_url_encrypted="x", plan="LITE")
        db.add(tenant)
        db.flush()
        invoice = BillingInvoice(
            tenant_id=tenant.id,
            status="paid",
            plan_code="LITE",
            cycle_code="MONTHLY",
            total_fils=14_900,
            confirm_name="Old",
        )
        db.add(invoice)
        db.commit()

        einvoice = db.scalar(select(BillingAddon).where(BillingAddon.code == "uae_einvoicing"))
        assert einvoice is not None and einvoice.monthly_fils == 4_900
        insights = db.scalar(select(BillingAddon).where(BillingAddon.code == "ai_insights"))
        assert insights is not None and insights.monthly_fils == 7_900
        delivery = db.scalar(select(BillingAddon).where(BillingAddon.code == "delivery_integrations"))
        assert delivery is not None and delivery.monthly_fils == 0
        assert db.get(CommercialCatalogRelease, "2026-11-14-uae-1") is not None

        einvoice.monthly_fils = 9_900
        growth = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        assert growth is not None
        growth.monthly_fils = 11_100
        db.commit()
        ensure_catalog(db)
        db.commit()
        assert einvoice.monthly_fils == 9_900
        assert growth.monthly_fils == 11_100
        assert legacy.monthly_fils == 14_900 and legacy.active is False
        assert invoice.total_fils == 14_900 and invoice.plan_code == "LITE"

        tenant_id = tenant.id
        stored_tenant = db.get(Tenant, tenant_id)
        assert stored_tenant is not None
        with pytest.raises(ApiError) as arranged:
            quote_addon(db, None, stored_tenant, "delivery_integrations")  # type: ignore[arg-type]
        assert arranged.value.code == "custom_pricing"

        cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
        assert cycle is not None
        db.add(Subscription(tenant_id=tenant_id, plan_id=growth.id, cycle_id=cycle.id, status="active"))
        db.commit()
        with pytest.raises(ApiError) as owned:
            quote_addon(db, None, stored_tenant, "sales_insights")  # type: ignore[arg-type]
        assert owned.value.code == "already_included"
