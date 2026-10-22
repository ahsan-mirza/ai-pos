import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.schemas.payloads import AnalyticsSummary, CategorySlice, PaymentSplit

# Returned sales still happened; refunds are subtracted separately so revenue nets out correctly.
REVENUE_STATUSES = ("completed", "partially_refunded", "refunded")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def load_sales(
    db: Session,
    currency: str,
    start: datetime | None,
    end: datetime | None,
    store_scope: uuid.UUID | None = None,
) -> list[Sale]:
    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.product))
        .where(Sale.status.in_(REVENUE_STATUSES), Sale.currency == currency)
    )
    if store_scope is not None:
        statement = statement.where(Sale.store_id == store_scope)
    if start is not None:
        statement = statement.where(Sale.created_at >= start)
    if end is not None:
        statement = statement.where(Sale.created_at < end)
    return list(db.scalars(statement).unique().all())


def _load_refunds(
    db: Session,
    currency: str,
    start: datetime | None,
    store_scope: uuid.UUID | None,
) -> list[SaleReturn]:
    statement = select(SaleReturn).where(SaleReturn.currency == currency)
    if store_scope is not None:
        statement = statement.where(SaleReturn.store_id == store_scope)
    if start is not None:
        statement = statement.where(SaleReturn.created_at >= start)
    return list(db.scalars(statement).all())


def _units(sales: list[Sale]) -> int:
    return sum(item.quantity for sale in sales for item in sale.items)


def _bucket(edges: list[datetime], created: datetime) -> int | None:
    for index in range(len(edges) - 1):
        if edges[index] <= created < edges[index + 1]:
            return index
    return None


def _series(sales: list[Sale], refunds: list[SaleReturn], edges: list[datetime]) -> list[int]:
    totals = [0 for _ in range(len(edges) - 1)]
    for sale in sales:
        index = _bucket(edges, _as_utc(sale.created_at))
        if index is not None:
            totals[index] += sale.total_cents
    for refund in refunds:
        index = _bucket(edges, _as_utc(refund.created_at))
        if index is not None:
            totals[index] -= refund.total_refund_cents
    return totals


def period_start(timeframe: str, now: datetime) -> datetime | None:
    if timeframe == "weekly":
        return now - timedelta(days=7)
    if timeframe == "monthly":
        return now - timedelta(days=30)
    return None


def period_edges(timeframe: str, now: datetime) -> list[datetime]:
    if timeframe == "weekly":
        return [now - timedelta(days=7 - offset) for offset in range(8)]
    if timeframe == "monthly":
        return [now - timedelta(days=30 - offset * 5) for offset in range(7)]
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    edges = [month_start]
    cursor = month_start
    for _ in range(5):
        year = cursor.year
        month = cursor.month - 1
        if month == 0:
            month = 12
            year -= 1
        cursor = datetime(year, month, 1, tzinfo=UTC)
        edges.append(cursor)
    edges.reverse()
    edges.append(now)
    return edges


def build_summary(
    db: Session,
    *,
    timeframe: str,
    currency: str,
    store_scope: uuid.UUID | None = None,
) -> AnalyticsSummary:
    now = datetime.now(UTC)
    current_start = period_start(timeframe, now)
    previous_start: datetime | None = None
    if current_start is not None:
        previous_start = current_start - (now - current_start)

    current = load_sales(db, currency, current_start, now, store_scope)
    refunds = _load_refunds(db, currency, current_start, store_scope)
    gross = sum(sale.total_cents for sale in current)
    revenue = gross - sum(refund.total_refund_cents for refund in refunds)
    units = _units(current)
    count = len(current)
    average = (gross + count // 2) // count if count else 0

    growth: int | None = None
    if previous_start is not None:
        previous = load_sales(db, currency, previous_start, current_start, store_scope)
        previous_units = _units(previous)
        if previous_units:
            growth = round((units - previous_units) * 10_000 / previous_units)

    categories: dict[str, CategorySlice] = {}
    payments: dict[str, int] = {}
    for sale in current:
        payments[sale.payment_method] = payments.get(sale.payment_method, 0) + sale.total_cents
        for item in sale.items:
            category = item.product.category if item.product is not None else "Uncategorized"
            current_slice = categories.get(category)
            if current_slice is None:
                current_slice = CategorySlice(category=category, units=0, revenue_cents=0)
                categories[category] = current_slice
            current_slice.units += item.quantity
            current_slice.revenue_cents += item.line_total_cents

    known_methods = {"cash", "card", "transfer", "store_credit", "on_account"}
    wholesale = sum(sale.total_cents for sale in current if sale.sale_type == "WHOLESALE")
    receivables_statement = select(func.coalesce(func.sum(Sale.due_balance_cents), 0)).where(
        Sale.is_quote_proforma.is_(False), Sale.currency == currency
    )
    if store_scope is not None:
        receivables_statement = receivables_statement.where(Sale.store_id == store_scope)
    return AnalyticsSummary(
        timeframe=timeframe,  # type: ignore[arg-type]
        currency=currency,
        net_revenue_cents=revenue,
        units_sold=units,
        average_ticket_cents=average,
        units_growth_bps=growth,
        revenue_series=_series(current, refunds, period_edges(timeframe, now)),
        categories=sorted(categories.values(), key=lambda item: item.revenue_cents, reverse=True),
        payment_split=[
            PaymentSplit(method=method, revenue_cents=amount)  # type: ignore[arg-type]
            for method, amount in sorted(payments.items())
            if method in known_methods
        ],
        cogs_cents=sum(item.cost_cents or 0 for sale in current for item in sale.items),
        gross_margin_cents=sum(
            item.line_total_cents - item.tax_cents - (item.cost_cents or 0)
            for sale in current
            for item in sale.items
            if item.cost_cents is not None
        ),
        wholesale_revenue_cents=wholesale,
        retail_revenue_cents=gross - wholesale,
        receivables_cents=int(db.scalar(receivables_statement) or 0),
    )
