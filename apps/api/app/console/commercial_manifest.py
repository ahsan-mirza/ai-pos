"""Approved UAE commercial catalog. The quote engine reads the database, not this module.

Revision 2026-11-14-uae-1 is applied once to package prices, cycle discounts, and the
onboarding fee. A later console edit of those rows is left alone.

Add-on list prices are filled only while a purchasable add-on is still at zero fils.
A console price above zero is not replaced. Delivery Integrations stays at zero and
is offered as contact-sales, because partner access is not a published list price.

Amounts are fils. 12900 fils is AED 129.00. The quote engine does not add VAT.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.tenancy.models import (
    BillingAddon,
    BillingCycle,
    BillingFee,
    BillingPlan,
    BillingPlanPrice,
    CommercialCatalogRelease,
)

COMMERCIAL_REVISION = "2026-11-14-uae-1"
ONBOARDING_OPTIONAL_REVISION = "2026-11-14-uae-onboarding-optional"

# Monthly list price for a new subscription. Enterprise stays custom and is absent here.
PLAN_MONTHLY_FILS: dict[str, int] = {
    "FREE": 0,
    "GROWTH": 12_900,
    "PRO_AI": 29_900,
}

# Billing-cycle discounts in basis points. 500 is 5 percent. The annual row stays at
# 25 percent for a historical plan. New Free, Growth, and Pro AI invoices use the
# separate published annual rate of 20 percent.
CYCLE_DISCOUNT_BPS: dict[str, int] = {
    "MONTHLY": 0,
    "QUARTERLY": 500,
    "HALF_YEARLY": 1_200,
    "ANNUAL": 2_500,
}

ONBOARDING_FILS = 25_000

# Per tenant, per month. The quote engine has no per-branch or per-register add-on unit.
ADDON_MONTHLY_FILS: dict[str, int] = {
    "split_bills": 1_500,
    "tips_service_charge": 1_500,
    "quotes_layaway": 1_900,
    "multi_currency": 1_900,
    "variants_matrix": 1_900,
    "fefo": 1_900,
    "cheques": 1_900,
    "tax_free": 1_900,
    "alterations": 1_900,
    "wholesale_pricing": 2_900,
    "serial_tracking": 2_900,
    "consignment": 2_900,
    "repairs": 2_900,
    "card_terminals": 2_900,
    "bnpl": 2_900,
    "gift_cards": 2_900,
    "fashion_rental": 2_900,
    "sales_insights": 2_900,
    "tables": 3_900,
    "delivery_channels": 3_900,
    "sales_orders": 3_900,
    "online_store": 3_900,
    "b2b_credit": 3_900,
    "deep_analytics": 4_900,
    "axiz_reach": 4_900,
    "uae_einvoicing": 4_900,
    "fleet_dispatch": 4_900,
    "ai_insights": 7_900,
}

# No published list price. Checkout rejects a purchase until sales agrees a contract.
CUSTOM_ADDON_CODES = frozenset({"delivery_integrations"})


def apply_commercial_catalog(db: Session) -> bool:
    """Applies the package revision once, then fills add-ons that still have no price.

    Subscriptions, invoices, payments, and purchased add-on rows are not read or updated.
    """
    from app.console.billing import ensure_module_addons

    ensure_module_addons(db)
    changed = _apply_revision_once(db)
    if _publish_optional_onboarding_once(db):
        changed = True
    if _fill_unpriced_addons(db):
        changed = True
    return changed


def _apply_revision_once(db: Session) -> bool:
    applied = db.get(CommercialCatalogRelease, COMMERCIAL_REVISION)
    if applied is not None:
        return False
    now = datetime.now(UTC)
    for code, fils in PLAN_MONTHLY_FILS.items():
        row = db.scalar(select(BillingPlan).where(BillingPlan.code == code))
        if row is None:
            continue
        if row.monthly_fils != fils:
            row.monthly_fils = fils
            row.updated_at = now
        price = db.scalar(
            select(BillingPlanPrice).where(BillingPlanPrice.plan_id == row.id, BillingPlanPrice.country == "AE")
        )
        if price is not None and price.monthly_fils != fils:
            price.monthly_fils = fils
            price.updated_at = now
    for code, discount in CYCLE_DISCOUNT_BPS.items():
        cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == code))
        if cycle is None or cycle.discount_bps == discount:
            continue
        cycle.discount_bps = discount
        cycle.updated_at = now
    fee = db.scalar(select(BillingFee).where(BillingFee.code == "onboarding"))
    if fee is not None and fee.amount_fils != ONBOARDING_FILS:
        fee.amount_fils = ONBOARDING_FILS
        fee.updated_at = now
    db.add(CommercialCatalogRelease(revision=COMMERCIAL_REVISION, applied_at=now))
    db.flush()
    return True


def _publish_optional_onboarding_once(db: Session) -> bool:
    """Restores a zeroed onboarding list price once. A later non-zero console amount is kept.

    The fee stays in the catalog. Quotes add it only when the customer opts in.
    """
    if db.get(CommercialCatalogRelease, ONBOARDING_OPTIONAL_REVISION) is not None:
        return False
    now = datetime.now(UTC)
    fee = db.scalar(select(BillingFee).where(BillingFee.code == "onboarding"))
    if fee is not None and int(fee.amount_fils or 0) == 0:
        fee.amount_fils = ONBOARDING_FILS
        fee.updated_at = now
    db.add(CommercialCatalogRelease(revision=ONBOARDING_OPTIONAL_REVISION, applied_at=now))
    db.flush()
    return True


def _fill_unpriced_addons(db: Session) -> bool:
    now = datetime.now(UTC)
    changed = False
    for code, fils in ADDON_MONTHLY_FILS.items():
        row = db.scalar(select(BillingAddon).where(BillingAddon.code == code))
        if row is None or fils <= 0:
            continue
        if int(row.monthly_fils or 0) > 0 or int(row.one_time_fils or 0) > 0:
            continue
        history = list(row.price_history or [])
        history.append(
            {
                "monthly_fils": int(row.monthly_fils or 0),
                "one_time_fils": int(row.one_time_fils or 0),
                "refundable": bool(row.refundable),
                "effective_at": now.isoformat(),
                "reason": COMMERCIAL_REVISION,
            }
        )
        row.price_history = history
        flag_modified(row, "price_history")
        row.monthly_fils = fils
        row.updated_at = now
        changed = True
    if changed:
        db.flush()
    return changed
