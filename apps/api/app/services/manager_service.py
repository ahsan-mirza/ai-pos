"""The manager's phone view: today's trading by branch and the things waiting on a manager."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.permissions import Permission
from app.models.cheque import Cheque
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.time_entry import TimeEntry
from app.models.user import User
from app.schemas.manager import (
    Attention,
    BranchToday,
    CreditHoldRow,
    ManagerDashboard,
    PendingTimeEntry,
    TopProduct,
)
from app.services import approval_service
from app.services.settings_service import business_currency

POSTED = ("completed", "partially_refunded", "refunded")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _day_start(now: datetime, offset_minutes: int) -> datetime:
    """Midnight in the viewer's timezone, as a UTC instant."""
    shift = timedelta(minutes=offset_minutes)
    local = now + shift
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - shift


def _sales(db: Session, since: datetime, until: datetime, store_id) -> list[Sale]:
    query = select(Sale).where(
        Sale.created_at >= since,
        Sale.created_at < until,
        Sale.is_quote_proforma.is_(False),
        Sale.status.in_(POSTED),
    )
    if store_id is not None:
        query = query.where(Sale.store_id == store_id)
    return list(db.scalars(query))


def _refunds(db: Session, since: datetime, until: datetime, store_id) -> dict:
    query = (
        select(SaleReturn.store_id, func.coalesce(func.sum(SaleReturn.total_refund_cents), 0))
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
        .group_by(SaleReturn.store_id)
    )
    if store_id is not None:
        query = query.where(SaleReturn.store_id == store_id)
    return {row[0]: int(row[1]) for row in db.execute(query)}


def dashboard(db: Session, principal: Principal, offset_minutes: int, now: datetime | None = None) -> ManagerDashboard:
    now = now or datetime.now(UTC)
    scope = principal.store_id
    start = _day_start(now, offset_minutes)
    sales = _sales(db, start, now, scope)
    refunds = _refunds(db, start, now, scope)
    stores = {row.id: row for row in db.scalars(select(Store))}

    per_store: dict = defaultdict(lambda: {"sales": 0, "revenue": 0, "last": None})
    hourly = [0] * 24
    for sale in sales:
        created = _aware(sale.created_at)
        row = per_store[sale.store_id]
        row["sales"] += 1
        row["revenue"] += sale.total_cents
        row["last"] = max(row["last"], created) if row["last"] else created
        hour = int((created - start).total_seconds() // 3600)
        if 0 <= hour < 24:
            hourly[hour] += sale.total_cents
    branches = []
    for store_id in set(per_store) | set(refunds):
        row = per_store[store_id]
        store = stores.get(store_id)
        refunded = refunds.get(store_id, 0)
        branches.append(
            BranchToday(
                store_id=store_id,
                store_code=store.code if store else "",
                store_name=store.name if store else "",
                sales=row["sales"],
                revenue_cents=row["revenue"],
                refunds_cents=refunded,
                net_cents=row["revenue"] - refunded,
                average_basket_cents=row["revenue"] // row["sales"] if row["sales"] else 0,
                last_sale_at=row["last"],
            )
        )
    branches.sort(key=lambda row: row.net_cents, reverse=True)

    yesterday_sales = _sales(db, start - timedelta(days=1), now - timedelta(days=1), scope)
    yesterday_refunds = _refunds(db, start - timedelta(days=1), now - timedelta(days=1), scope)
    yesterday = sum(sale.total_cents for sale in yesterday_sales) - sum(yesterday_refunds.values())

    top: list[TopProduct] = []
    if sales:
        rows = db.execute(
            select(
                SaleItem.product_id,
                func.sum(SaleItem.quantity * SaleItem.unit_factor),
                func.sum(SaleItem.line_total_cents),
            )
            .where(SaleItem.sale_id.in_([sale.id for sale in sales]))
            .group_by(SaleItem.product_id)
            .order_by(func.sum(SaleItem.line_total_cents).desc())
            .limit(5)
        ).all()
        names = {
            row.id: row.name for row in db.scalars(select(Product).where(Product.id.in_([item[0] for item in rows])))
        }
        top = [
            TopProduct(
                product_id=item[0],
                name=names.get(item[0], "Product"),
                quantity=int(item[1]),
                revenue_cents=int(item[2]),
            )
            for item in rows
        ]

    user = principal.user
    attention = Attention(
        approvals=approval_service.pending_count(db, user) if user else 0,
        timesheets=_pending_timesheets_count(db, scope) if principal.has(Permission.STAFF_MANAGE) else None,
        credit_holds=_credit_hold_count(db) if principal.has(Permission.CUSTOMERS_MANAGE) else None,
        cheques_to_deposit=_cheques_due(db, scope, (now + timedelta(minutes=offset_minutes)).date())
        if principal.has(Permission.CHEQUES_MANAGE)
        else None,
    )
    return ManagerDashboard(
        currency=business_currency(db),
        as_of=now,
        net_cents=sum(row.net_cents for row in branches),
        sales=len(sales),
        yesterday_net_cents=yesterday,
        hourly_cents=hourly,
        branches=branches,
        top_products=top,
        attention=attention,
    )


def _pending_timesheets_query(scope):
    query = select(TimeEntry).where(TimeEntry.status == "CLOSED")
    if scope is not None:
        query = query.where(TimeEntry.store_id == scope)
    return query


def _pending_timesheets_count(db: Session, scope) -> int:
    return int(db.scalar(select(func.count()).select_from(_pending_timesheets_query(scope).subquery())) or 0)


def _credit_hold_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.credit_hold.is_(True), Customer.is_active.is_(True))
        )
        or 0
    )


def _cheques_due(db: Session, scope, today) -> int:
    query = select(func.count()).select_from(Cheque).where(Cheque.status == "RECEIVED", Cheque.cheque_date <= today)
    if scope is not None:
        query = query.where(Cheque.store_id == scope)
    return int(db.scalar(query) or 0)


def pending_timesheets(db: Session, principal: Principal) -> list[PendingTimeEntry]:
    entries = list(
        db.scalars(_pending_timesheets_query(principal.store_id).order_by(TimeEntry.clock_in_at.desc()).limit(200))
    )
    users = {
        row.id: row.full_name
        for row in db.scalars(select(User).where(User.id.in_({entry.user_id for entry in entries}))).unique()
    }
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    rows = []
    for entry in entries:
        if entry.clock_out_at is None:
            continue
        worked = (
            int((_aware(entry.clock_out_at) - _aware(entry.clock_in_at)).total_seconds() // 60) - entry.break_minutes
        )
        rows.append(
            PendingTimeEntry(
                id=entry.id,
                user_name=users.get(entry.user_id, ""),
                store_code=stores.get(entry.store_id, ""),
                clock_in_at=entry.clock_in_at,
                clock_out_at=entry.clock_out_at,
                break_minutes=entry.break_minutes,
                worked_minutes=max(worked, 0),
            )
        )
    return rows


def credit_holds(db: Session) -> list[CreditHoldRow]:
    customers = db.scalars(
        select(Customer)
        .where(Customer.credit_hold.is_(True), Customer.is_active.is_(True))
        .order_by(Customer.current_balance_cents.desc())
        .limit(200)
    )
    return [
        CreditHoldRow(
            customer_id=row.id,
            name=row.company_name or row.name,
            balance_cents=row.current_balance_cents,
            credit_limit_cents=row.credit_limit_cents,
            reason=row.credit_hold_reason,
            manual=row.credit_hold_manual,
        )
        for row in customers
    ]
