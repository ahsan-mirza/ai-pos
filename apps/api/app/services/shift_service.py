"""Register shifts: opened and closed offline by registers, reconciled here into X / Z reports."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.models.device import Device
from app.models.payment_intent import PaymentIntent
from app.models.repair_ticket import RepairDeposit
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.shift import CashMovement, RegisterShift
from app.models.store import Store
from app.models.user import User
from app.schemas.shifts import (
    CashMovementOut,
    CashMovementPayload,
    RegisterShiftPayload,
    ServerTips,
    ShiftOut,
    ShiftReport,
    TipReport,
)
from app.services.numbering import accept_register_number, next_server_number
from app.services.settings_service import business_currency
from app.services.sync_service import SyncContext, register_handler
from app.services.sync_validation import parse_payload, require_store

POSTED = ("completed", "partially_refunded", "refunded")


def _aware(value):
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=UTC)


def _user(db: Session, user_id: uuid.UUID, label: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise SyncRejected(f"{label} does not exist.")
    return user


def build_report(db: Session, shift: RegisterShift) -> ShiftReport:
    sales = select(Sale.id).where(Sale.shift_id == shift.id, Sale.status.in_(POSTED), Sale.is_quote_proforma.is_(False))
    count, total, tax, tips, service = db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_cents), 0),
            func.coalesce(func.sum(Sale.tax_cents), 0),
            func.coalesce(func.sum(Sale.tip_cents), 0),
            func.coalesce(func.sum(Sale.service_charge_cents), 0),
        ).where(Sale.id.in_(sales))
    ).one()
    tenders: dict[str, int] = defaultdict(int)
    for method, amount in db.execute(
        select(SaleTender.method, func.sum(SaleTender.amount_cents))
        .where(SaleTender.sale_id.in_(sales))
        .group_by(SaleTender.method)
    ):
        tenders[method] += int(amount)
    # Foreign cash goes into its own currency's drawer; the business-currency change handed back leaves this one.
    foreign_cash: dict[str, int] = defaultdict(int)
    foreign_value = 0
    foreign_change = 0
    for currency, received, amount, change in db.execute(
        select(
            SaleTender.currency,
            func.sum(SaleTender.foreign_amount_cents),
            func.sum(SaleTender.amount_cents),
            func.coalesce(func.sum(SaleTender.change_cents), 0),
        )
        .where(SaleTender.sale_id.in_(sales), SaleTender.method == "cash", SaleTender.currency.is_not(None))
        .group_by(SaleTender.currency)
    ):
        foreign_cash[currency] += int(received or 0)
        foreign_value += int(amount or 0)
        foreign_change += int(change or 0)
    returns = select(SaleReturn.id).where(SaleReturn.shift_id == shift.id)
    returns_count, refunds_total = db.execute(
        select(func.count(SaleReturn.id), func.coalesce(func.sum(SaleReturn.total_refund_cents), 0)).where(
            SaleReturn.id.in_(returns)
        )
    ).one()
    refund_tenders: dict[str, int] = defaultdict(int)
    for method, amount in db.execute(
        select(ReturnTender.method, func.sum(ReturnTender.amount_cents))
        .where(ReturnTender.return_id.in_(returns))
        .group_by(ReturnTender.method)
    ):
        refund_tenders[method] += int(amount)
    movements: dict[str, int] = defaultdict(int)
    no_sale = 0
    for kind, amount, events in db.execute(
        select(CashMovement.kind, func.sum(CashMovement.amount_cents), func.count(CashMovement.id))
        .where(CashMovement.shift_id == shift.id)
        .group_by(CashMovement.kind)
    ):
        movements[kind] += int(amount)
        if kind == "NO_SALE":
            no_sale = int(events)
    # Cash taken for a repair before it is invoiced is in the drawer now. Crediting it on the invoice
    # uses a deposit tender, which is not cash, so it is counted here and not again with the sale.
    deposit_in = int(
        db.scalar(
            select(func.coalesce(func.sum(RepairDeposit.amount_cents), 0)).where(
                RepairDeposit.shift_id == shift.id, RepairDeposit.method == "cash"
            )
        )
        or 0
    )
    deposit_out = int(
        db.scalar(
            select(func.coalesce(func.sum(RepairDeposit.amount_cents), 0)).where(
                RepairDeposit.refund_shift_id == shift.id,
                RepairDeposit.method == "cash",
                RepairDeposit.status == "REFUNDED",
            )
        )
        or 0
    )
    expected = (
        shift.opening_float_cents
        + tenders.get("cash", 0)
        - foreign_value
        - foreign_change
        - refund_tenders.get("cash", 0)
        + movements.get("PAY_IN", 0)
        - movements.get("PAY_OUT", 0)
        - movements.get("CASH_DROP", 0)
        + deposit_in
        - deposit_out
    )
    return ShiftReport(
        sales_count=int(count),
        sales_total_cents=int(total),
        tax_cents=int(tax),
        tenders=dict(tenders),
        on_account_cents=max(0, int(total) + int(tips) - sum(tenders.values())),
        returns_count=int(returns_count),
        refunds_total_cents=int(refunds_total),
        refund_tenders=dict(refund_tenders),
        pay_in_cents=movements.get("PAY_IN", 0),
        pay_out_cents=movements.get("PAY_OUT", 0),
        drops_cents=movements.get("CASH_DROP", 0),
        no_sale_count=no_sale,
        opening_float_cents=shift.opening_float_cents,
        expected_cash_cents=expected,
        foreign_cash=dict(foreign_cash),
        tips_cents=int(tips),
        service_charge_cents=int(service),
        tips_by_server=tips_by_server(db, Sale.id.in_(sales)),
        deposit_cents=deposit_in,
        deposit_refund_cents=deposit_out,
        provider_totals={
            f"{channel}:{provider}": int(amount)
            for channel, provider, amount in db.execute(
                select(PaymentIntent.channel, PaymentIntent.provider, func.sum(PaymentIntent.amount_cents))
                .where(PaymentIntent.sale_id.in_(sales), PaymentIntent.channel != "QR")
                .group_by(PaymentIntent.channel, PaymentIntent.provider)
            )
        },
    )


def tip_report(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> TipReport:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Pick a period of at most 400 days that ends after it starts.")
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    condition = and_(
        Sale.status.in_(POSTED),
        Sale.is_quote_proforma.is_(False),
        Sale.created_at >= since,
        Sale.created_at < until,
        *((Sale.store_id == store_id,) if store_id is not None else ()),
    )
    count, tips, service = db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.tip_cents), 0),
            func.coalesce(func.sum(Sale.service_charge_cents), 0),
        ).where(condition, (Sale.tip_cents > 0) | (Sale.service_charge_cents > 0))
    ).one()
    return TipReport(
        start=start,
        end=end,
        store_id=store_id,
        sales_count=int(count),
        tips_cents=int(tips),
        service_charge_cents=int(service),
        by_server=tips_by_server(db, condition),
    )


def tips_by_server(db: Session, condition: ColumnElement[bool]) -> list[ServerTips]:
    """Tips per member of staff: the server the tip was for, else the cashier who rang the sale."""
    earner = func.coalesce(Sale.tip_user_id, Sale.cashier_id)
    rows = db.execute(
        select(earner, func.count(Sale.id), func.sum(Sale.tip_cents))
        .where(condition, Sale.tip_cents > 0)
        .group_by(earner)
        .order_by(func.sum(Sale.tip_cents).desc())
    ).all()
    ids = [row[0] for row in rows if row[0] is not None]
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}
    return [
        ServerTips(user_id=user_id, name=names.get(user_id, "Unknown"), sales_count=int(sales), tips_cents=int(cents))
        for user_id, sales, cents in rows
    ]


def apply_shift(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(RegisterShiftPayload, payload)
    require_store(db, data.store_id)
    if data.currency != business_currency(db):
        raise SyncRejected(f"Shifts are counted in the business currency {business_currency(db)}.")
    _user(db, data.opened_by_id, "The cashier who opened the shift")
    shift = db.get(RegisterShift, data.id)
    if shift is None:
        shift = RegisterShift(
            id=data.id,
            store_id=data.store_id,
            device_id=ctx.device.id if ctx.device is not None else None,
            opened_by_id=data.opened_by_id,
            opened_at=data.opened_at,
            currency=data.currency,
            status="OPEN",
            opening_float_cents=data.opening_float_cents,
            blind_close=data.blind_close,
            notes=data.notes,
        )
        db.add(shift)
        db.flush()
    elif shift.store_id != data.store_id:
        raise SyncRejected("This shift belongs to another store.")
    if data.status == "CLOSED" and shift.status != "CLOSED":
        closer = _user(db, data.closed_by_id, "The cashier who closed the shift")  # type: ignore[arg-type]
        report = build_report(db, shift)
        if data.z_number:
            taken = db.scalar(select(RegisterShift.id).where(RegisterShift.z_number == data.z_number)) is not None
            shift.z_number = accept_register_number(
                db, number=data.z_number, store_id=shift.store_id, device=ctx.device, doc_type="Z", taken=taken
            )
        else:
            shift.z_number = next_server_number(db, shift.store_id, "Z")
        shift.status = "CLOSED"
        shift.closed_by_id = closer.id
        shift.closed_at = data.closed_at
        shift.counted_cash_cents = data.counted_cash_cents
        shift.expected_cash_cents = report.expected_cash_cents
        shift.variance_cents = (data.counted_cash_cents or 0) - report.expected_cash_cents
        report.foreign_counted = {code.upper(): value for code, value in data.counted_foreign.items()}
        shift.report = report.model_dump(mode="json")
        shift.notes = data.notes or shift.notes
        db.flush()
    return shift.id


def apply_cash_movement(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(CashMovementPayload, payload)
    shift = db.get(RegisterShift, data.shift_id)
    if shift is None:
        raise SyncRejected("The shift for this cash movement has not synced yet.")
    if shift.store_id != data.store_id:
        raise SyncRejected("The cash movement and its shift are in different stores.")
    if db.get(CashMovement, data.id) is not None:
        return data.id
    if shift.status == "CLOSED":
        raise SyncRejected(f"Shift {shift.z_number or shift.id} is already closed.")
    _user(db, data.user_id, "The cashier")
    db.add(
        CashMovement(
            id=data.id,
            shift_id=shift.id,
            store_id=data.store_id,
            user_id=data.user_id,
            kind=data.kind,
            amount_cents=data.amount_cents,
            currency=data.currency,
            reason=data.reason.strip(),
            occurred_at=data.occurred_at,
        )
    )
    db.flush()
    return data.id


register_handler("register_shift", apply_shift)
register_handler("cash_movement", apply_cash_movement)


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item is not None}
    if not wanted:
        return {}
    return {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(wanted)))}


def shift_out(db: Session, shift: RegisterShift) -> ShiftOut:
    report = (
        ShiftReport.model_validate(shift.report)
        if shift.status == "CLOSED" and shift.report
        else build_report(db, shift)
    )
    movements = list(
        db.scalars(select(CashMovement).where(CashMovement.shift_id == shift.id).order_by(CashMovement.occurred_at))
    )
    names = _names(db, {shift.opened_by_id, shift.closed_by_id, *(row.user_id for row in movements)})
    store = db.get(Store, shift.store_id)
    device = db.get(Device, shift.device_id) if shift.device_id else None
    return ShiftOut(
        id=shift.id,
        store_id=shift.store_id,
        store_code=store.code if store is not None else "",
        device_code=device.code if device is not None else None,
        opened_by_name=names.get(shift.opened_by_id, "Unknown"),
        closed_by_name=names.get(shift.closed_by_id) if shift.closed_by_id else None,
        opened_at=_aware(shift.opened_at),
        closed_at=_aware(shift.closed_at),
        currency=shift.currency,
        status=shift.status,  # type: ignore[arg-type]
        opening_float_cents=shift.opening_float_cents,
        counted_cash_cents=shift.counted_cash_cents,
        expected_cash_cents=shift.expected_cash_cents
        if shift.expected_cash_cents is not None
        else report.expected_cash_cents,
        variance_cents=shift.variance_cents,
        blind_close=shift.blind_close,
        z_number=shift.z_number,
        report=report,
        movements=[
            CashMovementOut(
                id=row.id,
                kind=row.kind,  # type: ignore[arg-type]
                amount_cents=row.amount_cents,
                reason=row.reason,
                user_name=names.get(row.user_id, "Unknown"),
                occurred_at=_aware(row.occurred_at),
            )
            for row in movements
        ],
    )


def list_shifts(db: Session, *, store_scope: uuid.UUID | None, status: str | None, limit: int) -> list[ShiftOut]:
    query = select(RegisterShift).order_by(RegisterShift.opened_at.desc()).limit(limit)
    if store_scope is not None:
        query = query.where(RegisterShift.store_id == store_scope)
    if status is not None:
        query = query.where(RegisterShift.status == status)
    return [shift_out(db, row) for row in db.scalars(query)]


def get_shift(db: Session, shift_id: uuid.UUID, store_scope: uuid.UUID | None) -> ShiftOut:
    shift = db.get(RegisterShift, shift_id)
    if shift is None or (store_scope is not None and shift.store_id != store_scope):
        raise ApiError(404, "not_found", "Shift was not found.")
    return shift_out(db, shift)
