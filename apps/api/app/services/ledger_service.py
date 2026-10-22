"""Customer statement of account. Every balance change appends a CustomerLedgerEntry, so
customers.current_balance_cents always equals the sum of that customer's ledger."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import TERM_DAYS, Customer, CustomerLedgerEntry
from app.models.sale import Sale

AGING_BUCKETS = (("current", None, 0), ("1_30", 1, 30), ("31_60", 31, 60), ("61_90", 61, 90), ("90_plus", 91, None))


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def due_date_for(customer: Customer | None, sold_at: datetime) -> datetime:
    days = TERM_DAYS.get(customer.payment_terms, 0) if customer is not None else 0
    return as_utc(sold_at) + timedelta(days=days)


def payment_status(total_cents: int, paid_cents: int) -> str:
    if paid_cents >= total_cents:
        return "PAID"
    return "PARTIAL" if paid_cents > 0 else "ON_ACCOUNT_UNPAID"


def _append(
    db: Session,
    customer: Customer,
    *,
    entry_type: str,
    amount_cents: int,
    created_at: datetime,
    sale_id: uuid.UUID | None = None,
    due_date: datetime | None = None,
    method: str | None = None,
    reference: str = "",
    note: str = "",
    user_id: uuid.UUID | None = None,
) -> CustomerLedgerEntry:
    customer.current_balance_cents += amount_cents
    entry = CustomerLedgerEntry(
        customer_id=customer.id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        balance_after_cents=customer.current_balance_cents,
        sale_id=sale_id,
        due_date=due_date,
        method=method,
        reference=reference[:120],
        note=note[:255],
        user_id=user_id,
        created_at=created_at,
    )
    db.add(entry)
    return entry


def post_sale(db: Session, customer: Customer, sale: Sale, *, paid_method: str | None, user_id: uuid.UUID) -> None:
    """Books the invoice and, when something was paid at the till, the matching payment."""
    if sale.total_cents == 0:
        return
    # Ledger rows carry posting time so running balances stay in posting order; the invoice keeps its sale date.
    at = datetime.now(UTC)
    reference = sale.invoice_number or sale.client_sale_id[:8].upper()
    _append(
        db,
        customer,
        entry_type="INVOICE",
        amount_cents=sale.total_cents,
        created_at=at,
        sale_id=sale.id,
        due_date=sale.due_date,
        reference=reference,
        user_id=user_id,
    )
    if sale.amount_paid_cents > 0:
        _append(
            db,
            customer,
            entry_type="PAYMENT",
            amount_cents=-sale.amount_paid_cents,
            # Payments sort after their invoice even on clocks with coarse resolution.
            created_at=at + timedelta(microseconds=1),
            sale_id=sale.id,
            method=paid_method,
            reference=reference,
            note="Paid at the register",
            user_id=user_id,
        )


def open_invoices(db: Session, customer_id: uuid.UUID) -> list[Sale]:
    statement = (
        select(Sale)
        .where(
            Sale.customer_id == customer_id,
            Sale.is_quote_proforma.is_(False),
            Sale.due_balance_cents > 0,
        )
        .order_by(Sale.created_at, Sale.id)
    )
    return list(db.scalars(statement).all())


def receive_payment(
    db: Session,
    customer: Customer,
    *,
    amount_cents: int,
    method: str,
    reference: str,
    note: str,
    user_id: uuid.UUID | None,
) -> tuple[CustomerLedgerEntry, list[tuple[Sale, int]]]:
    """Allocates oldest invoice first. Anything left over stays on the account as a credit balance."""
    remaining = amount_cents
    allocations: list[tuple[Sale, int]] = []
    for sale in open_invoices(db, customer.id):
        if remaining == 0:
            break
        applied = min(remaining, sale.due_balance_cents)
        sale.amount_paid_cents += applied
        sale.due_balance_cents -= applied
        sale.payment_status = payment_status(sale.total_cents, sale.amount_paid_cents)
        remaining -= applied
        allocations.append((sale, applied))
    invoices = ", ".join((sale.invoice_number or sale.client_sale_id[:8].upper()) for sale, _ in allocations)
    entry = _append(
        db,
        customer,
        entry_type="PAYMENT",
        amount_cents=-amount_cents,
        created_at=datetime.now(UTC),
        method=method,
        reference=reference,
        note=note or (f"Applied to {invoices}" if invoices else "Unapplied credit"),
        user_id=user_id,
    )
    db.flush()
    return entry, allocations


def adjust(db: Session, customer: Customer, *, amount_cents: int, note: str, user_id: uuid.UUID | None) -> None:
    _append(
        db,
        customer,
        entry_type="ADJUSTMENT",
        amount_cents=amount_cents,
        created_at=datetime.now(UTC),
        note=note,
        user_id=user_id,
    )
    db.flush()


def entries(db: Session, customer_id: uuid.UUID, limit: int = 500) -> list[CustomerLedgerEntry]:
    statement = (
        select(CustomerLedgerEntry)
        .where(CustomerLedgerEntry.customer_id == customer_id)
        .order_by(CustomerLedgerEntry.created_at.desc(), CustomerLedgerEntry.id)
        .limit(limit)
    )
    return list(reversed(db.scalars(statement).all()))


def days_overdue(sale: Sale, now: datetime) -> int:
    if sale.due_date is None:
        return 0
    return max(0, (now - as_utc(sale.due_date)).days)


def aging(invoices: list[Sale], now: datetime) -> dict[str, int]:
    buckets = {name: 0 for name, _, _ in AGING_BUCKETS}
    for sale in invoices:
        overdue = days_overdue(sale, now)
        for name, low, high in AGING_BUCKETS:
            if (low is None or overdue >= low) and (high is None or overdue <= high):
                buckets[name] += sale.due_balance_cents
                break
    return buckets
