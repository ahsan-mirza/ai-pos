"""Tenant sales reports from completed receipts, their lines, tenders, and refunds.

Gross sales are sale.subtotal_cents (merchandise as stored, before tax).
Discounts are the promotion and cashier discounts stored on each line.
Charged sales are sale.total_cents (tax included).
Net sales are charged sales minus refunds whose own timestamp falls in the window.
Voided, draft, and quote rows are not completed sales.
A split tender is summed from sale_tenders, so the receipt total is not repeated per method.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.cache import get_value, set_value
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.user import User
from app.schemas.sales_insights import (
    CategoryPerformance,
    InsightCompare,
    InsightWindow,
    PaymentSlice,
    ProductPerformance,
    SalesSummary,
    StaffPerformance,
    TransactionRow,
    TrendPoint,
)
from app.services.settings_service import business_currency
from app.tenancy.context import current_tenant

REVENUE = ("completed", "partially_refunded", "refunded")
# No store timezone column exists. Business days are UTC until one is configured.
REPORT_TZ = "UTC"


@dataclass(frozen=True)
class InsightFilters:
    start: datetime
    end: datetime
    store_id: uuid.UUID | None
    cashier_id: uuid.UUID | None
    category: str | None
    method: str | None
    sale_type: str | None
    status: str | None
    query: str | None
    currency: str

    def token(self) -> str:
        raw = json.dumps(
            {
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
                "store": str(self.store_id) if self.store_id else "",
                "cashier": str(self.cashier_id) if self.cashier_id else "",
                "category": self.category or "",
                "method": self.method or "",
                "sale_type": self.sale_type or "",
                "status": self.status or "",
                "query": self.query or "",
                "currency": self.currency,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


def resolve_store(principal: Principal, requested: uuid.UUID | None) -> uuid.UUID | None:
    bound = principal.store_id
    if bound is not None and requested is not None and requested != bound:
        raise ApiError(403, "store_scope", "You can only view your own store.")
    return bound if bound is not None else requested


def window_for(
    start: datetime | None, end: datetime | None, *, now: datetime | None = None
) -> tuple[datetime, datetime]:
    clock = now or datetime.now(UTC)
    finish = end or clock
    begin = start or datetime(finish.year, finish.month, finish.day, tzinfo=UTC)
    if begin.tzinfo is None:
        begin = begin.replace(tzinfo=UTC)
    if finish.tzinfo is None:
        finish = finish.replace(tzinfo=UTC)
    begin = begin.astimezone(UTC)
    finish = finish.astimezone(UTC)
    if finish <= begin:
        raise ApiError(422, "bad_range", "The end of the report must be after the start.")
    if finish - begin > timedelta(days=366):
        raise ApiError(422, "range_too_wide", "Choose a reporting period of one year or less.")
    return begin, finish


def _sale_ids(filters: InsightFilters):
    status = (filters.status,) if filters.status else REVENUE
    statement = select(Sale.id).where(
        Sale.is_quote_proforma.is_(False),
        Sale.created_at >= filters.start,
        Sale.created_at < filters.end,
        Sale.status.in_(status),
        Sale.currency == filters.currency,
    )
    if filters.store_id is not None:
        statement = statement.where(Sale.store_id == filters.store_id)
    if filters.cashier_id is not None:
        statement = statement.where(Sale.cashier_id == filters.cashier_id)
    if filters.sale_type is not None:
        statement = statement.where(Sale.sale_type == filters.sale_type)
    if filters.method is not None:
        tendered = select(SaleTender.sale_id).where(SaleTender.method == filters.method)
        statement = statement.where(or_(Sale.payment_method == filters.method, Sale.id.in_(tendered)))
    if filters.category or filters.query:
        match = select(SaleItem.sale_id).join(Product, Product.id == SaleItem.product_id, isouter=True)
        if filters.category:
            match = match.where(func.coalesce(Product.category, "Uncategorized") == filters.category)
        if filters.query:
            like = f"%{filters.query.strip()}%"
            match = match.where(
                or_(
                    SaleItem.product_name.ilike(like),
                    SaleItem.sku.ilike(like),
                    Product.name.ilike(like),
                    Product.sku.ilike(like),
                )
            )
        statement = statement.where(Sale.id.in_(match))
    return statement


def _receipt_clause(filters: InsightFilters):
    return Sale.id.in_(_sale_ids(filters))


def _money(value: object) -> int:
    return int(value or 0)


def summary(db: Session, filters: InsightFilters) -> SalesSummary:
    tenant = current_tenant()
    key = f"sales-insights:{tenant.id if tenant else 'local'}:summary:{filters.token()}"
    cached = get_value(key)
    if cached:
        return SalesSummary.model_validate_json(cached)
    clause = _receipt_clause(filters)
    header = db.execute(
        select(
            func.coalesce(func.sum(Sale.subtotal_cents), 0),
            func.coalesce(func.sum(Sale.tax_cents), 0),
            func.coalesce(func.sum(Sale.total_cents), 0),
            func.count(Sale.id),
        ).where(clause)
    ).one()
    lines = db.execute(
        select(
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.discount_cents + SaleItem.manual_discount_cents), 0),
        )
        .select_from(SaleItem)
        .where(SaleItem.sale_id.in_(_sale_ids(filters)))
    ).one()
    refunds = db.execute(
        select(func.coalesce(func.sum(SaleReturn.total_refund_cents), 0)).where(
            SaleReturn.currency == filters.currency,
            SaleReturn.created_at >= filters.start,
            SaleReturn.created_at < filters.end,
            *([SaleReturn.store_id == filters.store_id] if filters.store_id else []),
        )
    ).scalar_one()
    voided = db.scalar(
        select(func.count())
        .select_from(Sale)
        .where(
            Sale.status == "voided",
            Sale.created_at >= filters.start,
            Sale.created_at < filters.end,
            *([Sale.store_id == filters.store_id] if filters.store_id else []),
        )
    )
    gross, tax, charged, count = (_money(header[0]), _money(header[1]), _money(header[2]), _money(header[3]))
    items, discounts = _money(lines[0]), _money(lines[1])
    returned_items = _money(
        db.scalar(
            select(func.coalesce(func.sum(ReturnItem.quantity), 0))
            .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
            .where(
                SaleReturn.currency == filters.currency,
                SaleReturn.created_at >= filters.start,
                SaleReturn.created_at < filters.end,
                *([SaleReturn.store_id == filters.store_id] if filters.store_id else []),
            )
        )
    )
    items = max(0, items - returned_items)
    refund_cents = _money(refunds)
    net = charged - refund_cents
    span = filters.end - filters.start
    previous = summary_totals(db, filters, filters.start - span, filters.start)
    change = None
    if previous[0] != 0:
        change = round((net - previous[0]) * 10_000 / previous[0])
    body = SalesSummary(
        window=InsightWindow(start=filters.start, end=filters.end, timezone=REPORT_TZ, currency=filters.currency),
        gross_sales_cents=gross,
        discount_cents=discounts,
        tax_cents=tax,
        charged_cents=charged,
        refund_cents=refund_cents,
        net_sales_cents=net,
        transactions=count,
        items_sold=items,
        average_transaction_cents=(charged // count) if count else 0,
        average_items_per_transaction_bps=(items * 100 // count) if count else 0,
        voided=_money(voided),
        compare=InsightCompare(net_sales_cents=previous[0], transactions=previous[1], net_change_bps=change),
    )
    set_value(key, body.model_dump_json(), 30)
    return body


def summary_totals(db: Session, filters: InsightFilters, start: datetime, end: datetime) -> tuple[int, int]:
    earlier = InsightFilters(
        start,
        end,
        filters.store_id,
        filters.cashier_id,
        filters.category,
        filters.method,
        filters.sale_type,
        filters.status,
        filters.query,
        filters.currency,
    )
    charged = _money(db.scalar(select(func.coalesce(func.sum(Sale.total_cents), 0)).where(_receipt_clause(earlier))))
    count = _money(db.scalar(select(func.count()).select_from(Sale).where(_receipt_clause(earlier))))
    refunds = _money(
        db.scalar(
            select(func.coalesce(func.sum(SaleReturn.total_refund_cents), 0)).where(
                SaleReturn.currency == filters.currency,
                SaleReturn.created_at >= start,
                SaleReturn.created_at < end,
                *([SaleReturn.store_id == filters.store_id] if filters.store_id else []),
            )
        )
    )
    return charged - refunds, count


def products(
    db: Session, filters: InsightFilters, *, include_cost: bool, limit: int, offset: int
) -> tuple[int, list[ProductPerformance]]:
    name = func.coalesce(SaleItem.product_name, Product.name, "Unknown product")
    sku = func.coalesce(SaleItem.sku, Product.sku, "")
    category = func.coalesce(Product.category, "Uncategorized")
    grouped = (
        select(
            SaleItem.product_id,
            name.label("name"),
            sku.label("sku"),
            category.label("category"),
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.unit_price_cents * SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.discount_cents + SaleItem.manual_discount_cents), 0),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            func.count(func.distinct(SaleItem.sale_id)),
            func.coalesce(func.sum(SaleItem.cost_cents), 0),
        )
        .select_from(SaleItem)
        .join(Product, Product.id == SaleItem.product_id, isouter=True)
        .where(SaleItem.sale_id.in_(_sale_ids(filters)))
        .group_by(SaleItem.product_id, name, sku, category)
    )
    rows = list(db.execute(grouped).all())
    total_net = sum(_money(row[7]) for row in rows) or 1
    ranked = sorted(rows, key=lambda row: _money(row[7]), reverse=True)
    page = ranked[offset : offset + limit]
    body = [
        ProductPerformance(
            product_id=str(row[0]),
            name=row[1],
            sku=row[2] or "",
            category=row[3],
            quantity=_money(row[4]),
            gross_cents=_money(row[5]),
            discount_cents=_money(row[6]),
            net_cents=_money(row[7]),
            transactions=_money(row[8]),
            contribution_bps=round(_money(row[7]) * 10_000 / total_net),
            cost_cents=_money(row[9]) if include_cost else None,
        )
        for row in page
    ]
    return len(ranked), body


def _cashier_clause(cashier_id: uuid.UUID | None):
    return Sale.cashier_id.is_(None) if cashier_id is None else Sale.cashier_id == cashier_id


def staff(db: Session, filters: InsightFilters) -> list[StaffPerformance]:
    people = db.execute(
        select(Sale.cashier_id, func.coalesce(User.full_name, "Unassigned"))
        .join(User, User.id == Sale.cashier_id, isouter=True)
        .where(_receipt_clause(filters))
        .group_by(Sale.cashier_id, User.full_name)
    ).all()
    ranked: list[StaffPerformance] = []
    for cashier_id, label in people:
        who = _cashier_clause(cashier_id)
        header = db.execute(
            select(
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.subtotal_cents), 0),
                func.coalesce(func.sum(Sale.total_cents), 0),
            ).where(_receipt_clause(filters), who)
        ).one()
        lines = db.execute(
            select(
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.coalesce(func.sum(SaleItem.discount_cents + SaleItem.manual_discount_cents), 0),
            ).where(SaleItem.sale_id.in_(select(Sale.id).where(_receipt_clause(filters), who)))
        ).one()
        count = _money(header[0])
        charged = _money(header[2])
        ranked.append(
            StaffPerformance(
                cashier_id=str(cashier_id) if cashier_id else None,
                name=label,
                transactions=count,
                items_sold=_money(lines[0]),
                gross_cents=_money(header[1]),
                discount_cents=_money(lines[1]),
                net_cents=charged,
                average_cents=(charged // count) if count else 0,
            )
        )
    return sorted(ranked, key=lambda row: row.net_cents, reverse=True)


def categories(db: Session, filters: InsightFilters) -> list[CategoryPerformance]:
    category = func.coalesce(Product.category, "Uncategorized")
    rows = db.execute(
        select(
            category,
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            func.count(func.distinct(SaleItem.sale_id)),
        )
        .select_from(SaleItem)
        .join(Product, Product.id == SaleItem.product_id, isouter=True)
        .where(SaleItem.sale_id.in_(_sale_ids(filters)))
        .group_by(category)
        .order_by(func.coalesce(func.sum(SaleItem.line_total_cents), 0).desc())
    ).all()
    total = sum(_money(row[2]) for row in rows) or 1
    return [
        CategoryPerformance(
            category=row[0],
            quantity=_money(row[1]),
            net_cents=_money(row[2]),
            transactions=_money(row[3]),
            contribution_bps=round(_money(row[2]) * 10_000 / total),
        )
        for row in rows
    ]


def payments(db: Session, filters: InsightFilters) -> list[PaymentSlice]:
    tendered = db.execute(
        select(
            SaleTender.method,
            func.coalesce(func.sum(SaleTender.amount_cents), 0),
            func.count(func.distinct(SaleTender.sale_id)),
        )
        .where(SaleTender.sale_id.in_(_sale_ids(filters)))
        .group_by(SaleTender.method)
    ).all()
    covered = select(SaleTender.sale_id).where(SaleTender.sale_id.in_(_sale_ids(filters)))
    bare = db.execute(
        select(Sale.payment_method, func.coalesce(func.sum(Sale.total_cents), 0), func.count(Sale.id)).where(
            _receipt_clause(filters), Sale.id.not_in(covered)
        ).group_by(Sale.payment_method)
    ).all()
    merged: dict[str, list[int]] = {}
    for method, amount, count in (*tendered, *bare):
        slot = merged.setdefault(method, [0, 0])
        slot[0] += _money(amount)
        slot[1] += _money(count)
    return [
        PaymentSlice(method=method, amount_cents=values[0], transactions=values[1])
        for method, values in sorted(merged.items())
    ]


def trends(db: Session, filters: InsightFilters, bucket: str) -> list[TrendPoint]:
    if bucket == "hour" and filters.end - filters.start > timedelta(days=2):
        raise ApiError(422, "range_too_wide", "Hourly trends are available for ranges of two days or less.")
    dialect = db.get_bind().dialect.name
    column = Sale.created_at
    if dialect == "postgresql":
        label = func.to_char(func.date_trunc(bucket if bucket != "day" else "day", column), "YYYY-MM-DD HH24:MI")
    else:
        pattern = "%Y-%m-%d %H:00" if bucket == "hour" else "%Y-%m-%d"
        label = func.strftime(pattern, column)
    rows = db.execute(
        select(label, func.coalesce(func.sum(Sale.total_cents), 0), func.count(Sale.id))
        .where(_receipt_clause(filters))
        .group_by(label)
        .order_by(label)
    ).all()
    return [TrendPoint(bucket=str(row[0]), charged_cents=_money(row[1]), transactions=_money(row[2])) for row in rows]


def transactions(
    db: Session, filters: InsightFilters, *, limit: int, offset: int, receipt: str | None
) -> tuple[int, list[TransactionRow]]:
    clause = _receipt_clause(filters)
    if receipt:
        like = f"%{receipt.strip()}%"
        clause = and_(clause, or_(Sale.invoice_number.ilike(like), Sale.client_sale_id.ilike(like)))
    total = _money(db.scalar(select(func.count()).select_from(Sale).where(clause)))
    rows = db.execute(
        select(Sale, func.coalesce(User.full_name, "Unassigned"))
        .join(User, User.id == Sale.cashier_id, isouter=True)
        .where(clause)
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    body: list[TransactionRow] = []
    for sale, cashier in rows:
        qty = _money(
            db.scalar(select(func.coalesce(func.sum(SaleItem.quantity), 0)).where(SaleItem.sale_id == sale.id))
        )
        discount = _money(
            db.scalar(
                select(func.coalesce(func.sum(SaleItem.discount_cents + SaleItem.manual_discount_cents), 0)).where(
                    SaleItem.sale_id == sale.id
                )
            )
        )
        body.append(
            TransactionRow(
                id=str(sale.id),
                invoice_number=sale.invoice_number,
                created_at=sale.created_at,
                cashier=cashier,
                items=qty,
                gross_cents=sale.subtotal_cents,
                discount_cents=discount,
                net_cents=sale.total_cents,
                tax_cents=sale.tax_cents,
                payment_method=sale.payment_method,
                status=sale.status,
            )
        )
    return total, body


def sees_cost(principal: Principal) -> bool:
    return principal.has(Permission.PORTAL_INVENTORY_MANAGE)


def currency_for(db: Session) -> str:
    return business_currency(db)
