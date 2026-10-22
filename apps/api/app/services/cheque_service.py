"""Post-dated cheques: recorded when received at the till or against an account, tracked to clearance,
and reversed on the customer's account when they bounce or are handed back."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.cheque import Cheque, ChequeEvent
from app.models.customer import Customer
from app.models.sale import Sale
from app.models.user import User
from app.schemas.cheques import ChequeAction, ChequeEventOut, ChequeList, ChequeOut, ChequeStats
from app.schemas.payloads import ChequeDetails
from app.services import ledger_service

OPEN = ("RECEIVED", "DEPOSITED")
TRANSITIONS = {
    "RECEIVED": {"DEPOSITED", "BOUNCED", "CANCELLED"},
    "DEPOSITED": {"CLEARED", "BOUNCED"},
}
ACTION_STATUS = {"deposit": "DEPOSITED", "clear": "CLEARED", "bounce": "BOUNCED", "cancel": "CANCELLED"}


def _event(db: Session, cheque: Cheque, to_status: str, user_id: uuid.UUID | None, note: str) -> None:
    db.add(
        ChequeEvent(
            cheque_id=cheque.id,
            from_status=None if to_status == "RECEIVED" else cheque.status,
            to_status=to_status,
            user_id=user_id,
            note=note[:255],
            occurred_at=datetime.now(UTC),
        )
    )


def record(
    db: Session,
    *,
    details: ChequeDetails,
    amount_cents: int,
    currency: str,
    store_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    source: str,
    sale_id: uuid.UUID | None = None,
    ledger_entry_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Cheque:
    cheque = Cheque(
        store_id=store_id,
        customer_id=customer_id,
        cheque_number=details.cheque_number.strip(),
        bank=details.bank.strip(),
        cheque_date=details.cheque_date,
        amount_cents=amount_cents,
        currency=currency,
        status="RECEIVED",
        source=source,
        sale_id=sale_id,
        ledger_entry_id=ledger_entry_id,
        received_by_id=user_id,
    )
    db.add(cheque)
    db.flush()
    _event(db, cheque, "RECEIVED", user_id, "Post-dated" if details.cheque_date > date.today() else "")
    return cheque


def exposure(db: Session, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Uncleared cheques per customer: money already credited to the account that may still bounce."""
    if not customer_ids:
        return {}
    rows = db.execute(
        select(Cheque.customer_id, func.sum(Cheque.amount_cents))
        .where(Cheque.customer_id.in_(customer_ids), Cheque.status.in_(OPEN))
        .group_by(Cheque.customer_id)
    )
    return {customer_id: int(total) for customer_id, total in rows if customer_id is not None}


def _reverse(db: Session, cheque: Cheque, status: str, user_id: uuid.UUID | None, fee_cents: int) -> None:
    label = "bounced" if status == "BOUNCED" else "returned to the customer"
    if cheque.sale_id is not None:
        sale = db.get(Sale, cheque.sale_id)
        if sale is not None:
            sale.amount_paid_cents = max(0, sale.amount_paid_cents - cheque.amount_cents)
            sale.due_balance_cents = sale.total_cents - sale.amount_paid_cents
            sale.payment_status = ledger_service.payment_status(sale.total_cents, sale.amount_paid_cents)
    customer = db.get(Customer, cheque.customer_id) if cheque.customer_id else None
    if customer is None:
        return
    ledger_service.adjust(
        db,
        customer,
        amount_cents=cheque.amount_cents,
        note=f"Cheque {cheque.cheque_number} ({cheque.bank}) {label}",
        user_id=user_id,
    )
    if fee_cents > 0:
        ledger_service.adjust(
            db, customer, amount_cents=fee_cents, note=f"Bounced cheque fee, {cheque.cheque_number}", user_id=user_id
        )
    if status == "BOUNCED":
        customer.credit_hold = True
        customer.credit_hold_manual = True
        customer.credit_hold_reason = f"Cheque {cheque.cheque_number} bounced on {date.today():%d %b %Y}"


def act(db: Session, cheque_id: uuid.UUID, action: str, data: ChequeAction, user_id: uuid.UUID | None, store_scope):
    cheque = db.get(Cheque, cheque_id)
    if cheque is None or (store_scope is not None and cheque.store_id != store_scope):
        raise ApiError(404, "not_found", "Cheque was not found.")
    target = ACTION_STATUS.get(action)
    if target is None:
        raise ApiError(404, "not_found", "Unknown cheque action.")
    if target not in TRANSITIONS.get(cheque.status, set()):
        raise ApiError(422, "cheque_state", f"A {cheque.status.lower()} cheque cannot be marked {target.lower()}.")
    if target == "DEPOSITED" and cheque.cheque_date > date.today():
        raise ApiError(
            422, "cheque_state", f"This cheque is dated {cheque.cheque_date:%d %b %Y}; deposit it from then."
        )
    fee = data.fee_cents if target == "BOUNCED" else 0
    _event(db, cheque, target, user_id, data.note.strip())
    cheque.status = target
    cheque.bounce_fee_cents = fee
    if target in ("BOUNCED", "CANCELLED"):
        _reverse(db, cheque, target, user_id, fee)
    db.commit()
    return cheque_out(db, cheque)


def _names(db: Session, user_ids: set[uuid.UUID | None], customer_ids: set[uuid.UUID | None]):
    users = {item for item in user_ids if item}
    customers = {item for item in customer_ids if item}
    user_names = (
        {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(users))).unique()} if users else {}
    )
    customer_names = (
        {row.id: row.company_name or row.name for row in db.scalars(select(Customer).where(Customer.id.in_(customers)))}
        if customers
        else {}
    )
    return user_names, customer_names


def _invoices(db: Session, cheques: list[Cheque]) -> dict[uuid.UUID, str]:
    ids = {row.sale_id for row in cheques if row.sale_id is not None}
    if not ids:
        return {}
    return {
        sale_id: number or client_id[:8].upper()
        for sale_id, number, client_id in db.execute(
            select(Sale.id, Sale.invoice_number, Sale.client_sale_id).where(Sale.id.in_(ids))
        )
    }


def _out(
    cheque: Cheque, events: list[ChequeEvent], users: dict, customers: dict, invoices: dict[uuid.UUID, str]
) -> ChequeOut:
    sale_reference = invoices.get(cheque.sale_id) if cheque.sale_id else None
    return ChequeOut(
        id=cheque.id,
        store_id=cheque.store_id,
        customer_id=cheque.customer_id,
        customer_name=customers.get(cheque.customer_id) if cheque.customer_id else None,
        cheque_number=cheque.cheque_number,
        bank=cheque.bank,
        cheque_date=cheque.cheque_date,
        amount_cents=cheque.amount_cents,
        currency=cheque.currency,
        status=cheque.status,  # type: ignore[arg-type]
        source=cheque.source,  # type: ignore[arg-type]
        sale_id=cheque.sale_id,
        sale_reference=sale_reference,
        bounce_fee_cents=cheque.bounce_fee_cents,
        received_by_name=users.get(cheque.received_by_id) if cheque.received_by_id else None,
        created_at=ledger_service.as_utc(cheque.created_at),
        events=[
            ChequeEventOut(
                from_status=event.from_status,
                to_status=event.to_status,
                user_name=users.get(event.user_id) if event.user_id else None,
                note=event.note,
                occurred_at=ledger_service.as_utc(event.occurred_at),
            )
            for event in events
        ],
    )


def cheque_out(db: Session, cheque: Cheque) -> ChequeOut:
    events = list(
        db.scalars(select(ChequeEvent).where(ChequeEvent.cheque_id == cheque.id).order_by(ChequeEvent.occurred_at))
    )
    users, customers = _names(db, {cheque.received_by_id, *(event.user_id for event in events)}, {cheque.customer_id})
    return _out(cheque, events, users, customers, _invoices(db, [cheque]))


def list_cheques(
    db: Session, *, status: str | None, customer_id: uuid.UUID | None, store_scope: uuid.UUID | None, limit: int
) -> ChequeList:
    scope = []
    if store_scope is not None:
        scope.append(Cheque.store_id == store_scope)
    if customer_id is not None:
        scope.append(Cheque.customer_id == customer_id)
    query = select(Cheque).where(*scope).order_by(Cheque.cheque_date, Cheque.created_at).limit(limit)
    if status is not None:
        query = query.where(Cheque.status == status)
    cheques = list(db.scalars(query))
    events: dict[uuid.UUID, list[ChequeEvent]] = defaultdict(list)
    if cheques:
        for event in db.scalars(
            select(ChequeEvent)
            .where(ChequeEvent.cheque_id.in_([row.id for row in cheques]))
            .order_by(ChequeEvent.occurred_at)
        ):
            events[event.cheque_id].append(event)
    users, customers = _names(
        db,
        {row.received_by_id for row in cheques} | {event.user_id for rows in events.values() for event in rows},
        {row.customer_id for row in cheques},
    )
    totals = {
        row[0]: (int(row[1]), int(row[2]))
        for row in db.execute(
            select(Cheque.status, func.count(), func.coalesce(func.sum(Cheque.amount_cents), 0))
            .where(*scope)
            .group_by(Cheque.status)
        )
    }
    week = date.today() + timedelta(days=7)
    due = db.execute(
        select(func.count(), func.coalesce(func.sum(Cheque.amount_cents), 0)).where(
            *scope, Cheque.status == "RECEIVED", Cheque.cheque_date <= week
        )
    ).one()
    invoices = _invoices(db, cheques)
    in_hand = totals.get("RECEIVED", (0, 0))
    deposited = totals.get("DEPOSITED", (0, 0))
    return ChequeList(
        stats=ChequeStats(
            in_hand_count=in_hand[0],
            in_hand_cents=in_hand[1],
            deposited_count=deposited[0],
            deposited_cents=deposited[1],
            due_this_week_count=int(due[0]),
            due_this_week_cents=int(due[1]),
            bounced_count=totals.get("BOUNCED", (0, 0))[0],
            bounced_cents=totals.get("BOUNCED", (0, 0))[1],
            exposure_cents=in_hand[1] + deposited[1],
        ),
        cheques=[_out(row, events.get(row.id, []), users, customers, invoices) for row in cheques],
    )
