"""Automatic credit holds. An account goes on hold when an invoice is overdue past the grace period or a
cheque bounces; overdue holds lift on their own once paid, bounce and manager holds need a manager."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.customer import Customer
from app.services import ledger_service


def overdue_reason(db: Session, settings: Settings, customer: Customer, now: datetime | None = None) -> str | None:
    now = now or datetime.now(UTC)
    worst = max(
        (ledger_service.days_overdue(sale, now) for sale in ledger_service.open_invoices(db, customer.id)), default=0
    )
    if worst > settings.credit_hold_overdue_days:
        return f"Invoice {worst} days overdue (limit {settings.credit_hold_overdue_days})"
    return None


def refresh(db: Session, settings: Settings, customer: Customer) -> bool:
    """Re-evaluates an automatic hold. Returns whether the hold changed."""
    if customer.credit_hold_manual:
        return False
    reason = overdue_reason(db, settings, customer)
    held = reason is not None
    changed = held != customer.credit_hold or (held and reason != customer.credit_hold_reason)
    customer.credit_hold = held
    customer.credit_hold_reason = reason
    return changed


def refresh_all(db: Session, settings: Settings) -> int:
    changed = 0
    for customer in db.scalars(
        select(Customer).where(Customer.customer_type == "WHOLESALE", Customer.is_active.is_(True))
    ):
        changed += refresh(db, settings, customer)
    db.commit()
    return changed


def set_hold(db: Session, settings: Settings, customer: Customer, *, hold: bool, reason: str) -> None:
    """A manager places a hold (kept until a manager lifts it) or lifts any hold."""
    if hold:
        customer.credit_hold = True
        customer.credit_hold_manual = True
        customer.credit_hold_reason = reason.strip() or "Placed on hold by a manager"
        return
    customer.credit_hold_manual = False
    customer.credit_hold = False
    customer.credit_hold_reason = None
    refresh(db, settings, customer)
