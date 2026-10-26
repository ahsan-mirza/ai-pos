"""Shared sales velocity for slow/dead stock, fast movers, and best sellers.

Windows are half-open UTC ranges. Net units are posted ``SaleItem.quantity`` (already pieces or grams)
minus ``ReturnItem.quantity`` whose return falls in the same window. A sale line still counts as the last
qualifying sale when returned quantity is less than sold quantity. Fully returned lines do not.

These thresholds are the one policy for the aged-stock report, clearance suggestions, and the assistant.
Fast-mover gates stay separate and are not a slow/dead status.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn

POSTED = ("completed", "partially_refunded", "refunded")

# Aged stock. Cover of exactly COVER_SLOW_DAYS is not slow; only more than that is.
SLOW_DAYS = 60
DEAD_DAYS = 180
COVER_SLOW_DAYS = 180
VELOCITY_WINDOW_DAYS = 90

# Fast movers (RAISE_ON_DEMAND). Recent and baseline windows are adjacent and compared as daily rates.
DEMAND_DAYS = 28
BASELINE_DAYS = 56
DEMAND_MIN_UNITS = 10
DEMAND_GROWTH = 1.5
DEMAND_MAX_COVER_DAYS = 14

RankBy = Literal["quantity", "revenue"]


def cover_days(on_hand: int, net_units: int, window_days: int) -> int | None:
    """Days of stock at the window's net daily rate. Zero or negative net sales is no velocity, not infinite cover."""
    if net_units <= 0 or window_days <= 0:
        return None
    return round(on_hand / (net_units / window_days))


def _aware(value: datetime) -> datetime:
    from datetime import UTC

    return value if value.tzinfo else value.replace(tzinfo=UTC)


def last_qualifying_sale(
    db: Session, *, store_id: uuid.UUID | None = None
) -> dict[tuple[uuid.UUID, uuid.UUID], datetime]:
    """Latest posted sale per product and store whose line was not fully returned."""
    returned = (
        select(ReturnItem.sale_item_id, func.sum(ReturnItem.quantity).label("qty"))
        .group_by(ReturnItem.sale_item_id)
        .subquery()
    )
    query = (
        select(SaleItem.product_id, Sale.store_id, func.max(Sale.created_at))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .outerjoin(returned, returned.c.sale_item_id == SaleItem.id)
        .where(
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
            SaleItem.quantity > func.coalesce(returned.c.qty, 0),
        )
        .group_by(SaleItem.product_id, Sale.store_id)
    )
    if store_id is not None:
        query = query.where(Sale.store_id == store_id)
    return {(product_id, store): _aware(moment) for product_id, store, moment in db.execute(query)}


def _net(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    store_id: uuid.UUID | None,
    by_store: bool,
) -> dict:
    """Net units (and, when by_store is false, this is units only) in ``[since, until)``."""
    sales = (
        select(SaleItem.product_id, Sale.store_id, func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(SaleItem.product_id, Sale.store_id)
    )
    returns = (
        select(ReturnItem.product_id, SaleReturn.store_id, func.coalesce(func.sum(ReturnItem.quantity), 0))
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
        .group_by(ReturnItem.product_id, SaleReturn.store_id)
    )
    if store_id is not None:
        sales = sales.where(Sale.store_id == store_id)
        returns = returns.where(SaleReturn.store_id == store_id)
    totals: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for product_id, store, units in db.execute(sales):
        totals[(product_id, store)] = totals.get((product_id, store), 0) + int(units)
    for product_id, store, units in db.execute(returns):
        totals[(product_id, store)] = totals.get((product_id, store), 0) - int(units)
    if by_store:
        return totals
    by_product: dict[uuid.UUID, int] = {}
    for (product_id, _), units in totals.items():
        by_product[product_id] = by_product.get(product_id, 0) + units
    return by_product


def net_units_by_store(
    db: Session, *, since: datetime, until: datetime, store_id: uuid.UUID | None = None
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """Net units per ``(product, store)``. Negative when returns in the window exceed sales."""
    return _net(db, since=since, until=until, store_id=store_id, by_store=True)


def net_units_by_product(
    db: Session, *, since: datetime, until: datetime, store_id: uuid.UUID | None = None
) -> dict[uuid.UUID, int]:
    """Net units per product, summed across the scoped stores."""
    return _net(db, since=since, until=until, store_id=store_id, by_store=False)


@dataclass(frozen=True)
class RankedProduct:
    product_id: uuid.UUID
    name: str
    sku: str
    category: str
    units: int
    revenue_cents: int


def rank_products(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    store_id: uuid.UUID | None = None,
    category: str | None = None,
    limit: int = 10,
    by: RankBy = "revenue",
) -> list[RankedProduct]:
    """Best sellers by net units. Revenue is line totals minus refunds dated in the same window.

    Rows with no positive net units are left out. Pack ``unit_factor`` is not applied: quantity is already
    base units.
    """
    sales = (
        select(
            SaleItem.product_id,
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(SaleItem.product_id)
    )
    refunds = (
        select(
            ReturnItem.product_id,
            func.coalesce(func.sum(ReturnItem.quantity), 0),
            func.coalesce(func.sum(ReturnItem.refund_cents), 0),
        )
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
        .group_by(ReturnItem.product_id)
    )
    if store_id is not None:
        sales = sales.where(Sale.store_id == store_id)
        refunds = refunds.where(SaleReturn.store_id == store_id)
    totals: dict[uuid.UUID, list[int]] = {}
    for product_id, units, revenue in db.execute(sales):
        bucket = totals.setdefault(product_id, [0, 0])
        bucket[0] += int(units)
        bucket[1] += int(revenue)
    for product_id, units, refunded in db.execute(refunds):
        bucket = totals.setdefault(product_id, [0, 0])
        bucket[0] -= int(units)
        bucket[1] -= int(refunded)
    positive = {product_id: amounts for product_id, amounts in totals.items() if amounts[0] > 0}
    if not positive:
        return []
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_(positive))).unique()
    }
    ranked: list[RankedProduct] = []
    needle = category.strip().lower() if category and category.strip() else None
    for product_id, (units, revenue) in positive.items():
        product = products.get(product_id)
        if product is None:
            continue
        if needle is not None and product.category.lower() != needle:
            continue
        ranked.append(
            RankedProduct(
                product_id=product_id,
                name=product.name,
                sku=product.sku,
                category=product.category,
                units=units,
                revenue_cents=revenue,
            )
        )
    ranked.sort(key=lambda row: (-(row.units if by == "quantity" else row.revenue_cents), row.name.lower()))
    return ranked[: max(limit, 0)]
