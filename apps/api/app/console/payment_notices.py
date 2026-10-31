"""Console alerts for payment proofs. The badge counts transfers still in pending_review.

A notice is created once per transfer. Reading it does not approve, reject, or reopen the receipt.
Delivery uses the in-process live rooms. A failure here must not undo the payment submission.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.errors import ApiError
from app.tenancy.models import (
    BillingInvoice,
    BillingTransfer,
    ConsolePaymentNotice,
    ConsolePaymentNoticeRead,
    Tenant,
)
from app.websockets import rooms

logger = logging.getLogger("ai_pos.billing")

ROOM = "console:billing"
NOTICE_LIMIT = 30


def pending_count(db: Session) -> int:
    """Unique receipts waiting for an administrator. Approved, rejected, and paid rows are excluded."""
    found = db.scalar(
        select(func.count()).select_from(BillingTransfer).where(BillingTransfer.status == "pending_review")
    )
    return int(found or 0)


def _reference(invoice: BillingInvoice | None) -> str:
    if invoice is None:
        return ""
    short = str(invoice.id).split("-", 1)[0].upper()
    return f"{invoice.plan_code}-{short}" if invoice.plan_code else short


def _submitted_payload(notice: ConsolePaymentNotice, pending: int) -> dict[str, object]:
    return {
        "type": "payment.submitted_for_review",
        "id": str(notice.id),
        "payment_submission_id": str(notice.transfer_id),
        "tenant_name": notice.tenant_name,
        "invoice_reference": notice.invoice_reference,
        "amount_fils": notice.amount_fils,
        "currency": notice.currency,
        "submitted_at": notice.submitted_at.isoformat(),
        "status": "pending_review",
        "pending": pending,
    }


def announce_submission(db: Session, row: BillingTransfer) -> None:
    """Record and broadcast one alert. A second call for the same transfer does nothing."""
    if db.scalar(select(ConsolePaymentNotice.id).where(ConsolePaymentNotice.transfer_id == row.id)) is not None:
        return
    tenant = db.get(Tenant, row.tenant_id)
    invoice = db.get(BillingInvoice, row.invoice_id)
    notice = ConsolePaymentNotice(
        transfer_id=row.id,
        tenant_id=row.tenant_id,
        tenant_name="" if tenant is None else tenant.name,
        invoice_id=row.invoice_id,
        invoice_reference=_reference(invoice),
        amount_fils=row.amount_fils,
        currency=invoice.currency if invoice is not None else "AED",
        submitted_at=row.created_at,
    )
    db.add(notice)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return
    audit_operator(
        db,
        None,
        "billing.review_notice",
        tenant_id=row.tenant_id,
        after={
            "notice_id": str(notice.id),
            "transfer_id": str(row.id),
            "invoice_reference": notice.invoice_reference,
            "amount_fils": notice.amount_fils,
            "currency": notice.currency,
            "status": "pending_review",
        },
        reason="Payment proof submitted for review",
    )
    rooms.queue(db, ROOM, _submitted_payload(notice, pending_count(db)))


def announce_status(db: Session, row: BillingTransfer) -> None:
    """Tell open consoles the queue length changed. Does not create another notice."""
    rooms.queue(
        db,
        ROOM,
        {
            "type": "payment.review_changed",
            "id": str(uuid.uuid4()),
            "payment_submission_id": str(row.id),
            "status": row.status,
            "pending": pending_count(db),
        },
    )


def list_notices(db: Session, operator_id: uuid.UUID) -> list[dict[str, object]]:
    rows = db.execute(
        select(ConsolePaymentNotice, BillingTransfer.status, ConsolePaymentNoticeRead.read_at)
        .join(BillingTransfer, BillingTransfer.id == ConsolePaymentNotice.transfer_id)
        .outerjoin(
            ConsolePaymentNoticeRead,
            (ConsolePaymentNoticeRead.notice_id == ConsolePaymentNotice.id)
            & (ConsolePaymentNoticeRead.operator_id == operator_id),
        )
        .order_by(ConsolePaymentNotice.created_at.desc())
        .limit(NOTICE_LIMIT)
    ).all()
    return [
        {
            "id": notice.id,
            "payment_submission_id": notice.transfer_id,
            "tenant_name": notice.tenant_name,
            "invoice_reference": notice.invoice_reference,
            "amount_fils": notice.amount_fils,
            "currency": notice.currency,
            "submitted_at": notice.submitted_at,
            "status": status,
            "read": read_at is not None,
        }
        for notice, status, read_at in rows
    ]


def mark_read(db: Session, operator: OperatorPrincipal, notice_id: uuid.UUID) -> dict[str, object]:
    notice = db.get(ConsolePaymentNotice, notice_id)
    if notice is None:
        raise ApiError(404, "notice_not_found", "That notification does not exist.")
    existing = db.scalar(
        select(ConsolePaymentNoticeRead).where(
            ConsolePaymentNoticeRead.notice_id == notice.id,
            ConsolePaymentNoticeRead.operator_id == operator.id,
        )
    )
    if existing is None:
        db.add(ConsolePaymentNoticeRead(notice_id=notice.id, operator_id=operator.id))
        db.commit()
    found = next((row for row in list_notices(db, operator.id) if row["id"] == notice.id), None)
    if found is None:
        raise ApiError(404, "notice_not_found", "That notification does not exist.")
    return found
