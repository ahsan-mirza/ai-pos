"""Issue one voucher per customer per period, from a promotion the merchant already configured.

The promotion engine still calculates the discount. This module only decides who receives a code.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerCoupon
from app.models.product import Product
from app.models.promotion import Promotion, PromotionRedemption
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.services import messaging_service

HISTORY = ("completed", "partially_refunded")


def list_for_customer(db: Session, customer_id: uuid.UUID) -> list[dict[str, object]]:
    rows = db.execute(
        select(CustomerCoupon, Promotion)
        .join(Promotion, Promotion.id == CustomerCoupon.promotion_id)
        .where(CustomerCoupon.customer_id == customer_id)
        .order_by(CustomerCoupon.issued_at.desc())
    ).all()
    return [
        {
            "id": coupon.id,
            "code": coupon.code,
            "status": coupon.status,
            "reason": coupon.reason,
            "issued_at": coupon.issued_at,
            "expires_at": coupon.expires_at,
            "min_spend_cents": promo.min_spend_cents,
            "promotion_id": promo.id,
            "promotion_name": promo.name,
            "kind": promo.kind,
            "amount_cents": (promo.params or {}).get("amount_cents"),
            "percent_bps": (promo.params or {}).get("percent_bps"),
            "product_ids": list(promo.product_ids or []),
            "category_ids": list(promo.category_ids or []),
        }
        for coupon, promo in rows
    ]


def report(db: Session) -> dict[str, int]:
    issued = db.scalar(select(func.count(CustomerCoupon.id))) or 0
    redeemed = db.scalar(select(func.count(CustomerCoupon.id)).where(CustomerCoupon.status == "redeemed")) or 0
    discount = (
        db.scalar(
            select(func.coalesce(func.sum(PromotionRedemption.discount_cents), 0)).where(
                PromotionRedemption.customer_coupon_id.is_not(None)
            )
        )
        or 0
    )
    sales = (
        db.scalar(
            select(func.count(func.distinct(PromotionRedemption.sale_id))).where(
                PromotionRedemption.customer_coupon_id.is_not(None)
            )
        )
        or 0
    )
    return {"issued": int(issued), "redeemed": int(redeemed), "discount_cents": int(discount), "sales": int(sales)}


def issue_due(db: Session) -> int:
    """Walk active customer promotions and issue a voucher when the customer's history matches."""
    now = datetime.now(UTC)
    created = 0
    promos = list(db.scalars(select(Promotion).where(Promotion.is_active.is_(True))))
    customers = list(db.scalars(select(Customer).where(Customer.is_active.is_(True))))
    for promo in promos:
        params = promo.params or {}
        if not params.get("customer_issued"):
            continue
        if promo.ends_at is not None and promo.ends_at <= now:
            continue
        for customer in customers:
            reason = _matches(db, promo, customer, now)
            if reason is None:
                continue
            if _issue(db, promo, customer, reason=reason, now=now) is not None:
                created += 1
    return created


def _issue(db: Session, promo: Promotion, customer: Customer, *, reason: str, now: datetime) -> CustomerCoupon | None:
    key = _period_key(promo, customer.id, now)
    existing = db.scalar(select(CustomerCoupon).where(CustomerCoupon.idempotency_key == key))
    if existing is not None:
        return None
    params = promo.params or {}
    window = int(params.get("window_days") or params.get("quiet_days") or 30)
    expires = promo.ends_at or now + timedelta(days=window)
    for _ in range(5):
        row = CustomerCoupon(
            promotion_id=promo.id,
            customer_id=customer.id,
            code=secrets.token_hex(4).upper(),
            status="issued",
            reason=reason[:255],
            issued_at=now,
            expires_at=expires,
            idempotency_key=key,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            continue
        _notify(db, promo, customer, row)
        return row
    return None


def _notify(db: Session, promo: Promotion, customer: Customer, coupon: CustomerCoupon) -> None:
    params = promo.params or {}
    if not params.get("notify"):
        return
    if customer.email_opt_in:
        channel = "email"
    elif customer.whatsapp_opt_in:
        channel = "whatsapp"
    else:
        return
    messaging_service.enqueue(
        db,
        template_key="coupon_issued",
        customer=customer,
        channel=channel,
        context={"code": coupon.code, "offer": promo.name, "reason": coupon.reason},
        dedupe_key=str(coupon.id),
    )


def _period_key(promo: Promotion, customer_id: uuid.UUID, now: datetime) -> str:
    params = promo.params or {}
    if params.get("segment") == "milestone" and not params.get("visit_count") and not params.get("spend_cents"):
        return f"{promo.id}:{customer_id}:first"
    days = int(params.get("window_days") or params.get("quiet_days") or 30)
    return f"{promo.id}:{customer_id}:{now.date().toordinal() // days}"


def _matches(db: Session, promo: Promotion, customer: Customer, now: datetime) -> str | None:
    params = promo.params or {}
    segment = params.get("segment")
    sales = _history(db, customer.id)
    if segment == "loyalty":
        return "Has loyalty points" if customer.loyalty_points > 0 else None
    if segment == "birthday":
        birthday = customer.birthday
        if birthday is None or (birthday.month, birthday.day) != (now.month, now.day):
            return None
        return "Birthday"
    if segment == "win_back":
        quiet = int(params.get("quiet_days") or 30)
        if not sales:
            return None
        last = sales[0].created_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if now - last < timedelta(days=quiet):
            return None
        return f"No purchase for {quiet} days"
    window_days = int(params.get("window_days") or 365)
    start = now - timedelta(days=window_days)
    recent = [sale for sale in sales if _aware(sale.created_at) >= start]
    if segment == "repeat":
        needed = int(params.get("repeat_count") or 2)
        hits = _matching_lines(db, promo, recent)
        return f"Bought {hits} times" if hits >= needed else None
    if segment == "category":
        return "Bought a listed product" if _matching_lines(db, promo, recent) > 0 else None
    if segment == "basket":
        floor = promo.min_spend_cents
        return "Basket reached the minimum" if any(_net(db, sale) >= floor for sale in recent) else None
    if segment == "milestone":
        if params.get("visit_count") and len(sales) >= int(params["visit_count"]):
            return f"{len(sales)} purchases"
        if params.get("spend_cents") and sum(_net(db, sale) for sale in sales) >= int(params["spend_cents"]):
            return "Spend milestone"
        if not params.get("visit_count") and not params.get("spend_cents") and len(sales) == 1:
            return "First purchase"
    return None


def _history(db: Session, customer_id: uuid.UUID) -> list[Sale]:
    return list(
        db.scalars(
            select(Sale)
            .where(
                Sale.customer_id == customer_id,
                Sale.is_quote_proforma.is_(False),
                Sale.status.in_(HISTORY),
            )
            .order_by(Sale.created_at.desc())
        )
    )


def _matching_lines(db: Session, promo: Promotion, sales: list[Sale]) -> int:
    if not sales:
        return 0
    product_ids = set(promo.product_ids or [])
    category_ids = set(promo.category_ids or [])
    rows = db.execute(
        select(SaleItem, Product)
        .join(Product, Product.id == SaleItem.product_id)
        .where(SaleItem.sale_id.in_([sale.id for sale in sales]))
    ).all()
    hits = 0
    for item, product in rows:
        if _refunded_quantity(db, item.id) >= item.quantity:
            continue
        category = str(product.category_id) if product.category_id else None
        if (not product_ids and not category_ids) or str(item.product_id) in product_ids or (
            category is not None and category in category_ids
        ):
            hits += 1
    return hits


def _refunded_quantity(db: Session, sale_item_id: uuid.UUID) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ReturnItem.quantity), 0)).where(ReturnItem.sale_item_id == sale_item_id)
    )
    return int(total or 0)


def _net(db: Session, sale: Sale) -> int:
    lines = int(
        db.scalar(select(func.coalesce(func.sum(SaleItem.line_total_cents), 0)).where(SaleItem.sale_id == sale.id)) or 0
    )
    refunded = int(
        db.scalar(
            select(func.coalesce(func.sum(ReturnItem.refund_cents), 0))
            .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
            .where(SaleItem.sale_id == sale.id)
        )
        or 0
    )
    return max(0, lines - refunded)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
