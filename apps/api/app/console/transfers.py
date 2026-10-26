"""Manual bank transfers. A receipt stays pending until an administrator verifies the bank credit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.errors import ApiError
from app.tenancy.models import (
    BillingInvoice,
    BillingPayment,
    BillingPolicy,
    BillingTransfer,
    PlatformBankAccount,
    Subscription,
    Tenant,
)

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"
PDF = b"%PDF"
MAX_BYTES = 2_000_000
KINDS = {PNG: "image/png", JPEG: "image/jpeg", PDF: "application/pdf"}


def active_bank_snapshot(db: Session) -> dict[str, str] | None:
    row = db.scalar(
        select(PlatformBankAccount).where(PlatformBankAccount.active.is_(True)).order_by(PlatformBankAccount.updated_at.desc())
    )
    if row is None:
        return None
    return _account_dict(row)


def grace_days(db: Session) -> int:
    row = db.get(BillingPolicy, 1)
    if row is None:
        row = BillingPolicy(id=1, grace_days=5, updated_at=datetime.now(UTC))
        db.add(row)
        db.flush()
    return row.grace_days


def set_grace_days(db: Session, operator: OperatorPrincipal, days: int) -> int:
    if not 0 <= days <= 60:
        raise ApiError(422, "invalid_grace", "Grace period must be between 0 and 60 days.")
    before = grace_days(db)
    row = db.get(BillingPolicy, 1)
    assert row is not None
    row.grace_days = days
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db, operator, "billing.grace", before={"grace_days": before}, after={"grace_days": days}, reason="Grace period"
    )
    db.commit()
    return days


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def access_state(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> str:
    """active, trial, grace, or restricted. No subscription row means the store is not on this billing policy."""
    moment = now or datetime.now(UTC)
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if row is None:
        return "unbilled"
    if row.status == "canceled":
        return "restricted"
    if row.status == "trialing" and row.trial_ends_at is not None and moment <= _aware(row.trial_ends_at):
        return "trial"
    end = _aware(row.current_period_end) if row.current_period_end is not None else None
    if row.status == "active" and end is not None and moment <= end:
        return "active"
    if end is not None and moment <= end + timedelta(days=grace_days(db)):
        return "grace"
    return "restricted"


def ai_allowed(db: Session, tenant_id: uuid.UUID) -> bool:
    return access_state(db, tenant_id) in {"unbilled", "trial", "active"}


def list_accounts(db: Session) -> list[PlatformBankAccount]:
    return list(db.scalars(select(PlatformBankAccount).order_by(PlatformBankAccount.display_name)))


def save_account(
    db: Session, operator: OperatorPrincipal, data: dict[str, object], account_id: uuid.UUID | None
) -> PlatformBankAccount:
    row = db.get(PlatformBankAccount, account_id) if account_id else None
    if account_id is not None and row is None:
        raise ApiError(404, "bank_account_not_found", "That bank account does not exist.")
    if row is None:
        row = PlatformBankAccount(
            display_name=str(data["display_name"]),
            bank_name=str(data["bank_name"]),
            holder_name=str(data["holder_name"]),
        )
        db.add(row)
    before = _account_dict(row) if account_id else None
    fields = (
        "display_name",
        "bank_name",
        "holder_name",
        "account_number",
        "iban",
        "swift",
        "country",
        "currency",
        "instructions",
    )
    for key in fields:
        if key in data and data[key] is not None:
            setattr(row, key, str(data[key]).strip())
    if "active" in data:
        row.active = bool(data["active"])
    row.updated_at = datetime.now(UTC)
    audit_operator(db, operator, "billing.bank_account", before=before, after=_account_dict(row), reason="Bank account")
    db.commit()
    db.refresh(row)
    return row


def submit_transfer(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount_fils: int,
    transferred_on: str,
    bank_reference: str,
    sending_bank: str,
    note: str,
    idempotency_key: str,
    filename: str,
    body: bytes,
) -> BillingTransfer:
    if len(idempotency_key) < 8:
        raise ApiError(422, "invalid_request", "Send an idempotency key of at least 8 characters.")
    existing = db.scalar(
        select(BillingTransfer).where(
            BillingTransfer.tenant_id == tenant_id, BillingTransfer.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing
    invoice = db.get(BillingInvoice, invoice_id)
    if invoice is None or invoice.tenant_id != tenant_id:
        raise ApiError(404, "invoice_not_found", "That invoice is not on this store.")
    if invoice.status != "pending":
        raise ApiError(409, "invoice_not_payable", "This invoice is not waiting for a transfer.")
    if amount_fils <= 0:
        raise ApiError(422, "invalid_amount", "Enter the amount you transferred.")
    kind = _kind(body)
    pending = db.scalar(
        select(BillingTransfer.id).where(
            BillingTransfer.invoice_id == invoice.id, BillingTransfer.status == "pending_review"
        )
    )
    if pending is not None:
        raise ApiError(409, "transfer_pending", "A receipt for this invoice is already waiting for review.")
    row = BillingTransfer(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        amount_fils=amount_fils,
        transferred_on=transferred_on,
        bank_reference=bank_reference.strip(),
        sending_bank=sending_bank.strip(),
        note=note.strip(),
        idempotency_key=idempotency_key,
        filename=filename[:120] or "receipt",
        content_type=kind,
        body=body,
    )
    db.add(row)
    from app.console import hardware as hardware_catalog

    hardware_catalog.mark_under_review(db, invoice.id)
    db.commit()
    db.refresh(row)
    return row


def list_transfers(db: Session, status: str | None) -> list[BillingTransfer]:
    statement = select(BillingTransfer).order_by(BillingTransfer.created_at.desc())
    if status:
        statement = statement.where(BillingTransfer.status == status)
    return list(db.scalars(statement))


def receipt_bytes(db: Session, transfer_id: uuid.UUID, tenant_id: uuid.UUID | None) -> BillingTransfer:
    row = db.get(BillingTransfer, transfer_id)
    if row is None or (tenant_id is not None and row.tenant_id != tenant_id):
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    return row


def approve(db: Session, operator: OperatorPrincipal, transfer_id: uuid.UUID) -> BillingPayment:
    from app.console.billing import _activate

    row = db.get(BillingTransfer, transfer_id)
    if row is None:
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    if row.status == "approved":
        found = db.scalar(select(BillingPayment).where(BillingPayment.submission_id == row.id))
        if found is None:
            raise ApiError(409, "payment_missing", "This receipt was approved without a payment record.")
        return found
    if row.status != "pending_review":
        raise ApiError(409, "transfer_closed", "This receipt is no longer waiting for review.")
    invoice = db.get(BillingInvoice, row.invoice_id)
    tenant = db.get(Tenant, row.tenant_id)
    if invoice is None or tenant is None or invoice.status == "paid":
        raise ApiError(409, "invoice_not_payable", "This invoice cannot take another payment.")
    if row.amount_fils < invoice.total_fils:
        raise ApiError(422, "underpaid", "The transferred amount is less than the invoice.")
    if row.amount_fils > invoice.total_fils:
        raise ApiError(422, "overpaid", "The transferred amount is more than the invoice.")
    reference = row.bank_reference or None
    if reference and db.scalar(select(BillingPayment.id).where(BillingPayment.bank_reference == reference)):
        raise ApiError(409, "duplicate_reference", "That bank reference is already recorded.")
    payment = BillingPayment(
        tenant_id=row.tenant_id,
        invoice_id=invoice.id,
        submission_id=row.id,
        amount_fils=row.amount_fils,
        bank_reference=reference,
        recorded_by=operator.id,
    )
    db.add(payment)
    invoice.status = "paid"
    invoice.paid_at = datetime.now(UTC)
    row.status = "approved"
    row.reviewed_by = operator.id
    row.reviewed_at = invoice.paid_at
    _activate(db, tenant, invoice)
    from app.console import hardware as hardware_catalog

    hardware_catalog.mark_paid(db, invoice.id)
    audit_operator(
        db,
        operator,
        "billing.transfer_approve",
        tenant_id=tenant.id,
        after={"invoice_id": str(invoice.id), "amount_fils": payment.amount_fils, "reference": reference},
        reason="Verified bank credit",
    )
    db.commit()
    db.refresh(payment)
    return payment


def reject(db: Session, operator: OperatorPrincipal, transfer_id: uuid.UUID, reason: str) -> BillingTransfer:
    cleaned = reason.strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reason_required", "Enter why this receipt was rejected.")
    row = db.get(BillingTransfer, transfer_id)
    if row is None:
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    if row.status != "pending_review":
        raise ApiError(409, "transfer_closed", "This receipt is no longer waiting for review.")
    row.status = "rejected"
    row.decision_reason = cleaned
    row.reviewed_by = operator.id
    row.reviewed_at = datetime.now(UTC)
    from app.console import hardware as hardware_catalog

    hardware_catalog.release_review(db, row.invoice_id)
    audit_operator(
        db,
        operator,
        "billing.transfer_reject",
        tenant_id=row.tenant_id,
        after={"transfer_id": str(row.id)},
        reason=cleaned,
    )
    db.commit()
    db.refresh(row)
    return row


def _kind(body: bytes) -> str:
    if len(body) < 8 or len(body) > MAX_BYTES:
        raise ApiError(422, "invalid_receipt", "Upload a PNG, JPEG, or PDF no larger than 2 MB.")
    for magic, content_type in KINDS.items():
        if body.startswith(magic):
            return content_type
    raise ApiError(422, "invalid_receipt", "Upload a PNG, JPEG, or PDF.")


def _account_dict(row: PlatformBankAccount) -> dict[str, str]:
    return {
        "display_name": row.display_name,
        "bank_name": row.bank_name,
        "holder_name": row.holder_name,
        "account_number": row.account_number,
        "iban": row.iban,
        "swift": row.swift,
        "country": row.country,
        "currency": row.currency,
        "instructions": row.instructions,
        "active": "yes" if row.active else "no",
    }
