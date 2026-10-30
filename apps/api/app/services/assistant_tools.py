"""The read-only report tools the AI assistant may call. Every answer is built from one of these; the assistant
never writes queries of its own, so it can only say what the reports say, scoped to the user's permissions and
branch."""

from __future__ import annotations

import calendar
import json
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.store import Store
from app.services import (
    credit_risk_service,
    expense_service,
    insights_service,
    management_reports,
    payables_service,
    replenishment_service,
    restaurant_insights_service,
    sales_velocity,
    weighed,
)
from app.services.settings_service import business_currency

POSTED = ("completed", "partially_refunded", "refunded")
PERIODS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_7_days",
    "last_30_days",
    "this_year",
    "last_year",
)
PERIOD_LABELS = {
    "today": ("today", "اليوم"),
    "yesterday": ("yesterday", "أمس"),
    "this_week": ("this week", "هذا الأسبوع"),
    "last_week": ("last week", "الأسبوع الماضي"),
    "this_month": ("this month", "هذا الشهر"),
    "last_month": ("last month", "الشهر الماضي"),
    "last_7_days": ("the last 7 days", "آخر 7 أيام"),
    "last_30_days": ("the last 30 days", "آخر 30 يومًا"),
    "this_year": ("this year", "هذه السنة"),
    "last_year": ("last year", "السنة الماضية"),
}
METHOD_LABELS = {
    "cash": ("Cash", "نقدًا"),
    "card": ("Card", "بطاقة"),
    "qr": ("QR", "رمز QR"),
    "transfer": ("Bank transfer", "تحويل بنكي"),
    "cheque": ("Cheque", "شيك"),
    "store_credit": ("Store credit", "رصيد المتجر"),
    "loyalty": ("Loyalty points", "نقاط الولاء"),
    "trade_in": ("Trade-in", "استبدال"),
    "on_account": ("On account", "على الحساب"),
    "channel": ("Delivery app", "تطبيق التوصيل"),
}


@dataclass
class Period:
    start: date
    end: date
    label_en: str
    label_ar: str

    def label(self, language: str) -> str:
        return self.label_ar if language == "ar" else self.label_en


def resolve_period(args: dict[str, Any], default: str, today: date) -> Period:
    """A named period, an explicit from/to range, or a calendar month (1-12) of this or last year."""
    start, end = args.get("from"), args.get("to")
    if isinstance(start, str) and isinstance(end, str):
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            first = last = None
        if first and last and first <= last and (last - first).days <= 400:
            text = f"{first.isoformat()} – {last.isoformat()}"
            # Isolate the dates so right-to-left text does not reorder their digits.
            return Period(first, last, text, f"من \u2066{first.isoformat()}\u2069 إلى \u2066{last.isoformat()}\u2069")
    month = args.get("month")
    if isinstance(month, int) and 1 <= month <= 12:
        year = today.year if month <= today.month else today.year - 1
        last_day = calendar.monthrange(year, month)[1]
        name = calendar.month_name[month]
        return Period(date(year, month, 1), date(year, month, last_day), f"{name} {year}", f"{name} {year}")
    name = args.get("period") if args.get("period") in PERIODS else default
    if name == "today":
        first = last = today
    elif name == "yesterday":
        first = last = today - timedelta(days=1)
    elif name == "this_week":
        first, last = today - timedelta(days=today.weekday()), today
    elif name == "last_week":
        first = today - timedelta(days=today.weekday() + 7)
        last = first + timedelta(days=6)
    elif name == "this_month":
        first, last = today.replace(day=1), today
    elif name == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        first = last.replace(day=1)
    elif name == "last_7_days":
        first, last = today - timedelta(days=6), today
    elif name == "this_year":
        first, last = today.replace(month=1, day=1), today
    elif name == "last_year":
        first, last = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    else:
        first, last = today - timedelta(days=29), today
    en, ar = PERIOD_LABELS[name]
    return Period(first, last, en, ar)


@dataclass
class ToolResult:
    tool: str
    title: str
    period: str | None
    facts: dict[str, Any]
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)


@dataclass
class ToolContext:
    db: Session
    principal: Principal
    today: date
    language: str
    currency: str = ""

    def money(self, cents: int) -> str:
        return f"{self.currency} {cents / 100:,.2f}"


def _bounds(period: Period) -> tuple[datetime, datetime]:
    return datetime.combine(period.start, time.min, UTC), datetime.combine(
        period.end + timedelta(days=1), time.min, UTC
    )


class BranchAccessDenied(Exception):
    """The caller named a branch their account cannot see. The query is not run."""


def _store_scope(ctx: ToolContext, args: dict[str, Any]) -> tuple[uuid.UUID | None, str | None]:
    """The user's own branch, or one branch in this store when the account covers every branch.

    A code that is not in this store, or a branch the user is not assigned to, is rejected.
    An unknown code does not widen the query to every branch.
    """
    code = args.get("store_code")
    named = code.strip() if isinstance(code, str) and code.strip() else None
    if ctx.principal.store_id is not None:
        store = ctx.db.get(Store, ctx.principal.store_id)
        if store is None or (named is not None and named.upper() != store.code.upper()):
            raise BranchAccessDenied
        return ctx.principal.store_id, store.code
    if named is not None:
        store = ctx.db.scalars(select(Store).where(func.upper(Store.code) == named.upper())).first()
        if store is None:
            raise BranchAccessDenied
        return store.id, store.code
    return None, None


def _sales(db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None) -> list[Sale]:
    query = select(Sale).where(
        Sale.created_at >= since, Sale.created_at < until, Sale.is_quote_proforma.is_(False), Sale.status.in_(POSTED)
    )
    if store_id is not None:
        query = query.where(Sale.store_id == store_id)
    return list(db.scalars(query))


def _title(base: str, store_code: str | None) -> str:
    return f"{base} · {store_code}" if store_code else base


def sales_summary(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "today", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    since, until = _bounds(period)
    sales = _sales(ctx.db, since, until, store_id)
    refunds_query = (
        select(SaleReturn.store_id, func.coalesce(func.sum(SaleReturn.total_refund_cents), 0))
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
        .group_by(SaleReturn.store_id)
    )
    if store_id is not None:
        refunds_query = refunds_query.where(SaleReturn.store_id == store_id)
    refunds = {row[0]: int(row[1]) for row in ctx.db.execute(refunds_query)}
    stores = {row.id: row.code for row in ctx.db.scalars(select(Store))}
    per_store: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0])
    for sale in sales:
        per_store[sale.store_id][0] += 1
        per_store[sale.store_id][1] += sale.total_cents
    gross = sum(sale.total_cents for sale in sales)
    refunded = sum(refunds.values())
    rows = []
    for key in sorted(set(per_store) | set(refunds), key=lambda item: -(per_store[item][1] - refunds.get(item, 0))):
        count, revenue = per_store[key]
        rows.append(
            [
                stores.get(key, ""),
                count,
                ctx.money(revenue),
                ctx.money(refunds.get(key, 0)),
                ctx.money(revenue - refunds.get(key, 0)),
            ]
        )
    return ToolResult(
        tool="sales_summary",
        title=_title("Sales summary", store_code),
        period=period.label(ctx.language),
        facts={
            "sales_count": len(sales),
            "gross_sales": ctx.money(gross),
            "refunds": ctx.money(refunded),
            "net_sales": ctx.money(gross - refunded),
            "average_basket": ctx.money(gross // len(sales)) if sales else ctx.money(0),
            "branches": len(rows),
        },
        columns=["Branch", "Sales", "Gross", "Refunds", "Net"],
        rows=rows,
    )


def top_products(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "last_30_days", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    since, until = _bounds(period)
    limit = min(max(int(args.get("limit") or 10), 1), 25)
    by_quantity = args.get("by") == "quantity"
    category = args.get("category")
    if not isinstance(category, str) or not category.strip():
        category = None
    ranked = sales_velocity.rank_products(
        ctx.db,
        since=since,
        until=until,
        store_id=store_id,
        category=category,
        limit=limit,
        by="quantity" if by_quantity else "revenue",
    )
    rows = [[row.name, row.sku, row.units, ctx.money(row.revenue_cents)] for row in ranked]
    facts: dict[str, Any] = {
        "ranked_by": "units sold" if by_quantity else "revenue",
        "products": [{"name": row[0], "units": row[2], "revenue": row[3]} for row in rows[:5]],
    }
    if category is not None:
        facts["category"] = category
    return ToolResult(
        tool="top_products",
        title=_title("Top products", store_code),
        period=period.label(ctx.language),
        facts=facts,
        columns=["Product", "SKU", "Units", "Revenue"],
        rows=rows,
    )


def sales_by_category(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "last_30_days", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    since, until = _bounds(period)
    units = func.sum(SaleItem.quantity * SaleItem.unit_factor)
    revenue = func.sum(SaleItem.line_total_cents)
    query = (
        select(Product.category, units, revenue)
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(Product.category)
        .order_by(revenue.desc())
    )
    if store_id is not None:
        query = query.where(Sale.store_id == store_id)
    data = ctx.db.execute(query).all()
    total = sum(int(row[2] or 0) for row in data) or 1
    rows = [
        [category or "Uncategorised", int(qty or 0), ctx.money(int(cents or 0)), f"{int(cents or 0) * 100 // total}%"]
        for category, qty, cents in data
    ]
    return ToolResult(
        tool="sales_by_category",
        title=_title("Sales by category", store_code),
        period=period.label(ctx.language),
        facts={
            "categories": [{"category": row[0], "units": row[1], "revenue": row[2], "share": row[3]} for row in rows]
        },
        columns=["Category", "Units", "Revenue", "Share"],
        rows=rows,
    )


def payment_mix(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "today", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    since, until = _bounds(period)
    query = (
        select(SaleTender.method, func.count(), func.sum(SaleTender.amount_cents))
        .join(Sale, SaleTender.sale_id == Sale.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(SaleTender.method)
        .order_by(func.sum(SaleTender.amount_cents).desc())
    )
    if store_id is not None:
        query = query.where(Sale.store_id == store_id)
    data = ctx.db.execute(query).all()
    total = sum(int(row[2] or 0) for row in data) or 1
    index = 1 if ctx.language == "ar" else 0
    rows = [
        [
            METHOD_LABELS.get(method, (method, method))[index],
            int(count),
            ctx.money(int(cents or 0)),
            f"{int(cents or 0) * 100 // total}%",
        ]
        for method, count, cents in data
    ]
    return ToolResult(
        tool="payment_mix",
        title=_title("Payment methods", store_code),
        period=period.label(ctx.language),
        facts={"methods": [{"method": row[0], "payments": row[1], "amount": row[2], "share": row[3]} for row in rows]},
        columns=["Method", "Payments", "Amount", "Share"],
        rows=rows,
    )


def staff_performance(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "this_month", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    report = management_reports.staff_sales(ctx.db, start=period.start, end=period.end, store_id=store_id)
    rows = [
        [
            row.name,
            row.sales,
            ctx.money(row.revenue_cents),
            ctx.money(row.gross_profit_cents),
            f"{row.gross_margin_bps / 100:.1f}%",
            ctx.money(row.average_basket_cents),
        ]
        for row in sorted(report.rows, key=lambda item: -item.revenue_cents)
    ]
    return ToolResult(
        tool="staff_performance",
        title=_title("Sales by staff", store_code),
        period=period.label(ctx.language),
        facts={"staff": [{"name": row[0], "sales": row[1], "revenue": row[2], "margin": row[4]} for row in rows[:10]]},
        columns=["Staff", "Sales", "Revenue", "Gross profit", "Margin", "Avg basket"],
        rows=rows,
    )


def profit_and_loss(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "this_month", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    report = management_reports.pnl(ctx.db, start=period.start, end=period.end, store_id=store_id)
    total = report.total
    rows = [
        [
            row.store_code or "All",
            ctx.money(row.revenue_cents),
            ctx.money(row.gross_profit_cents),
            f"{row.gross_margin_bps / 100:.1f}%",
            ctx.money(row.operating_expenses_cents),
            ctx.money(row.operating_profit_cents),
        ]
        for row in report.by_store
    ]
    return ToolResult(
        tool="profit_and_loss",
        title=_title("Profit and loss", store_code),
        period=period.label(ctx.language),
        facts={
            "revenue": ctx.money(total.revenue_cents),
            "cost_of_goods": ctx.money(total.cogs_cents),
            "gross_profit": ctx.money(total.gross_profit_cents),
            "gross_margin": f"{total.gross_margin_bps / 100:.1f}%",
            "operating_expenses": ctx.money(total.operating_expenses_cents),
            "operating_profit": ctx.money(total.operating_profit_cents),
            "cost_estimated": report.cost_estimated,
        },
        columns=["Branch", "Revenue", "Gross profit", "Margin", "Expenses", "Operating profit"],
        rows=rows,
    )


def stock_value(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = management_reports.valuation(ctx.db, store_id=store_id)
    rows = [
        [group.key, group.units, ctx.money(group.cost_value_cents), ctx.money(group.retail_value_cents)]
        for group in report.by_store
    ]
    return ToolResult(
        tool="stock_value",
        title=_title("Stock value", store_code),
        period=None,
        facts={
            "units": report.units,
            "cost_value": ctx.money(report.cost_value_cents),
            "retail_value": ctx.money(report.retail_value_cents),
            "top_categories": [
                {"category": group.key, "cost_value": ctx.money(group.cost_value_cents)}
                for group in report.by_category[:5]
            ],
        },
        columns=["Branch", "Units", "At cost", "At retail"],
        rows=rows,
    )


def slow_stock(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    named_slow = "slow_days" in args
    named_dead = "dead_days" in args
    slow_days = min(max(int(args.get("slow_days") or sales_velocity.SLOW_DAYS), 1), 3649)
    dead_days = min(max(int(args.get("dead_days") or sales_velocity.DEAD_DAYS), 2), 3650)
    if dead_days <= slow_days:
        # A question that names only the dead window ("not sold in 30 days") keeps that window.
        if named_dead and not named_slow:
            slow_days = dead_days - 1
        else:
            dead_days = slow_days + 1
    report = management_reports.aged_stock(
        ctx.db, store_id=store_id, slow_days=slow_days, dead_days=dead_days
    )
    focus = "DEAD" if named_dead and not named_slow else "SLOW" if named_slow and not named_dead else None
    chosen = [row for row in report.rows if focus is None or row.status == focus]
    ranked = sorted(chosen, key=lambda row: -row.holding_cost_month_cents)[:15]
    rows = [
        [
            row.name,
            row.store_code,
            row.on_hand,
            ctx.money(row.cost_value_cents),
            row.days_since_sale if row.days_since_sale is not None else "never",
            row.status,
            ctx.money(row.holding_cost_month_cents),
            "cost review"
            if row.review_required
            else (
                f"{ctx.money(row.suggested_price_cents)} (-{row.markdown_pct}%)"
                if row.suggested_price_cents
                else "at floor"
            ),
        ]
        for row in ranked
    ]
    return ToolResult(
        tool="slow_stock",
        title=_title("Slow and dead stock", store_code),
        period=None,
        facts={
            "slow_after_days": report.slow_days,
            "dead_after_days": report.dead_days,
            "cover_slow_days": sales_velocity.COVER_SLOW_DAYS,
            "velocity_window_days": sales_velocity.VELOCITY_WINDOW_DAYS,
            "needs_cost_review": sum(1 for row in chosen if row.review_required),
            "slow_value": ctx.money(report.slow_value_cents),
            "dead_value": ctx.money(report.dead_value_cents),
            "items": len(report.rows),
            "holding_cost_per_month": ctx.money(report.holding_cost_month_cents),
            "carrying_rate": f"{report.carrying_rate_bps / 100:g}% a year",
        },
        columns=["Product", "Branch", "On hand", "At cost", "Days since sale", "Status", "Holding / month", "Clear at"],
        rows=rows,
    )


def _days(args: dict[str, Any], default: int, low: int, high: int) -> int:
    try:
        return min(max(int(args.get("days") or default), low), high)
    except (TypeError, ValueError):
        return default


def anomalies(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = insights_service.anomalies(ctx.db, ctx.principal, days=_days(args, 30, 7, 365), store_id=store_id)
    rows = [
        [
            item.severity,
            item.user_name,
            item.kind.replace("_", " ").lower(),
            item.count,
            f"{item.rate:.1f} / 100" if item.rate is not None else ctx.money(item.amount_cents or 0),
            f"{item.peer_rate:.1f} / 100" if item.peer_rate is not None else "",
            item.summary,
        ]
        for item in report.anomalies[:15]
    ]
    top = report.anomalies[0] if report.anomalies else None
    return ToolResult(
        tool="anomalies",
        title=_title(f"Unusual activity · last {report.days} days", store_code),
        period=None,
        facts={
            "days": report.days,
            "cashiers_compared": report.peers,
            "high": sum(1 for item in report.anomalies if item.severity == "HIGH"),
            "medium": sum(1 for item in report.anomalies if item.severity == "MEDIUM"),
            "top": top.summary if top else None,
        },
        columns=["Severity", "Cashier", "Signal", "Count", "Rate / amount", "Team median", "Why"],
        rows=rows,
    )


def price_suggestions(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = insights_service.pricing(ctx.db, ctx.principal, store_id=store_id, limit=200)
    action = args.get("action")
    if action not in (None, "RAISE_TO_FLOOR", "RAISE_ON_DEMAND", "EXPIRY_MARKDOWN", "CLEARANCE"):
        action = None
    items = [item for item in report.suggestions if action is None or item.action == action]
    rows = [
        [
            item.name,
            item.action.replace("_", " ").lower(),
            ctx.money(item.price_cents),
            ctx.money(item.suggested_price_cents),
            f"{item.change_pct:+d}%",
            item.reason,
        ]
        for item in items[:15]
    ]
    first = items[0] if items else None
    return ToolResult(
        tool="price_suggestions",
        title=_title("Fast movers" if action == "RAISE_ON_DEMAND" else "Price suggestions", store_code),
        period=None,
        facts={
            "total": report.counts.get(action, 0) if action else len(report.suggestions),
            "filtered_action": action,
            "raise_to_floor": report.counts.get("RAISE_TO_FLOOR", 0),
            "raise_on_demand": report.counts.get("RAISE_ON_DEMAND", 0),
            "expiry_markdown": report.counts.get("EXPIRY_MARKDOWN", 0),
            "clearance": report.counts.get("CLEARANCE", 0),
            "first": first.reason if first else None,
            "first_product": first.name if first else None,
        },
        columns=["Product", "Action", "Now", "Suggested", "Change", "Why"],
        rows=rows,
    )


def shrink_report(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = insights_service.shrink(ctx.db, ctx.principal, days=_days(args, 90, 7, 730), store_id=store_id)
    rows = [
        [
            row.name,
            row.category,
            weighed.format_weight(row.lost_units) if row.sold_by_weight else row.lost_units,
            ctx.money(row.lost_cents),
            row.events,
            f"{row.shrink_rate_bps / 100:.1f}%",
        ]
        for row in report.top_products
    ]
    days = (report.until - report.since).days
    return ToolResult(
        tool="shrink_report",
        title=_title(f"Shrink · last {days} days", store_code),
        period=None,
        facts={
            "days": days,
            "lost": ctx.money(report.lost_cents),
            "found": ctx.money(report.found_cents),
            "net": ctx.money(report.net_cents),
            "share_of_sales": f"{report.shrink_bps / 100:.1f}%",
            "main_reason": report.by_reason[0].label if report.by_reason else None,
            "worst_category": report.by_category[0].label if report.by_category else None,
            "hotspots": [hotspot.summary for hotspot in report.hotspots[:3]],
        },
        columns=["Product", "Category", "Units lost", "At cost", "Events", "Of what left the shelf"],
        rows=rows,
    )


def kitchen_performance(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = restaurant_insights_service.kitchen(ctx.db, ctx.principal, store_id=store_id)
    rows = [
        [
            station.station_name,
            station.store_code,
            station.tickets_28d,
            f"{station.median_minutes:g} min" if station.median_minutes is not None else "",
            f"{station.p90_minutes:g} min" if station.p90_minutes is not None else "",
            f"{station.late_share_bps / 100:.0f}%",
            station.open_tickets,
            f"{station.wait_now_minutes:g} min" if station.wait_now_minutes is not None else "",
        ]
        for station in report.stations
    ]
    slowest = max(report.stations, key=lambda row: row.median_minutes or 0, default=None)
    return ToolResult(
        tool="kitchen_performance",
        title=_title("Kitchen prep times · last 28 days", store_code),
        period=None,
        facts={
            "stations": len(report.stations),
            "late_after_minutes": report.late_minutes,
            "at_risk_now": sum(1 for station in report.stations for ticket in station.live if ticket.at_risk),
            "slowest": (
                {"name": slowest.station_name, "median": slowest.median_minutes, "late_share": slowest.late_share_bps}
                if slowest and slowest.median_minutes is not None
                else None
            ),
        },
        columns=["Station", "Branch", "Tickets", "Median", "Slowest 10%", "Late", "Open now", "Wait now"],
        rows=rows,
    )


def table_turnaround(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = restaurant_insights_service.tables(ctx.db, ctx.principal, store_id=store_id, days=_days(args, 28, 7, 365))
    rows = [
        [row.label, row.store_code, row.seats, row.turns, row.turns_per_day, row.median_minutes or "",
         ctx.money(row.revenue_per_hour_cents)]
        for row in report.tables[:15]
    ]  # fmt: skip
    return ToolResult(
        tool="table_turnaround",
        title=_title(f"Table turnaround · last {report.days} days", store_code),
        period=None,
        facts={
            "days": report.days,
            "dine_in_orders": report.dine_in_orders,
            "median_minutes": report.median_minutes,
            "by_party": {item.label: item.median_minutes for item in report.by_party},
            "open_tables": len(report.open_tables),
            "lingering": sum(1 for row in report.open_tables if row.lingering),
            "best_table": report.tables[0].label if report.tables else None,
        },
        columns=["Table", "Branch", "Seats", "Turns", "Turns / day", "Median minutes", "Revenue / hour"],
        rows=rows,
    )


def upsell_pairs(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    report = restaurant_insights_service.upsell(ctx.db, ctx.principal, product_ids=[], store_id=store_id, limit=15)
    rows = [
        [pair.product_name, pair.add_on_name, f"{pair.confidence_bps / 100:.0f}%", f"{pair.lift:g}x", pair.together]
        for pair in report.pairs
    ]
    return ToolResult(
        tool="upsell_pairs",
        title=_title("Items ordered together · last 90 days", store_code),
        period=None,
        facts={
            "baskets": report.baskets,
            "pairs": len(report.pairs),
            "top": report.pairs[0].pitch if report.pairs else None,
        },
        columns=["When they order", "Suggest", "Takes it", "Lift", "Orders together"],
        rows=rows,
    )


def credit_risk(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    portfolio = credit_risk_service.portfolio(ctx.db)
    grades: dict[str, int] = defaultdict(int)
    for row in portfolio:
        grades[row.grade] += 1
    rows = [
        [
            row.name,
            row.grade,
            row.score,
            ctx.money(row.balance_cents),
            row.factors[0].detail if row.factors else "no risk factors",
            row.recommendation,
        ]
        for row in portfolio[:15]
    ]
    riskiest = portfolio[0] if portfolio else None
    return ToolResult(
        tool="credit_risk",
        title="Credit risk by account",
        period=None,
        facts={
            "accounts": len(portfolio),
            "by_grade": dict(sorted(grades.items())),
            "high_risk_accounts": grades.get("D", 0) + grades.get("E", 0),
            "riskiest": (
                {
                    "name": riskiest.name,
                    "grade": riskiest.grade,
                    "score": riskiest.score,
                    "reason": riskiest.factors[0].detail if riskiest.factors else "",
                }
                if riskiest
                else None
            ),
        },
        columns=["Customer", "Grade", "Score", "Owes", "Main reason", "Recommendation"],
        rows=rows,
    )


def reorder_forecast(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    store_id, store_code = _store_scope(ctx, args)
    if store_id is None:
        store = ctx.db.scalar(select(Store).where(Store.is_active.is_(True)).order_by(Store.is_warehouse, Store.code))
        store_id, store_code = (store.id, store.code) if store is not None else (None, None)
    run = replenishment_service.latest_run(ctx.db, store_id) if store_id is not None else None
    pending = [row for row in (run.suggestions if run else []) if row.status == "PENDING"]
    ranked = sorted(pending, key=lambda row: -row.suggested_qty * row.unit_cost_cents)[:15]
    rows = [
        [
            row.product_name,
            row.forecast_method_label or "Weighted average",
            f"{row.daily_rate:.1f}",
            f"{round(row.forecast_accuracy * 100)}%" if row.forecast_accuracy is not None else "n/a",
            row.on_hand,
            row.suggested_qty,
            row.supplier_name or (f"from {row.from_store_code}" if row.from_store_code else ""),
        ]
        for row in ranked
    ]
    tested = [row.forecast_accuracy for row in pending if row.forecast_accuracy is not None]
    return ToolResult(
        tool="reorder_forecast",
        title=_title("Reorder forecast", store_code),
        period=None,
        facts={
            "run_at": run.created_at.date().isoformat() if run else None,
            "lines_to_reorder": len(pending),
            "purchase_value": ctx.money(run.purchase_value_cents) if run else ctx.money(0),
            "average_accuracy": f"{round(sum(tested) / len(tested) * 100)}%" if tested else None,
            "trending_up": sum(1 for row in pending if (row.trend_pct_week or 0) > 0),
        },
        columns=["Product", "Model", "Per day", "Backtest accuracy", "On hand", "Order", "From"],
        rows=rows,
    )


def customer_balances(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    customers = list(
        ctx.db.scalars(
            select(Customer)
            .where(Customer.current_balance_cents > 0, Customer.is_active.is_(True))
            .order_by(Customer.current_balance_cents.desc())
            .limit(15)
        )
    )
    total = int(
        ctx.db.scalar(
            select(func.coalesce(func.sum(Customer.current_balance_cents), 0)).where(Customer.current_balance_cents > 0)
        )
        or 0
    )
    rows = [
        [
            row.company_name or row.name,
            ctx.money(row.current_balance_cents),
            ctx.money(row.credit_limit_cents),
            "yes" if row.credit_hold else "",
        ]
        for row in customers
    ]
    return ToolResult(
        tool="customer_balances",
        title="Customer balances (receivables)",
        period=None,
        facts={
            "total_receivable": ctx.money(total),
            "customers_owing": len(rows),
            "on_credit_hold": sum(1 for row in customers if row.credit_hold),
        },
        columns=["Customer", "Owes", "Credit limit", "On hold"],
        rows=rows,
    )


def payables_due(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    summary = payables_service.summary(ctx.db)
    owed = sorted((row for row in summary.suppliers if row.outstanding_cents), key=lambda row: -row.outstanding_cents)
    rows = [
        [row.name, ctx.money(row.outstanding_cents), ctx.money(row.overdue_cents), ctx.money(row.due_7d_cents)]
        for row in owed[:15]
    ]
    return ToolResult(
        tool="payables_due",
        title="Owed to suppliers",
        period=None,
        facts={
            "outstanding": ctx.money(summary.outstanding_cents),
            "overdue": ctx.money(summary.overdue_cents),
            "due_in_7_days": ctx.money(summary.due_7d_cents),
            "cheques_not_cleared": ctx.money(summary.cheques_issued_cents),
        },
        columns=["Supplier", "Outstanding", "Overdue", "Due in 7 days"],
        rows=rows,
    )


def expenses_by_category(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    period = resolve_period(args, "this_month", ctx.today)
    store_id, store_code = _store_scope(ctx, args)
    totals: dict[str, int] = defaultdict(int)
    for expense in expense_service.period_expenses(ctx.db, period.start, period.end, store_id):
        totals[expense.category] += expense.total_cents
    rows = [
        [category.replace("_", " ").title(), ctx.money(cents)]
        for category, cents in sorted(totals.items(), key=lambda item: -item[1])
    ]
    return ToolResult(
        tool="expenses_by_category",
        title=_title("Expenses by category", store_code),
        period=period.label(ctx.language),
        facts={
            "total": ctx.money(sum(totals.values())),
            "categories": [{"category": row[0], "amount": row[1]} for row in rows],
        },
        columns=["Category", "Amount"],
        rows=rows,
    )


@dataclass
class Tool:
    name: str
    description: str
    permission: Permission
    run: Callable[[ToolContext, dict[str, Any]], ToolResult]
    periodic: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "sales_summary",
            "Net sales, number of sales, refunds and average basket, by branch.",
            Permission.PORTAL_REPORTS_READ,
            sales_summary,
        ),
        Tool(
            "top_products",
            "Best-selling products ranked by revenue or by units sold.",
            Permission.PORTAL_REPORTS_READ,
            top_products,
            extra={
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                "by": {"type": "string", "enum": ["revenue", "quantity"]},
                "category": {"type": "string"},
            },
        ),
        Tool(
            "sales_by_category",
            "Units and revenue per product category (phones, accessories, ...).",
            Permission.PORTAL_REPORTS_READ,
            sales_by_category,
        ),
        Tool(
            "payment_mix",
            "How customers paid: cash, card, QR, transfer, cheque, store credit.",
            Permission.PORTAL_REPORTS_READ,
            payment_mix,
        ),
        Tool(
            "staff_performance",
            "Sales, revenue, gross profit and margin per salesperson.",
            Permission.PORTAL_REPORTS_READ,
            staff_performance,
        ),
        Tool(
            "profit_and_loss",
            "Revenue, cost of goods, gross profit, expenses and operating profit.",
            Permission.PORTAL_REPORTS_READ,
            profit_and_loss,
        ),
        Tool(
            "stock_value",
            "Units on hand and stock value at cost and retail, by branch.",
            Permission.PORTAL_REPORTS_READ,
            stock_value,
            periodic=False,
        ),
        Tool(
            "slow_stock",
            "Slow-moving and dead stock: items not selling, with the cash tied up in them.",
            Permission.PORTAL_REPORTS_READ,
            slow_stock,
            periodic=False,
            extra={
                "slow_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                "dead_days": {"type": "integer", "minimum": 2, "maximum": 3650},
            },
        ),
        Tool(
            "anomalies",
            "Unusual cashier activity: voids, no-sale drawer opens, refunds, price overrides and cash shortages "
            "compared with the rest of the team.",
            Permission.AUDIT_READ,
            anomalies,
            periodic=False,
            extra={"days": {"type": "integer", "minimum": 7, "maximum": 365}},
        ),
        Tool(
            "price_suggestions",
            "Prices to change: below the margin floor, demand outrunning stock, expiring batches to mark down, "
            "and dead stock to clear. Fast movers are the demand suggestions, not the best-seller ranking.",
            Permission.PORTAL_REPORTS_READ,
            price_suggestions,
            periodic=False,
            extra={
                "action": {
                    "type": "string",
                    "enum": ["RAISE_TO_FLOOR", "RAISE_ON_DEMAND", "EXPIRY_MARKDOWN", "CLEARANCE"],
                }
            },
        ),
        Tool(
            "shrink_report",
            "Shrink: stock lost to damage, expiry, theft and count differences, at cost and as a share of sales.",
            Permission.PORTAL_REPORTS_READ,
            shrink_report,
            periodic=False,
            extra={"days": {"type": "integer", "minimum": 7, "maximum": 730}},
        ),
        Tool(
            "kitchen_performance",
            "Kitchen prep times per station, share of late tickets, and the wait a new ticket faces now.",
            Permission.PORTAL_REPORTS_READ,
            kitchen_performance,
            periodic=False,
        ),
        Tool(
            "table_turnaround",
            "How long dine-in tables are held (by party size), turns per day and revenue per table-hour.",
            Permission.PORTAL_REPORTS_READ,
            table_turnaround,
            periodic=False,
            extra={"days": {"type": "integer", "minimum": 7, "maximum": 365}},
        ),
        Tool(
            "upsell_pairs",
            "Items guests usually order together, for waiter upsell prompts and combos.",
            Permission.PORTAL_REPORTS_READ,
            upsell_pairs,
            periodic=False,
        ),
        Tool(
            "customer_balances",
            "What wholesale customers owe (receivables) and who is on credit hold.",
            Permission.CUSTOMERS_MANAGE,
            customer_balances,
            periodic=False,
        ),
        Tool(
            "credit_risk",
            "Credit risk grade (A-E) and score per wholesale account, with the reasons and a recommendation.",
            Permission.CUSTOMERS_MANAGE,
            credit_risk,
            periodic=False,
        ),
        Tool(
            "reorder_forecast",
            "What to reorder from the latest replenishment run: forecast model, accuracy and quantities.",
            Permission.REPLENISHMENT_MANAGE,
            reorder_forecast,
            periodic=False,
        ),
        Tool(
            "payables_due",
            "What the business owes suppliers: outstanding, overdue and due this week.",
            Permission.PAYABLES_MANAGE,
            payables_due,
            periodic=False,
        ),
        Tool(
            "expenses_by_category",
            "Expenses (rent, utilities, salaries, ...) by category.",
            Permission.EXPENSES_MANAGE,
            expenses_by_category,
        ),
    )
}


def available(principal: Principal) -> list[Tool]:
    return [tool for tool in TOOLS.values() if principal.has(tool.permission)]


def json_schema(tool: Tool) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    if tool.periodic:
        properties["period"] = {"type": "string", "enum": list(PERIODS)}
        properties["month"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": 12,
            "description": "A calendar month instead of a period.",
        }
        properties["from"] = {"type": "string", "description": "Start date YYYY-MM-DD, with 'to', instead of a period."}
        properties["to"] = {"type": "string", "description": "End date YYYY-MM-DD."}
    properties["store_code"] = {"type": "string", "description": "Limit to one branch, by its code (e.g. DT-01)."}
    properties.update(tool.extra)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {"type": "object", "properties": properties, "additionalProperties": False},
        },
    }


# The model is not allowed to name a store, a branch, or a query. These keys are dropped before a tool runs.
_REJECTED_ARGUMENTS = frozenset(
    {"tenant_id", "branch_id", "store_id", "user_id", "database", "database_url", "sql", "query"}
)


def accepted_args(tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
    """Keeps only the arguments declared for this tool. Tenant and branch ids never pass through."""
    if not isinstance(args, dict):
        return {}
    schema = json_schema(tool)["function"]["parameters"]["properties"]
    clean: dict[str, Any] = {}
    for key, value in args.items():
        if key in _REJECTED_ARGUMENTS or key not in schema:
            continue
        spec = schema[key]
        if spec.get("type") == "integer":
            if isinstance(value, bool):
                continue
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if not isinstance(value, int):
                continue
            if "minimum" in spec and value < spec["minimum"]:
                continue
            if "maximum" in spec and value > spec["maximum"]:
                continue
        elif spec.get("type") == "string":
            if not isinstance(value, str) or ("enum" in spec and value not in spec["enum"]):
                continue
            if key in {"from", "to"}:
                try:
                    date.fromisoformat(value)
                except ValueError:
                    continue
            if key == "store_code":
                value = value.strip()[:32]
                if not value:
                    continue
        clean[key] = value
    return clean


def _dump_result(result: ToolResult) -> str:
    return json.dumps(
        {
            "tool": result.tool,
            "title": result.title,
            "period": result.period,
            "facts": result.facts,
            "columns": result.columns,
            "rows": result.rows,
        },
        default=str,
    )


def _load_result(raw: str) -> ToolResult | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tool"), str):
        return None
    return ToolResult(
        tool=data["tool"],
        title=str(data.get("title") or ""),
        period=data.get("period") if isinstance(data.get("period"), str) else None,
        facts=data.get("facts") if isinstance(data.get("facts"), dict) else {},
        columns=list(data.get("columns") or []),
        rows=list(data.get("rows") or []),
    )


def run(
    db: Session, principal: Principal, name: str, args: dict[str, Any], *, language: str, today: date
) -> ToolResult | None:
    from app.core.config import get_settings
    from app.services import assistant_scope

    tool = TOOLS.get(name)
    if tool is None or not principal.has(tool.permission):
        return None
    args = accepted_args(tool, args)
    ctx = ToolContext(db=db, principal=principal, today=today, language=language, currency=business_currency(db))
    branch_id, _store_code = _store_scope(ctx, args)
    tenant_id = assistant_scope.require_tenant_id()
    cache_key = assistant_scope.report_cache_key(
        tenant_id, str(branch_id) if branch_id is not None else "all", principal, tool.name, args
    )
    cached = assistant_scope.read_cached_report(cache_key)
    if cached is not None:
        loaded = _load_result(cached)
        if loaded is not None:
            return loaded
    result = tool.run(ctx, args)
    assistant_scope.store_cached_report(cache_key, _dump_result(result), get_settings().assistant_cache_ttl_seconds)
    return result
