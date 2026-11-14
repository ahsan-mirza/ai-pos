"""Plan-change requests.

A request records what the tenant asked for and which existing invoice pays for it.
Creating a request, issuing an invoice, or uploading a receipt does not change the
subscription. Activation stays in billing._activate, which only the existing
verification path calls.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console import billing
from app.core.config import Settings
from app.core.errors import ApiError
from app.schemas.billing import ChangeEventOut, ChangeOut, CheckoutIn, CheckoutOut, QuoteOut
from app.tenancy.models import (
    OPEN_SUBSCRIPTION_CHANGE_STATUSES,
    BillingCycle,
    BillingInvoice,
    BillingPlan,
    Subscription,
    SubscriptionChangeEvent,
    SubscriptionChangeRequest,
    Tenant,
)

QUOTE_HOLD = timedelta(days=14)
ISSUE_CLAIM = timedelta(minutes=2)
TERMINAL = frozenset({"completed", "cancelled", "rejected", "expired", "failed"})
PUBLISHED = frozenset({"FREE", "GROWTH", "PRO_AI"})


def expire_stale(db: Session, now: datetime | None = None) -> None:
    """Closes quoted requests that were never invoiced. Invoiced requests follow the invoice."""
    moment = now or datetime.now(UTC)
    rows = db.scalars(
        select(SubscriptionChangeRequest).where(
            SubscriptionChangeRequest.status == "quoted",
            SubscriptionChangeRequest.expires_at.is_not(None),
            SubscriptionChangeRequest.expires_at < moment,
        )
    )
    changed = False
    for row in rows:
        _append(db, row, "expired", actor_type="system", reason="The quote expired before an invoice was issued.")
        changed = True
    if changed:
        db.commit()


def create_request(
    db: Session,
    tenant: Tenant,
    plan_code: str,
    cycle_code: str,
    actor_id: uuid.UUID,
    *,
    stores: dict | None,
    country: str | None,
    onboarding: bool = False,
) -> SubscriptionChangeRequest:
    expire_stale(db)
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    if subscription is None:
        raise ApiError(409, "no_subscription", "This store has no subscription to change.")
    current_plan = db.get(BillingPlan, subscription.plan_id)
    current_cycle = db.get(BillingCycle, subscription.cycle_id)
    if current_plan is None or current_cycle is None:
        raise ApiError(409, "no_subscription", "This store has no subscription to change.")
    code = plan_code.strip().upper()
    cycle = cycle_code.strip().upper()
    if code == "ENTERPRISE":
        raise ApiError(422, "custom_pricing", "Enterprise is priced on a contract.")
    if code not in PUBLISHED:
        raise ApiError(422, "plan_not_selectable", "This plan cannot be selected.")
    if code == current_plan.code and cycle == current_cycle.code:
        raise ApiError(409, "already_current", "This plan and billing cycle are already active.")
    quote = billing.quote_for(db, code, cycle, [], [], stores, country, onboarding=onboarding, tenant_id=tenant.id)
    if quote.recurring_fils <= 0:
        raise ApiError(422, "nothing_to_bill", "The package has no recurring price.")
    open_row = _open_for(db, tenant.id)
    if open_row is not None:
        same_quote = (
            open_row.requested_plan_code == code
            and open_row.requested_cycle_code == cycle
            and open_row.status == "quoted"
        )
        if same_quote and _includes_onboarding(open_row.quote_snapshot) == onboarding:
            return open_row
        if same_quote:
            now = datetime.now(UTC)
            open_row.quote_snapshot = quote.model_dump(mode="json")
            open_row.updated_at = now
            open_row.expires_at = now + QUOTE_HOLD
            db.commit()
            db.refresh(open_row)
            return open_row
        raise ApiError(409, "change_in_progress", "A plan change is already open for this store.")
    now = datetime.now(UTC)
    row = SubscriptionChangeRequest(
        tenant_id=tenant.id,
        subscription_id=subscription.id,
        reference=f"SCR-{uuid.uuid4().hex[:8].upper()}",
        current_plan_code=current_plan.code,
        requested_plan_code=quote.plan_code,
        requested_cycle_code=quote.cycle_code,
        status="quoted",
        quote_snapshot=quote.model_dump(mode="json"),
        requested_by=actor_id,
        correlation_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        expires_at=now + QUOTE_HOLD,
    )
    db.add(row)
    db.flush()
    db.add(
        SubscriptionChangeEvent(
            request_id=row.id,
            previous_status=None,
            status="quoted",
            actor_type="tenant",
            actor_id=actor_id,
            reason=None,
            correlation_id=row.correlation_id,
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "change_in_progress", "A plan change is already open for this store.") from None
    db.refresh(row)
    return row


def issue_invoice(
    db: Session,
    settings: Settings,
    tenant: Tenant,
    actor_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CheckoutIn,
    stores: dict | None,
    country: str | None,
) -> tuple[SubscriptionChangeRequest, CheckoutOut]:
    """Issues the existing transfer invoice and links it. A second call returns the same invoice."""
    row = _owned(db, tenant.id, request_id)
    if payload.payment != "transfer":
        raise ApiError(422, "transfer_required", "A plan change from the business portal is paid by bank transfer.")
    same_plan = payload.plan_code.strip().upper() == row.requested_plan_code
    same_cycle = payload.cycle_code.strip().upper() == row.requested_cycle_code
    if not same_plan or not same_cycle:
        raise ApiError(422, "quote_mismatch", "The invoice does not match the plan change.")
    if bool(payload.onboarding) != _includes_onboarding(row.quote_snapshot):
        raise ApiError(422, "quote_mismatch", "The invoice does not match the plan change.")
    if row.status in TERMINAL:
        raise ApiError(409, "change_closed", "This plan change is already closed.")
    if row.invoice_id is not None:
        return row, _checkout_from(db, row)
    now = datetime.now(UTC)
    if row.status == "quoted":
        claimed = db.execute(
            update(SubscriptionChangeRequest)
            .where(
                SubscriptionChangeRequest.id == row.id,
                SubscriptionChangeRequest.tenant_id == tenant.id,
                SubscriptionChangeRequest.status == "quoted",
                SubscriptionChangeRequest.invoice_id.is_(None),
            )
            .values(status="pending_payment", issuing_at=now, updated_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:
            db.refresh(row)
            if row.invoice_id is not None:
                return row, _checkout_from(db, row)
            raise ApiError(409, "change_in_progress", "This plan change is already being invoiced.")
        _append(
            db,
            row,
            "pending_payment",
            actor_type="tenant",
            actor_id=actor_id,
            reason="Invoice requested.",
            previous="quoted",
        )
        db.commit()
    else:
        stale_before = now - ISSUE_CLAIM
        claimed = db.execute(
            update(SubscriptionChangeRequest)
            .where(
                SubscriptionChangeRequest.id == row.id,
                SubscriptionChangeRequest.tenant_id == tenant.id,
                SubscriptionChangeRequest.status == "pending_payment",
                SubscriptionChangeRequest.invoice_id.is_(None),
                (SubscriptionChangeRequest.issuing_at.is_(None))
                | (SubscriptionChangeRequest.issuing_at < stale_before),
            )
            .values(issuing_at=now, updated_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:
            db.refresh(row)
            if row.invoice_id is not None:
                return row, _checkout_from(db, row)
            raise ApiError(409, "change_in_progress", "This plan change is already being invoiced.")
    db.refresh(row)
    existing = _matching_invoice(db, row)
    if existing is not None:
        _attach(db, row, existing, actor_id)
        return row, _checkout_from(db, row)
    fresh = billing.quote_for(
        db,
        row.requested_plan_code,
        row.requested_cycle_code,
        [],
        [],
        stores,
        country,
        onboarding=_includes_onboarding(row.quote_snapshot),
        tenant_id=tenant.id,
    )
    stored = QuoteOut.model_validate(row.quote_snapshot)
    quote_changed = (
        fresh.total_fils != stored.total_fils
        or fresh.currency != stored.currency
        or fresh.discount_bps != stored.discount_bps
    )
    if quote_changed:
        _revert_issue(db, row)
        raise ApiError(409, "quote_changed", "The quote changed. Start the plan change again.")
    try:
        checkout = billing.create_checkout(db, settings, tenant, actor_id, payload, stores)
    except ApiError:
        db.rollback()
        _revert_issue(db, row)
        raise
    invoice = db.get(BillingInvoice, checkout.checkout_id)
    if invoice is None or invoice.tenant_id != tenant.id:
        raise ApiError(409, "invoice_mismatch", "The invoice does not belong to this store.")
    _attach(db, row, invoice, actor_id)
    db.refresh(row)
    return row, checkout


def list_requests(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[SubscriptionChangeRequest], int]:
    expire_stale(db)
    query = select(SubscriptionChangeRequest).where(SubscriptionChangeRequest.tenant_id == tenant_id)
    if status:
        query = query.where(SubscriptionChangeRequest.status == status)
    rows = list(
        db.scalars(query.order_by(SubscriptionChangeRequest.created_at.desc()).limit(limit).offset(offset))
    )
    total = len(
        list(db.scalars(select(SubscriptionChangeRequest.id).where(SubscriptionChangeRequest.tenant_id == tenant_id)))
    )
    if status:
        total = len(
            list(
                db.scalars(
                    select(SubscriptionChangeRequest.id).where(
                        SubscriptionChangeRequest.tenant_id == tenant_id,
                        SubscriptionChangeRequest.status == status,
                    )
                )
            )
        )
    return rows, total


def get_request(db: Session, tenant_id: uuid.UUID, request_id: uuid.UUID) -> SubscriptionChangeRequest:
    expire_stale(db)
    return _owned(db, tenant_id, request_id)


def cancel_request(
    db: Session, tenant_id: uuid.UUID, request_id: uuid.UUID, actor_id: uuid.UUID
) -> SubscriptionChangeRequest:
    row = _owned(db, tenant_id, request_id)
    if row.status == "completed":
        raise ApiError(409, "change_completed", "A completed plan change cannot be cancelled.")
    if row.status != "quoted":
        raise ApiError(409, "change_not_cancellable", "This plan change can no longer be cancelled.")
    now = datetime.now(UTC)
    row.cancelled_at = now
    _append(db, row, "cancelled", actor_type="tenant", actor_id=actor_id, reason="Cancelled by the store.")
    db.commit()
    db.refresh(row)
    return row


def note_payment_submitted(db: Session, invoice_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Links a receipt to the request. The subscription is unchanged."""
    row = _for_invoice(db, invoice_id, tenant_id)
    if row is None or row.status != "pending_payment":
        return
    now = datetime.now(UTC)
    row.payment_submitted_at = now
    row.rejection_reason = None
    _append(db, row, "payment_submitted", actor_type="tenant", reason="Payment proof submitted.")


def note_verified(db: Session, invoice_id: uuid.UUID, tenant_id: uuid.UUID, actor_id: uuid.UUID | None) -> None:
    """Records that the existing approval path verified payment and activated the plan.

    A second call does not add another completion event.
    """
    row = _for_invoice(db, invoice_id, tenant_id)
    if row is None or row.status in TERMINAL:
        return
    now = datetime.now(UTC)
    row.verified_at = now
    row.completed_at = now
    _append(
        db,
        row,
        "completed",
        actor_type="console",
        actor_id=actor_id,
        reason="Payment verified and the subscription was activated.",
    )


def note_proof_rejected(
    db: Session, invoice_id: uuid.UUID, tenant_id: uuid.UUID, reason: str, actor_id: uuid.UUID | None
) -> None:
    """A rejected receipt does not close the request. The store can send a corrected proof."""
    row = _for_invoice(db, invoice_id, tenant_id)
    if row is None or row.status in TERMINAL or row.status != "payment_submitted":
        return
    row.rejection_reason = reason
    _append(
        db,
        row,
        "pending_payment",
        actor_type="console",
        actor_id=actor_id,
        reason=reason,
    )


def present(db: Session, row: SubscriptionChangeRequest) -> ChangeOut:
    events = list(
        db.scalars(
            select(SubscriptionChangeEvent)
            .where(SubscriptionChangeEvent.request_id == row.id)
            .order_by(SubscriptionChangeEvent.created_at, SubscriptionChangeEvent.id)
        )
    )
    return ChangeOut(
        id=row.id,
        reference=row.reference,
        current_plan_code=row.current_plan_code,
        requested_plan_code=row.requested_plan_code,
        requested_cycle_code=row.requested_cycle_code,
        status=row.status,
        quote=QuoteOut.model_validate(row.quote_snapshot),
        invoice_id=row.invoice_id,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
        payment_submitted_at=row.payment_submitted_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        events=[
            ChangeEventOut(
                previous_status=event.previous_status,
                status=event.status,
                actor_type=event.actor_type,
                created_at=event.created_at,
                reason=event.reason,
            )
            for event in events
        ],
    )


def _includes_onboarding(snapshot: dict | None) -> bool:
    lines = snapshot.get("lines") if isinstance(snapshot, dict) else None
    if not isinstance(lines, list):
        return False
    return any(isinstance(line, dict) and line.get("code") == "onboarding" for line in lines)


def _owned(db: Session, tenant_id: uuid.UUID, request_id: uuid.UUID) -> SubscriptionChangeRequest:
    row = db.get(SubscriptionChangeRequest, request_id)
    if row is None or row.tenant_id != tenant_id:
        raise ApiError(404, "change_not_found", "That plan change does not exist.")
    return row


def _open_for(db: Session, tenant_id: uuid.UUID) -> SubscriptionChangeRequest | None:
    return db.scalar(
        select(SubscriptionChangeRequest).where(
            SubscriptionChangeRequest.tenant_id == tenant_id,
            SubscriptionChangeRequest.status.in_(OPEN_SUBSCRIPTION_CHANGE_STATUSES),
        )
    )


def _for_invoice(db: Session, invoice_id: uuid.UUID, tenant_id: uuid.UUID) -> SubscriptionChangeRequest | None:
    return db.scalar(
        select(SubscriptionChangeRequest).where(
            SubscriptionChangeRequest.invoice_id == invoice_id,
            SubscriptionChangeRequest.tenant_id == tenant_id,
        )
    )


def _matching_invoice(db: Session, row: SubscriptionChangeRequest) -> BillingInvoice | None:
    return db.scalar(
        select(BillingInvoice)
        .where(
            BillingInvoice.tenant_id == row.tenant_id,
            BillingInvoice.status == "pending",
            BillingInvoice.plan_code == row.requested_plan_code,
            BillingInvoice.cycle_code == row.requested_cycle_code,
            BillingInvoice.created_at >= row.created_at,
        )
        .order_by(BillingInvoice.created_at.desc())
    )


def _attach(db: Session, row: SubscriptionChangeRequest, invoice: BillingInvoice, actor_id: uuid.UUID) -> None:
    if invoice.tenant_id != row.tenant_id:
        raise ApiError(409, "invoice_mismatch", "The invoice does not belong to this store.")
    row.invoice_id = invoice.id
    row.issuing_at = None
    row.updated_at = datetime.now(UTC)
    if row.status != "pending_payment":
        _append(db, row, "pending_payment", actor_type="tenant", actor_id=actor_id, reason="Invoice issued.")
    db.commit()


def _checkout_from(db: Session, row: SubscriptionChangeRequest) -> CheckoutOut:
    invoice = db.get(BillingInvoice, row.invoice_id) if row.invoice_id else None
    if invoice is None or invoice.tenant_id != row.tenant_id:
        raise ApiError(409, "invoice_mismatch", "The invoice does not belong to this store.")
    return CheckoutOut(
        checkout_id=invoice.id,
        mode="transfer",
        url=None,
        quote=QuoteOut.model_validate(row.quote_snapshot),
        bank=invoice.bank_snapshot,
    )


def _revert_issue(db: Session, row: SubscriptionChangeRequest) -> None:
    current = db.get(SubscriptionChangeRequest, row.id)
    if current is None or current.invoice_id is not None or current.status != "pending_payment":
        return
    current.issuing_at = None
    _append(db, current, "quoted", actor_type="system", reason="The invoice was not issued.")
    db.commit()


def _append(
    db: Session,
    row: SubscriptionChangeRequest,
    status: str,
    *,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    previous: str | None = None,
) -> None:
    prior = previous if previous is not None else row.status
    now = datetime.now(UTC)
    row.status = status
    row.updated_at = now
    db.add(
        SubscriptionChangeEvent(
            request_id=row.id,
            previous_status=prior,
            status=status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            correlation_id=row.correlation_id,
            created_at=now,
        )
    )
