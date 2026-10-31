"""Manual bank transfers. A receipt stays pending until an administrator verifies the bank credit."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.security import OperatorPrincipal, audit_operator
from app.core.config import Settings
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

logger = logging.getLogger("ai_pos.billing")

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


def operational_block(db: Session, tenant_id: uuid.UUID) -> dict[str, str] | None:
    """Why paid operations are closed, or None when they are open.

    An active subscription and its grace period stay open. Uploading a receipt, leaving an invoice
    pending, or sitting on a trial does not open them.
    """
    state = access_state(db, tenant_id)
    if state in {"active", "grace"}:
        return None
    notice = attention(db, tenant_id)
    kind = None if notice is None else str(notice.get("kind") or "")
    # A practice trial with no invoice can still open its sample catalog. The first invoice closes paid APIs.
    if not kind and state in {"unbilled", "trial"}:
        return None
    if kind == "pending_review":
        code, status, message = (
            "subscription_payment_pending",
            "pending_review",
            "Your payment is awaiting verification. Paid features open after verification and activation.",
        )
    elif kind == "rejected":
        code, status, message = (
            "subscription_payment_rejected",
            "rejected",
            "The payment proof was not accepted. Paid features stay locked until a corrected proof is verified.",
        )
    elif kind == "revoked":
        code, status, message = (
            "subscription_revoked",
            "revoked",
            "The previous activation was revoked. Paid features stay locked until a payment is verified again.",
        )
    elif state == "restricted":
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
        if row is not None and row.status == "canceled":
            code, status, message = (
                "subscription_suspended",
                "canceled",
                "This subscription is not active. Paid features stay locked until it is restored.",
            )
        else:
            code, status, message = (
                "subscription_expired",
                "expired",
                "This subscription is past its grace period. Paid features stay locked until it is renewed.",
            )
    else:
        code, status, message = (
            "subscription_payment_required",
            "awaiting_payment",
            "Paid features stay locked until a payment is submitted, verified, and the subscription is activated.",
        )
    return {"code": code, "subscription_status": status, "message": message, "redirect": "/subscription"}


def ai_allowed(db: Session, tenant_id: uuid.UUID) -> bool:
    """AI stays closed during grace. A pending receipt closes it too."""
    if operational_block(db, tenant_id) is not None:
        return False
    return access_state(db, tenant_id) in {"unbilled", "active"}


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
        _console_after_submit(db, existing)
        return existing
    invoice = db.get(BillingInvoice, invoice_id)
    if invoice is None or invoice.tenant_id != tenant_id:
        raise ApiError(404, "invoice_not_found", "That invoice is not on this store.")
    if invoice.status != "pending":
        raise ApiError(409, "invoice_not_payable", "This invoice is not waiting for a transfer.")
    if amount_fils != invoice.total_fils:
        raise ApiError(
            422,
            "amount_mismatch",
            "Transfer the invoice total. This invoice does not accept a partial payment.",
        )
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
    _console_after_submit(db, row)
    _notify_owner(
        db,
        row.tenant_id,
        "Payment proof received",
        "We have your payment proof. Subscription features stay locked until an administrator verifies the transfer. "
        "Sign in to AxizPOS Business to see the status.",
    )
    return row


def attention(db: Session, tenant_id: uuid.UUID) -> dict[str, object] | None:
    """The invoice this store still has to act on. A paid, unrevoked invoice returns nothing."""
    invoice = db.scalar(
        select(BillingInvoice)
        .where(BillingInvoice.tenant_id == tenant_id, BillingInvoice.status == "pending")
        .order_by(BillingInvoice.created_at.desc())
    )
    paid = db.scalar(
        select(BillingPayment)
        .where(BillingPayment.tenant_id == tenant_id, BillingPayment.revoked_at.is_not(None))
        .order_by(BillingPayment.revoked_at.desc())
    )
    if invoice is None:
        if paid is None:
            return None
        source = db.get(BillingInvoice, paid.invoice_id)
        if source is None:
            return None
        return _attention_body(source, None, "revoked", paid.revoke_reason)
    latest = db.scalar(
        select(BillingTransfer)
        .where(BillingTransfer.invoice_id == invoice.id)
        .order_by(BillingTransfer.created_at.desc())
    )
    if latest is None:
        kind = "awaiting_proof"
        reason = None
    elif latest.status == "rejected":
        kind = "rejected"
        reason = latest.decision_reason
    elif latest.status == "pending_review":
        kind = "pending_review"
        reason = None
    else:
        return None
    return _attention_body(invoice, latest, kind, reason)


def _attention_body(
    invoice: BillingInvoice, transfer: BillingTransfer | None, kind: str, reason: str | None
) -> dict[str, object]:
    return {
        "kind": kind,
        "invoice_id": str(invoice.id),
        "plan_code": invoice.plan_code,
        "cycle_code": invoice.cycle_code,
        "currency": invoice.currency,
        "total_fils": invoice.total_fils,
        "issued_at": invoice.created_at.isoformat(),
        "bank": invoice.bank_snapshot,
        "transfer_id": None if transfer is None else str(transfer.id),
        "reason": reason,
    }


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


def approve(db: Session, operator: OperatorPrincipal, transfer_id: uuid.UUID, settings: Settings) -> BillingPayment:
    from app.console.billing import _activate

    row = db.get(BillingTransfer, transfer_id)
    if row is None:
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    if row.status == "approved":
        found = db.scalar(select(BillingPayment).where(BillingPayment.submission_id == row.id))
        if found is None:
            raise ApiError(409, "payment_missing", "This receipt was approved without a payment record.")
        from app.console.entitlements import publish_purchased

        publish_purchased(settings, row.tenant_id)
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
    _console_after_decision(db, row)
    db.commit()
    from app.console.entitlements import publish_purchased

    publish_purchased(settings, row.tenant_id)
    _notify_owner(
        db,
        row.tenant_id,
        "Subscription activated",
        "Your payment was verified and the subscription is active. "
        "Sign in to AxizPOS Business to use the paid features.",
    )
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
    _console_after_decision(db, row)
    db.commit()
    db.refresh(row)
    _notify_owner(
        db,
        row.tenant_id,
        "Payment proof needs attention",
        "We could not verify the transfer on your invoice. "
        "Sign in to AxizPOS Business to read the reason and send a corrected proof. Subscription features stay locked.",
    )
    return row


def reopen(db: Session, operator: OperatorPrincipal, transfer_id: uuid.UUID, reason: str) -> BillingTransfer:
    """Puts a rejected receipt back in the queue. It does not activate the subscription."""
    cleaned = reason.strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reason_required", "Enter why this review is being reopened.")
    row = db.get(BillingTransfer, transfer_id)
    if row is None:
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    if row.status != "rejected":
        raise ApiError(409, "transfer_closed", "Only a rejected receipt can be reopened.")
    previous = row.decision_reason
    row.status = "pending_review"
    row.reviewed_by = operator.id
    row.reviewed_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "billing.transfer_reopen",
        tenant_id=row.tenant_id,
        before={"decision_reason": previous},
        after={"transfer_id": str(row.id), "status": "pending_review"},
        reason=cleaned,
    )
    _console_after_decision(db, row)
    db.commit()
    db.refresh(row)
    return row


def revoke(
    db: Session, operator: OperatorPrincipal, settings: Settings, transfer_id: uuid.UUID, reason: str
) -> BillingPayment:
    """Stops a subscription that was activated from this receipt. The payment and receipt stay on record."""
    cleaned = reason.strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reason_required", "Enter why this activation is being revoked.")
    row = db.get(BillingTransfer, transfer_id)
    if row is None:
        raise ApiError(404, "transfer_not_found", "That receipt does not exist.")
    if row.status != "approved":
        raise ApiError(409, "transfer_closed", "Only a verified receipt can have its activation revoked.")
    payment = db.scalar(select(BillingPayment).where(BillingPayment.submission_id == row.id))
    if payment is None:
        raise ApiError(409, "payment_missing", "This receipt was approved without a payment record.")
    if payment.revoked_at is not None:
        raise ApiError(409, "already_revoked", "This activation was already revoked.")
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == row.tenant_id))
    if subscription is not None:
        subscription.status = "canceled"
        subscription.updated_at = datetime.now(UTC)
    payment.revoked_at = datetime.now(UTC)
    payment.revoke_reason = cleaned
    audit_operator(
        db,
        operator,
        "billing.transfer_revoke",
        tenant_id=row.tenant_id,
        after={"payment_id": str(payment.id), "invoice_id": str(row.invoice_id)},
        reason=cleaned,
    )
    db.commit()
    from app.console.entitlements import publish_purchased

    publish_purchased(settings, row.tenant_id)
    _notify_owner(
        db,
        row.tenant_id,
        "Subscription access was updated",
        "An administrator revoked the activation on your invoice. "
        "Sign in to AxizPOS Business to read the status. Paid features stay locked until a payment is verified again.",
    )
    db.refresh(payment)
    return payment


def _console_after_submit(db: Session, row: BillingTransfer) -> None:
    """The receipt is already committed. A notice failure leaves that receipt in place."""
    try:
        from app.console import payment_notices

        payment_notices.announce_submission(db, row)
        db.commit()
    except Exception:
        logger.exception("Console was not notified about transfer %s", row.id)
        db.rollback()


def _console_after_decision(db: Session, row: BillingTransfer) -> None:
    """Queue a count update on the decision's own commit. A queue failure still commits the decision."""
    try:
        from app.console import payment_notices

        payment_notices.announce_status(db, row)
    except Exception:
        logger.exception("Console count was not queued for transfer %s", row.id)


def _notify_owner(db: Session, tenant_id: uuid.UUID, heading: str, body: str) -> None:
    """Emails the store owner when a mailbox is configured. A mail failure does not change the payment."""
    tenant = db.get(Tenant, tenant_id)
    address = "" if tenant is None or tenant.owner_email is None else tenant.owner_email.strip()
    if not address:
        return
    try:
        from app.console import mail
        from app.core.config import get_settings
        from app.services.email_brand import notice_html
        from app.services.messaging_providers import Outgoing

        settings = get_settings()
        mail.send(
            settings,
            Outgoing(
                to=address,
                subject=heading,
                body=body,
                html=notice_html(heading=heading, body=body, support_email=settings.support_email),
            ),
        )
    except Exception:
        return


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
