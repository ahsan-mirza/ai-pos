"""Loyalty: points earned on what a customer pays, redeemed as a `loyalty` tender, reversed on returns.

Tiers raise the earn rate from the customer's paid spend over the last 12 months. Points lapse oldest-first
`expiry_months` after they were earned: every debit (redeem, reversal, expiry) is taken from the oldest credits."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.customer import Customer
from app.models.loyalty import LoyaltyEntry
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.schemas.loyalty import (
    LoyaltyEntryOut,
    LoyaltySettingsOut,
    LoyaltySettingsWrite,
    LoyaltyStanding,
    LoyaltyTier,
)
from app.services.settings_service import load_settings
from app.services.warranty_service import add_months

DEFAULTS = {
    "enabled": False,
    "earn_per_unit": 1,
    "redeem_cents": 1,
    "min_redeem": 100,
    "expiry_months": 0,
    "tiers": [],
}
SPEND_WINDOW = timedelta(days=365)
EXPIRY_NOTICE = timedelta(days=30)
CREDIT_TYPES = ("EARN", "ADJUST")


def settings(db: Session) -> LoyaltySettingsOut:
    return LoyaltySettingsOut(**{**DEFAULTS, **(load_settings(db).loyalty or {})})


def update_settings(db: Session, data: LoyaltySettingsWrite) -> LoyaltySettingsOut:
    load_settings(db).loyalty = data.model_dump()
    db.commit()
    return settings(db)


def _post(
    db: Session,
    customer: Customer,
    *,
    entry_type: str,
    points: int,
    sale_id: uuid.UUID | None = None,
    return_id: uuid.UUID | None = None,
    note: str = "",
    user_id: uuid.UUID | None = None,
) -> None:
    if points == 0:
        return
    customer.loyalty_points += points
    db.add(
        LoyaltyEntry(
            customer_id=customer.id,
            entry_type=entry_type,
            points=points,
            balance_after=customer.loyalty_points,
            sale_id=sale_id,
            return_id=return_id,
            note=note[:255],
            user_id=user_id,
        )
    )


def check_redemption(db: Session, customer: Customer | None, points: int | None, amount_cents: int) -> None:
    """A loyalty tender must name the points it spends, at the programme's value, within the balance."""
    rules = settings(db)
    if not rules.enabled:
        raise SyncRejected("The loyalty programme is switched off.")
    if customer is None:
        raise SyncRejected("Redeeming points needs the customer on the sale.")
    if not points:
        raise SyncRejected("Say how many points the loyalty tender spends.")
    if points < rules.min_redeem:
        raise SyncRejected(f"At least {rules.min_redeem} points must be redeemed at a time.")
    if points * rules.redeem_cents != amount_cents:
        raise SyncRejected("The loyalty tender amount does not match the points redeemed.")
    if points > customer.loyalty_points:
        raise SyncRejected(f"{customer.name} has only {customer.loyalty_points} points.")


def spend_12m(db: Session, customer_id: uuid.UUID, now: datetime | None = None) -> int:
    since = (now or datetime.now(UTC)) - SPEND_WINDOW
    sold = db.scalar(
        select(func.coalesce(func.sum(Sale.total_cents), 0)).where(
            Sale.customer_id == customer_id,
            Sale.is_quote_proforma.is_(False),
            Sale.status.not_in(("draft", "voided", "quote")),
            Sale.created_at >= since,
        )
    )
    refunded = db.scalar(
        select(func.coalesce(func.sum(SaleReturn.total_refund_cents), 0))
        .join(Sale, Sale.id == SaleReturn.original_sale_id)
        .where(Sale.customer_id == customer_id, SaleReturn.created_at >= since)
    )
    return max(0, int(sold or 0) - int(refunded or 0))


def tier_for(rules: LoyaltySettingsOut, spend_cents: int) -> LoyaltyTier | None:
    reached = [tier for tier in rules.tiers if spend_cents >= tier.min_spend_cents]
    return reached[-1] if reached else None


def apply_sale(db: Session, customer: Customer, *, sale_id: uuid.UUID, paid_cents: int, redeemed: int, user_id) -> None:
    """Spends redeemed points, then earns on the money actually paid (not on credit or points), at the
    customer's tier rate. The sale being recorded counts towards the tier."""
    rules = settings(db)
    if redeemed:
        _post(db, customer, entry_type="REDEEM", points=-redeemed, sale_id=sale_id, user_id=user_id)
    if rules.enabled and paid_cents > 0:
        tier = tier_for(rules, spend_12m(db, customer.id)) if rules.tiers else None
        multiplier = tier.multiplier_pct if tier is not None else 100
        _post(
            db,
            customer,
            entry_type="EARN",
            points=paid_cents * rules.earn_per_unit * multiplier // 10_000,
            sale_id=sale_id,
            user_id=user_id,
            note=f"{tier.name} tier" if tier is not None and multiplier != 100 else "",
        )


def _lapsing(db: Session, customer: Customer, cutoff: datetime) -> int:
    """Points earned before `cutoff` that no debit has used up yet."""
    old_credits = db.scalar(
        select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
            LoyaltyEntry.customer_id == customer.id,
            LoyaltyEntry.points > 0,
            LoyaltyEntry.entry_type.in_(CREDIT_TYPES),
            LoyaltyEntry.created_at < cutoff,
        )
    )
    debits = db.scalar(
        select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
            LoyaltyEntry.customer_id == customer.id, LoyaltyEntry.points < 0
        )
    )
    return max(0, min(customer.loyalty_points, int(old_credits or 0) + int(debits or 0)))


def expire_points(db: Session, now: datetime | None = None) -> int:
    """Lapses points older than the programme's expiry. Returns the number of customers affected."""
    rules = settings(db)
    if not rules.enabled or rules.expiry_months <= 0:
        return 0
    cutoff = add_months(now or datetime.now(UTC), -rules.expiry_months)
    affected = 0
    for customer in db.scalars(select(Customer).where(Customer.loyalty_points > 0)):
        lapsed = _lapsing(db, customer, cutoff)
        if lapsed > 0:
            _post(
                db,
                customer,
                entry_type="EXPIRE",
                points=-lapsed,
                note=f"Earned before {cutoff:%d %b %Y}, unused",
            )
            affected += 1
    db.commit()
    return affected


def standing(db: Session, customer_id: uuid.UUID) -> LoyaltyStanding:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    rules = settings(db)
    now = datetime.now(UTC)
    spend = spend_12m(db, customer.id, now)
    tier = tier_for(rules, spend)
    upcoming = next((row for row in rules.tiers if row.min_spend_cents > spend), None)
    expiring = 0
    if rules.enabled and rules.expiry_months > 0:
        expiring = _lapsing(db, customer, add_months(now + EXPIRY_NOTICE, -rules.expiry_months))
    return LoyaltyStanding(
        points=customer.loyalty_points,
        tier=tier.name if tier else None,
        multiplier_pct=tier.multiplier_pct if tier else 100,
        spend_12m_cents=spend,
        next_tier=upcoming.name if upcoming else None,
        next_tier_gap_cents=upcoming.min_spend_cents - spend if upcoming else None,
        expiring_soon=expiring,
        entries=ledger(db, customer.id, limit=50),
    )


def reverse_for_return(db: Session, customer: Customer, *, return_id: uuid.UUID, refund_cents: int, user_id) -> None:
    rules = settings(db)
    if not rules.enabled:
        return
    take = min(customer.loyalty_points, refund_cents * rules.earn_per_unit // 100)
    _post(
        db,
        customer,
        entry_type="REVERSE",
        points=-take,
        return_id=return_id,
        user_id=user_id,
        note="Points on returned goods",
    )


def adjust(
    db: Session, customer_id: uuid.UUID, points: int, note: str, user_id: uuid.UUID | None
) -> list[LoyaltyEntryOut]:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    if customer.loyalty_points + points < 0:
        raise ApiError(422, "validation_error", "The balance cannot go below zero.")
    _post(db, customer, entry_type="ADJUST", points=points, note=note, user_id=user_id)
    db.commit()
    return ledger(db, customer_id)


def ledger(db: Session, customer_id: uuid.UUID, limit: int = 200) -> list[LoyaltyEntryOut]:
    rows = db.scalars(
        select(LoyaltyEntry)
        .where(LoyaltyEntry.customer_id == customer_id)
        .order_by(LoyaltyEntry.created_at.desc())
        .limit(limit)
    )
    return [LoyaltyEntryOut.model_validate(row) for row in rows]
