"""Shared Deep Analytics totals.

Net sales, revenue, cost, and gross profit use the same figures as the management P&L: line totals
without VAT, refunds without VAT, and the FIFO cost stored on each sale line. Days are UTC dates,
matching the rest of the reports. A register sale appears only after it has synced.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchItem
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.user import User
from app.schemas.deep_analytics import (
    AnalyticsSection,
    Comparison,
    DeepOverview,
    ForecastOut,
    HourPoint,
    Kpi,
    NamedAmount,
    TrendPoint,
)
from app.services.settings_service import cached_settings

POSTED = ("completed", "partially_refunded", "refunded")
FORECAST_DAYS = 14
COVERAGE = "Posted sales already stored for this business. Offline register sales appear after they sync."


def bounds(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Choose a period of at most 400 days that ends after it starts.")
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def growth_bps(current: int, previous: int) -> int | None:
    if previous == 0:
        return None
    return round((current - previous) * 10_000 / previous)


def margin_bps(profit: int, revenue: int) -> int | None:
    if revenue == 0:
        return None
    return round(profit * 10_000 / revenue)


def forecast_from_daily(revenues: list[int]) -> ForecastOut:
    """A 7-day mean of daily revenue. Fewer than 14 days is not a forecast."""
    if len(revenues) < FORECAST_DAYS:
        return ForecastOut(
            status="insufficient_history",
            method="none",
            note=f"A forecast needs at least {FORECAST_DAYS} days in the selected period.",
        )
    daily = round(sum(revenues) / len(revenues)) if revenues else 0
    return ForecastOut(
        status="estimated",
        method="mean daily revenue",
        daily_revenue_cents=daily,
        note=(
            "Estimated mean of daily revenue in the selected period, including days with no sales. "
            "No confidence interval has been evaluated. This is not an actual result."
        ),
    )


def _sale_filters(since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str):
    clauses = [
        Sale.created_at >= since,
        Sale.created_at < until,
        Sale.is_quote_proforma.is_(False),
        Sale.status.in_(POSTED),
        Sale.currency == currency,
    ]
    if store_id is not None:
        clauses.append(Sale.store_id == store_id)
    return clauses


def _sales_totals(db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str) -> dict:
    row = db.execute(
        select(
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            func.coalesce(func.sum(SaleItem.tax_cents), 0),
            func.coalesce(func.sum(func.coalesce(SaleItem.cost_cents, 0)), 0),
            func.coalesce(func.sum(SaleItem.discount_cents + SaleItem.manual_discount_cents), 0),
            func.count(func.distinct(Sale.id)),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*_sale_filters(since, until, store_id, currency))
    ).one()
    missing_cost = db.scalar(
        select(SaleItem.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*_sale_filters(since, until, store_id, currency), SaleItem.cost_cents.is_(None))
        .limit(1)
    )
    tips = db.execute(
        select(
            func.coalesce(func.sum(Sale.tip_cents), 0),
            func.coalesce(func.sum(Sale.service_charge_cents), 0),
        ).where(*_sale_filters(since, until, store_id, currency))
    ).one()
    return {
        "gross_cents": int(row[0]),
        "tax_cents": int(row[1]),
        "cogs_cents": int(row[2]),
        "discount_cents": int(row[3]),
        "transactions": int(row[4]),
        "cost_estimated": missing_cost is not None,
        "tip_cents": int(tips[0]),
        "service_charge_cents": int(tips[1]),
    }


def _return_totals(db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str) -> dict:
    statement = (
        select(
            ReturnItem.refund_cents,
            ReturnItem.tax_refund_cents,
            ReturnItem.quantity,
            SaleItem.cost_cents,
            SaleItem.quantity,
        )
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until, SaleReturn.currency == currency)
    )
    if store_id is not None:
        statement = statement.where(SaleReturn.store_id == store_id)
    refunds = 0
    cogs = 0
    for refund, tax, quantity, cost, sold in db.execute(statement):
        refunds += int(refund) - int(tax)
        cogs += (int(cost or 0) * int(quantity)) // max(int(sold), 1)
    return {"refunds_cents": refunds, "cogs_cents": cogs}


def _kpis(sales: dict, returns: dict) -> tuple[list[Kpi], int, int, bool]:
    net = sales["gross_cents"] - sales["tax_cents"]
    revenue = net - returns["refunds_cents"]
    cogs = sales["cogs_cents"] - returns["cogs_cents"]
    profit = revenue - cogs
    margin = margin_bps(profit, revenue)
    average = round(revenue / sales["transactions"]) if sales["transactions"] else None
    cost_quality = "estimated" if sales["cost_estimated"] else "exact"
    rows = [
        Kpi(
            key="gross_sales",
            label="Gross sales",
            definition="Amount charged on sale lines, including VAT, before refunds.",
            formula="sum(sale line total)",
            cents=sales["gross_cents"],
            quality="exact",
        ),
        Kpi(
            key="net_sales",
            label="Net sales",
            definition="Sale lines with VAT removed, before refunds. Same figure as management P&L net sales.",
            formula="sum(line total - line VAT)",
            cents=net,
            quality="exact",
        ),
        Kpi(
            key="refunds",
            label="Refunds",
            definition="Refunded amount with VAT removed.",
            formula="sum(refund - VAT refunded)",
            cents=returns["refunds_cents"],
            quality="exact",
        ),
        Kpi(
            key="revenue",
            label="Revenue",
            definition="Net sales after refunds, excluding VAT.",
            formula="net sales - refunds",
            cents=revenue,
            quality="exact",
        ),
        Kpi(
            key="discounts",
            label="Discounts",
            definition="Promotion and cashier discounts taken off sale lines before VAT.",
            formula="sum(promotion discount + manual discount)",
            cents=sales["discount_cents"],
            quality="exact",
        ),
        Kpi(
            key="cogs",
            label="Cost of goods",
            definition="FIFO cost stored on each sale line, less the cost of units returned.",
            formula="sum(sale line cost) - returned cost",
            cents=cogs,
            quality=cost_quality,
            note="Missing line cost counts as zero and is marked estimated." if sales["cost_estimated"] else None,
        ),
        Kpi(
            key="gross_profit",
            label="Gross profit",
            definition="Revenue after refunds, minus cost of goods.",
            formula="revenue - cost of goods",
            cents=profit,
            quality=cost_quality,
        ),
        Kpi(
            key="gross_margin",
            label="Gross margin",
            definition="Gross profit as a share of revenue. Blank when revenue is zero.",
            formula="gross profit / revenue",
            bps=margin,
            quality="unavailable" if margin is None else cost_quality,
        ),
        Kpi(
            key="transactions",
            label="Transactions",
            definition="Posted sales in the period. Quotes are not included.",
            formula="count of posted sales",
            count=sales["transactions"],
            quality="exact",
        ),
        Kpi(
            key="average_transaction",
            label="Average transaction",
            definition="Revenue divided by the number of posted sales. Blank when there are no sales.",
            formula="revenue / transactions",
            cents=average,
            quality="unavailable" if average is None else "exact",
        ),
    ]
    return rows, revenue, profit, sales["cost_estimated"]


def _trend(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str
) -> list[TrendPoint]:
    day = func.date(Sale.created_at)
    sales = (
        select(
            day,
            func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0),
            func.coalesce(func.sum(func.coalesce(SaleItem.cost_cents, 0)), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(day)
    )
    by_day: dict[date, list[int]] = {}
    for raw_day, net, cost in db.execute(sales):
        key = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10])
        by_day[key] = [int(net), int(cost)]
    refunds = (
        select(
            SaleReturn.created_at,
            ReturnItem.refund_cents,
            ReturnItem.tax_refund_cents,
            ReturnItem.quantity,
            SaleItem.cost_cents,
            SaleItem.quantity,
        )
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until, SaleReturn.currency == currency)
    )
    if store_id is not None:
        refunds = refunds.where(SaleReturn.store_id == store_id)
    returned: dict[date, int] = {}
    returned_cost: dict[date, int] = {}
    for created, refund, tax, quantity, cost, sold in db.execute(refunds):
        key = created.date() if isinstance(created, datetime) else date.fromisoformat(str(created)[:10])
        returned[key] = returned.get(key, 0) + int(refund) - int(tax)
        returned_cost[key] = returned_cost.get(key, 0) + (int(cost or 0) * int(quantity)) // max(int(sold), 1)
    points: list[TrendPoint] = []
    cursor = since.date()
    last = (until - timedelta(days=1)).date()
    while cursor <= last:
        net, cost = by_day.get(cursor, [0, 0])
        revenue = net - returned.get(cursor, 0)
        profit = revenue - (cost - returned_cost.get(cursor, 0))
        points.append(TrendPoint(day=cursor, revenue_cents=revenue, gross_profit_cents=profit))
        cursor += timedelta(days=1)
    return points


def _named(
    db: Session,
    statement,
    limit: int,
) -> list[NamedAmount]:
    rows = [NamedAmount(name=str(name or "Uncategorised"), cents=int(cents)) for name, cents in db.execute(statement)]
    rows.sort(key=lambda row: row.cents, reverse=True)
    return rows[:limit]


def _categories(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str
) -> list[NamedAmount]:
    statement = (
        select(Product.category, func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(Product.category)
    )
    return _named(db, statement, 8)


def _ranked_products(
    db: Session,
    since: datetime,
    until: datetime,
    store_id: uuid.UUID | None,
    currency: str,
    *,
    descending: bool,
    limit: int,
) -> list[NamedAmount]:
    label = func.coalesce(SaleItem.product_name, Product.name)
    amount = func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0)
    statement = (
        select(label, amount)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(label)
        .order_by(amount.desc() if descending else amount.asc())
        .limit(limit)
    )
    return [NamedAmount(name=str(name or "Uncategorised"), cents=int(cents)) for name, cents in db.execute(statement)]


def _hourly(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str, start: date, end: date
) -> tuple[list[HourPoint], str | None]:
    if (end - start).days > 31:
        return [], "Hourly sales are shown for periods of 31 days or less."
    hour = extract("hour", Sale.created_at)
    amount = func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0)
    statement = (
        select(hour, amount)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(hour)
    )
    found = {int(raw): int(cents) for raw, cents in db.execute(statement)}
    return [HourPoint(hour=index, revenue_cents=found.get(index, 0)) for index in range(24)], None


def _people(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str
) -> list[NamedAmount]:
    amount = func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0)
    statement = (
        select(User.full_name, amount)
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(User, User.id == Sale.cashier_id)
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(User.full_name)
        .order_by(amount.desc())
        .limit(8)
    )
    return [NamedAmount(name=str(name), cents=int(cents)) for name, cents in db.execute(statement)]


def _branches(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str
) -> list[NamedAmount]:
    if store_id is not None:
        return []
    amount = func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0)
    statement = (
        select(Store.name, amount)
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Store, Store.id == Sale.store_id)
        .where(*_sale_filters(since, until, None, currency))
        .group_by(Store.name)
        .order_by(amount.desc())
        .limit(12)
    )
    return [NamedAmount(name=str(name), cents=int(cents)) for name, cents in db.execute(statement)]


def _payments(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None, currency: str
) -> list[NamedAmount]:
    statement = (
        select(Sale.payment_method, func.coalesce(func.sum(Sale.total_cents), 0))
        .where(*_sale_filters(since, until, store_id, currency))
        .group_by(Sale.payment_method)
    )
    return _named(db, statement, 8)


def _sections(
    db: Session,
    profile: str,
    since: datetime,
    until: datetime,
    store_id: uuid.UUID | None,
    currency: str,
    sales: dict,
) -> list[AnalyticsSection]:
    enabled = {capability.value for capability in cached_settings(db).capabilities}
    sections: list[AnalyticsSection] = []

    def add(section_id: str, label: str, ready: bool, detail: str, cents: int | None = None) -> None:
        sections.append(
            AnalyticsSection(
                id=section_id,
                label=label,
                status="available" if ready else "unavailable",
                detail=detail,
                cents=cents,
            )
        )

    if profile == "grocery":
        ready = "fefo" in enabled
        expiring = 0
        if ready:
            horizon = datetime.now(UTC).date() + timedelta(days=14)
            query = select(func.coalesce(func.sum(BatchItem.quantity_remaining), 0)).where(
                BatchItem.expiry_date.is_not(None),
                BatchItem.expiry_date <= horizon,
                BatchItem.quantity_remaining > 0,
            )
            if store_id is not None:
                query = query.where(BatchItem.store_id == store_id)
            expiring = int(db.scalar(query) or 0)
        if ready:
            expiry_detail = f"{expiring} units expire within 14 days."
        else:
            expiry_detail = "Turn on expiry-first stock to see expiring batches."
        add("expiry", "Expiry exposure", ready, expiry_detail)
    if profile == "electronics_wholesale":
        ready = "serial_tracking" in enabled
        sold = 0
        if ready:
            query = (
                select(func.count())
                .select_from(SaleItem)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(*_sale_filters(since, until, store_id, currency), SaleItem.serial_number_id.is_not(None))
            )
            sold = int(db.scalar(query) or 0)
        add(
            "serials",
            "Serial-tracked sales",
            ready,
            f"{sold} serial-tracked units sold." if ready else "Turn on serial tracking to see unit-level sales.",
        )
    if profile in {"electronics_wholesale", "wholesale_retail"}:
        wholesale = db.scalar(
            select(func.coalesce(func.sum(Sale.total_cents), 0)).where(
                *_sale_filters(since, until, store_id, currency), Sale.sale_type == "WHOLESALE"
            )
        )
        add(
            "wholesale",
            "Wholesale sales",
            True,
            "Sale totals marked wholesale, including VAT, before refunds.",
            int(wholesale or 0),
        )
    if profile == "retail_fashion":
        ready = "variants_matrix" in enabled
        sold = 0
        if ready:
            query = (
                select(func.count())
                .select_from(SaleItem)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(*_sale_filters(since, until, store_id, currency), SaleItem.variant_attributes.is_not(None))
            )
            sold = int(db.scalar(query) or 0)
        detail = f"{sold} variant lines sold." if ready else "Turn on the size and colour matrix."
        add("variants", "Size and colour", ready, detail)
    if profile in {"restaurant", "cafe", "quick_service"}:
        add("tips", "Tips", True, "Tips collected on posted sales. Service charge is separate.", sales["tip_cents"])
        add(
            "service_charge",
            "Service charge",
            True,
            "Service charge included in the sale total.",
            sales["service_charge_cents"],
        )
        add(
            "kitchen",
            "Kitchen timing",
            False,
            "Preparation times stay in AI Insights. Deep Analytics does not treat them as financial results.",
        )
    if profile == "quick_service":
        add(
            "channels",
            "Delivery versus counter",
            False,
            "Posted sales do not store an order channel, so this split is not calculated.",
        )
    return sections


def overview(
    db: Session,
    *,
    start: date,
    end: date,
    store_id: uuid.UUID | None,
    currency: str,
    compare: bool,
) -> DeepOverview:
    since, until = bounds(start, end)
    sales = _sales_totals(db, since, until, store_id, currency)
    returns = _return_totals(db, since, until, store_id, currency)
    kpis, revenue, profit, estimated = _kpis(sales, returns)
    trend = _trend(db, since, until, store_id, currency)
    comparison = None
    if compare:
        span = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span - 1)
        prev_since, prev_until = bounds(previous_start, previous_end)
        prev_sales = _sales_totals(db, prev_since, prev_until, store_id, currency)
        prev_returns = _return_totals(db, prev_since, prev_until, store_id, currency)
        _, prev_revenue, prev_profit, _ = _kpis(prev_sales, prev_returns)
        comparison = Comparison(
            period_from=previous_start,
            period_to=previous_end,
            revenue_cents=prev_revenue,
            gross_profit_cents=prev_profit,
            transactions=prev_sales["transactions"],
            revenue_growth_bps=growth_bps(revenue, prev_revenue),
            profit_growth_bps=growth_bps(profit, prev_profit),
        )
    profile = cached_settings(db).business_profile
    hours, hourly_note = _hourly(db, since, until, store_id, currency, start, end)
    leading = _ranked_products(db, since, until, store_id, currency, descending=True, limit=8)
    leading_names = {row.name for row in leading}
    trailing = [
        row
        for row in _ranked_products(db, since, until, store_id, currency, descending=False, limit=5)
        if row.name not in leading_names
    ]
    return DeepOverview(
        currency=currency,
        period_from=start,
        period_to=end,
        generated_at=datetime.now(UTC),
        coverage=COVERAGE,
        cost_estimated=estimated,
        kpis=kpis,
        comparison=comparison,
        trend=trend,
        hourly=hours,
        hourly_note=hourly_note,
        categories=_categories(db, since, until, store_id, currency),
        products=leading,
        slow_products=trailing,
        payments=_payments(db, since, until, store_id, currency),
        cashiers=_people(db, since, until, store_id, currency),
        branches=_branches(db, since, until, store_id, currency),
        sections=_sections(db, profile, since, until, store_id, currency, sales),
        forecast=forecast_from_daily([point.revenue_cents for point in trend]),
    )


def export_csv(report: DeepOverview) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value", "quality", "definition"])
    for kpi in report.kpis:
        value = kpi.cents if kpi.cents is not None else kpi.count if kpi.count is not None else kpi.bps
        writer.writerow([kpi.key, "" if value is None else value, kpi.quality, kpi.definition])
    writer.writerow([])
    writer.writerow(["day", "revenue_cents", "gross_profit_cents"])
    for point in report.trend:
        writer.writerow([point.day.isoformat(), point.revenue_cents, point.gross_profit_cents])
    return buffer.getvalue()
