"""Commercial payments for plugins, subscriptions, and later products.

Card charges go through a provider adapter. With no provider configured, a card attempt is refused.
Selecting cash or bank transfer does not mark the invoice paid.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.tenancy.models import (
    BillingInvoice,
    CommercialPayment,
    CommercialPaymentEvent,
    PlatformPaymentMethod,
    Tenant,
)

PURPOSES = (
    "PLUGIN_PURCHASE",
    "SUBSCRIPTION",
    "SUBSCRIPTION_RENEWAL",
    "SUBSCRIPTION_UPGRADE",
    "ADDON_PURCHASE",
)
OPEN = ("PENDING", "SUBMITTED", "REVIEW_REQUIRED")
SANDBOX_SCENARIOS = ("approved", "declined", "processing", "pending", "timeout", "unknown", "unavailable", "invalid")
_SANDBOX_TRANSITIONS = {
    "PENDING": {"PROCESSING", "DECLINED", "FAILED", "SANDBOX_UNKNOWN", "CANCELLED"},
    "PROCESSING": {"SANDBOX_APPROVED", "DECLINED", "FAILED", "SANDBOX_UNKNOWN"},
    "SANDBOX_UNKNOWN": {"SANDBOX_APPROVED", "DECLINED"},
    "SUBMITTED": set(),
    "REVIEW_REQUIRED": set(),
    "DECLINED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "SANDBOX_APPROVED": set(),
    "SUCCEEDED": set(),
}


class CardProvider(Protocol):
    code: str

    def create_session(self, payment: CommercialPayment) -> str: ...

    def verify(self, payload: bytes, signature: str | None) -> None: ...


class UnconfiguredCardProvider:
    """The gateway has not been chosen. This adapter never reports a successful charge."""

    code = ""

    def create_session(self, payment: CommercialPayment) -> str:
        raise ApiError(422, "card_not_configured", "No card provider is configured.")

    def verify(self, payload: bytes, signature: str | None) -> None:
        raise ApiError(422, "card_not_configured", "No card provider is configured.")


class AxizPosSandboxCardProvider:
    """Deterministic test adapter. It never contacts a network and never settles an invoice."""

    code = "axizpos_test"

    def create_session(self, payment: CommercialPayment) -> str:
        if payment.environment != "sandbox":
            raise ApiError(422, "sandbox_only", "The test card adapter only accepts a sandbox payment.")
        return f"TEST-{payment.id.hex[:16]}"

    def verify(self, payload: bytes, signature: str | None) -> None:
        raise ApiError(422, "sandbox_webhook_secret", "Verify the sandbox notice with the sandbox secret.")


def sandbox_card_allowed(settings: Settings) -> bool:
    """Development may use the internal test adapter. Production and unmarked tests may not."""
    env = getattr(settings, "app_env", "")
    if env == "production" or getattr(settings, "payment_live_card_enabled", False):
        return False
    if getattr(settings, "payment_sandbox_enabled", False):
        return True
    return env in ("development", "dev")


def card_provider(settings: Settings | None = None) -> CardProvider:
    if settings is not None and sandbox_card_allowed(settings):
        return AxizPosSandboxCardProvider()
    return UnconfiguredCardProvider()


def transition(payment: CommercialPayment, status: str) -> None:
    """Move a payment only along the server state machine. The browser cannot name the next state."""
    allowed = _SANDBOX_TRANSITIONS.get(payment.status, set())
    if status not in allowed:
        raise ApiError(409, "invalid_transition", f"A {payment.status} payment cannot become {status}.")
    payment.status = status
    payment.updated_at = datetime.now(UTC)


def _event(db: Session, payment: CommercialPayment, event_type: str, note: str = "") -> None:
    db.add(CommercialPaymentEvent(payment_id=payment.id, event_type=event_type, note=note[:500]))


def ensure_methods(db: Session) -> None:
    have = {row.code for row in db.scalars(select(PlatformPaymentMethod))}
    now = datetime.now(UTC)
    seeds = [
        (
            "bank_transfer",
            "Bank transfer",
            "BANK_TRANSFER",
            "manual",
            True,
            10,
            list(PURPOSES),
            "Transfer the invoice total and upload the receipt.",
        ),
        ("card", "Credit or debit card", "CARD", "", False, 20, list(PURPOSES), "No card provider is configured."),
        (
            "cash",
            "Cash",
            "CASH",
            "manual",
            False,
            30,
            ["PLUGIN_PURCHASE", "ADDON_PURCHASE"],
            "Cash stays unpaid until authorized staff record the collection.",
        ),
    ]
    added = False
    for code, name, category, provider, enabled, order, purposes, instructions in seeds:
        if code in have:
            continue
        added = True
        db.add(
            PlatformPaymentMethod(
                code=code,
                display_name=name,
                category=category,
                provider_code=provider,
                is_enabled=enabled,
                currencies=["AED"],
                purposes=purposes,
                sort_order=order,
                instructions=instructions,
                created_at=now,
                updated_at=now,
            )
        )
    if added:
        db.commit()


def method_availability(
    row: PlatformPaymentMethod, *, bank_ready: bool, purpose: str, sandbox_card: bool = False
) -> tuple[bool, str]:
    """Whether a tenant may start this method. Live card stays unavailable."""
    if purpose and purpose not in (row.purposes or []):
        return False, "This payment method is not offered for this purchase."
    if row.category == "CARD":
        if sandbox_card:
            return True, "TEST sandbox. No real card is charged."
        return False, row.instructions or "No card provider is configured."
    if not row.is_enabled:
        return False, "This payment method is turned off."
    if row.category == "BANK_TRANSFER" and not bank_ready:
        return False, "Bank transfer details have not been published yet."
    return True, ""


def list_methods(db: Session, purpose: str, *, sandbox_card: bool = False) -> list[dict]:
    ensure_methods(db)
    from app.console.transfers import active_bank_snapshot

    bank_ready = active_bank_snapshot(db) is not None
    rows = list(
        db.scalars(
            select(PlatformPaymentMethod).order_by(PlatformPaymentMethod.sort_order, PlatformPaymentMethod.code)
        )
    )
    found = []
    for row in rows:
        available, reason = method_availability(
            row, bank_ready=bank_ready, purpose=purpose, sandbox_card=sandbox_card
        )
        found.append(
            {
                "code": row.code,
                "display_name": row.display_name,
                "category": row.category,
                "available": available,
                "is_enabled": row.is_enabled,
                "test_mode": row.category == "CARD" and sandbox_card,
                "reason": reason or row.instructions,
                "sort_order": row.sort_order,
                "instructions": row.instructions,
            }
        )
    return found


def set_enabled(db: Session, code: str, enabled: bool) -> PlatformPaymentMethod:
    ensure_methods(db)
    row = db.scalar(select(PlatformPaymentMethod).where(PlatformPaymentMethod.code == code))
    if row is None:
        raise ApiError(404, "unknown_method", "That payment method does not exist.")
    if row.category == "CARD" and enabled:
        raise ApiError(422, "card_not_configured", "Choose a card provider before enabling card payments.")
    row.is_enabled = enabled
    row.updated_at = datetime.now(UTC)
    db.commit()
    return row


def _payment_out(payment: CommercialPayment, bank: dict[str, str] | None) -> dict:
    return {
        "id": payment.id,
        "invoice_id": payment.invoice_id,
        "method_code": payment.method_code,
        "purpose_type": payment.purpose_type,
        "purpose_ref": payment.purpose_ref,
        "amount_fils": payment.amount_fils,
        "currency": payment.currency,
        "status": payment.status,
        "reference": payment.reference,
        "environment": payment.environment,
        "scenario": payment.scenario,
        "test_mode": payment.environment == "sandbox",
        "provider_reference": payment.provider_reference,
        "failure_reason": payment.failure_reason,
        "bank": bank,
    }


def start_plugin_payment(
    db: Session,
    settings: Settings,
    tenant: Tenant,
    actor_id: uuid.UUID,
    *,
    purpose_type: str,
    addon_code: str,
    method_code: str,
    idempotency_key: str,
    scenario: str = "",
) -> dict:
    if purpose_type not in ("PLUGIN_PURCHASE", "ADDON_PURCHASE"):
        raise ApiError(422, "unsupported_purpose", "This checkout starts a plugin purchase.")
    key = idempotency_key.strip()
    if len(key) < 8:
        raise ApiError(422, "idempotency_required", "Send an idempotency key for this checkout.")
    existing = db.scalar(
        select(CommercialPayment).where(
            CommercialPayment.tenant_id == tenant.id, CommercialPayment.idempotency_key == key
        )
    )
    if existing is not None:
        bank = None
        if existing.invoice_id is not None:
            invoice = db.get(BillingInvoice, existing.invoice_id)
            bank = None if invoice is None else invoice.bank_snapshot
        return _payment_out(existing, bank)
    sandbox = sandbox_card_allowed(settings)
    methods = {row["code"]: row for row in list_methods(db, purpose_type, sandbox_card=sandbox)}
    chosen = methods.get(method_code)
    if chosen is None or not chosen["available"]:
        reason = "Choose an available payment method." if chosen is None else str(chosen["reason"])
        raise ApiError(422, "method_unavailable", reason)
    row = db.scalar(select(PlatformPaymentMethod).where(PlatformPaymentMethod.code == method_code))
    assert row is not None
    if row.category == "CARD" and not sandbox:
        refused = CommercialPayment(
            tenant_id=tenant.id,
            method_code=method_code,
            purpose_type=purpose_type,
            purpose_ref=addon_code,
            amount_fils=1,
            currency="AED",
            idempotency_key=key,
        )
        card_provider(settings).create_session(refused)
    if row.category == "CARD" and sandbox:
        return _start_sandbox_card(
            db,
            settings,
            tenant,
            actor_id,
            purpose_type=purpose_type,
            addon_code=addon_code,
            method_code=method_code,
            idempotency_key=key,
            scenario=scenario,
        )
    from app.console.billing import create_addon_checkout

    checkout = create_addon_checkout(
        db, settings, tenant, actor_id, addon_code, require_bank=row.category == "BANK_TRANSFER"
    )
    open_payment = db.scalar(
        select(CommercialPayment).where(
            CommercialPayment.tenant_id == tenant.id,
            CommercialPayment.invoice_id == checkout.checkout_id,
            CommercialPayment.status.in_(OPEN),
        )
    )
    if open_payment is not None:
        return _payment_out(open_payment, checkout.bank if row.category == "BANK_TRANSFER" else None)
    status = "REVIEW_REQUIRED" if row.category == "CASH" else "PENDING"
    payment = CommercialPayment(
        tenant_id=tenant.id,
        invoice_id=checkout.checkout_id,
        method_code=method_code,
        purpose_type=purpose_type,
        purpose_ref=addon_code,
        amount_fils=checkout.quote.total_fils,
        currency=checkout.quote.currency,
        status=status,
        idempotency_key=key,
        reference=f"AX{secrets.token_hex(4).upper()}",
        initiated_by=actor_id,
    )
    db.add(payment)
    db.flush()
    _event(db, payment, "PAYMENT_INITIATED", row.category)
    db.commit()
    return _payment_out(payment, checkout.bank if row.category == "BANK_TRANSFER" else None)


def payment_for_tenant(db: Session, tenant_id: uuid.UUID, payment_id: uuid.UUID) -> dict:
    payment = db.get(CommercialPayment, payment_id)
    if payment is None or payment.tenant_id != tenant_id:
        raise ApiError(404, "not_found", "Payment was not found.")
    return _payment_out(payment, _bank(db, payment))


def list_review_payments(db: Session) -> list[dict]:
    rows = db.scalars(
        select(CommercialPayment)
        .where(CommercialPayment.status == "REVIEW_REQUIRED")
        .order_by(CommercialPayment.created_at.desc())
        .limit(50)
    )
    return [_payment_out(row, _bank(db, row)) for row in rows]


def _bank(db: Session, payment: CommercialPayment) -> dict | None:
    if payment.invoice_id is None or payment.method_code != "bank_transfer":
        return None
    invoice = db.get(BillingInvoice, payment.invoice_id)
    if invoice is None:
        return None
    return invoice.bank_snapshot


def mark_invoice_submitted(db: Session, invoice_id: uuid.UUID) -> None:
    """A receipt upload moves a pending transfer to review. It does not mark the invoice paid."""
    now = datetime.now(UTC)
    rows = db.scalars(
        select(CommercialPayment).where(
            CommercialPayment.invoice_id == invoice_id, CommercialPayment.status == "PENDING"
        )
    )
    for payment in rows:
        payment.status = "SUBMITTED"
        payment.updated_at = now
        _event(db, payment, "PAYMENT_SUBMITTED", "Receipt uploaded")


def mark_invoice_succeeded(db: Session, invoice_id: uuid.UUID) -> None:
    """Called after a verified bank credit. A second approval does not create another success event."""
    rows = list(
        db.scalars(
            select(CommercialPayment).where(
                CommercialPayment.invoice_id == invoice_id, CommercialPayment.status.in_(OPEN)
            )
        )
    )
    now = datetime.now(UTC)
    for payment in rows:
        if payment.environment == "sandbox":
            continue
        payment.status = "SUCCEEDED"
        payment.completed_at = now
        payment.updated_at = now
        _event(db, payment, "PAYMENT_SUCCEEDED", "Verified")


def record_cash(
    db: Session, settings: Settings, payment_id: uuid.UUID, operator_id: uuid.UUID, reference: str
) -> CommercialPayment:
    payment = db.get(CommercialPayment, payment_id)
    if payment is None:
        raise ApiError(404, "not_found", "Payment was not found.")
    if payment.status == "SUCCEEDED":
        return payment
    if payment.environment == "sandbox":
        raise ApiError(409, "sandbox_payment", "A test payment cannot be recorded as live cash.")
    if payment.method_code != "cash" or payment.status != "REVIEW_REQUIRED":
        raise ApiError(409, "payment_closed", "This payment is not waiting for a cash collection.")
    cleaned = reference.strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reference_required", "Enter the cash receipt reference.")
    invoice = db.get(BillingInvoice, payment.invoice_id) if payment.invoice_id else None
    tenant = db.get(Tenant, payment.tenant_id)
    if invoice is None or tenant is None or invoice.status == "paid":
        raise ApiError(409, "invoice_not_payable", "This invoice cannot take another payment.")
    from app.console.billing import _activate

    invoice.status = "paid"
    invoice.paid_at = datetime.now(UTC)
    _activate(db, tenant, invoice)
    payment.status = "SUCCEEDED"
    payment.reference = cleaned[:40]
    payment.completed_at = invoice.paid_at
    payment.updated_at = invoice.paid_at
    _event(db, payment, "PAYMENT_VERIFIED", f"Collected by {operator_id}")
    db.commit()
    from app.console.entitlements import publish_purchased

    publish_purchased(settings, payment.tenant_id)
    db.refresh(payment)
    return payment


def _start_sandbox_card(
    db: Session,
    settings: Settings,
    tenant: Tenant,
    actor_id: uuid.UUID,
    *,
    purpose_type: str,
    addon_code: str,
    method_code: str,
    idempotency_key: str,
    scenario: str,
) -> dict:
    """Quote the add-on, then store a TEST attempt. The invoice is not issued and nothing is activated."""
    from app.console.billing import quote_addon

    priced = quote_addon(db, settings, tenant, addon_code)
    payment = CommercialPayment(
        tenant_id=tenant.id,
        invoice_id=None,
        method_code=method_code,
        purpose_type=purpose_type,
        purpose_ref=addon_code,
        amount_fils=priced.total_fils,
        currency=priced.currency,
        status="PENDING",
        idempotency_key=idempotency_key,
        reference=f"TEST{secrets.token_hex(4).upper()}",
        environment="sandbox",
        scenario="",
        initiated_by=actor_id,
    )
    db.add(payment)
    db.flush()
    payment.provider_reference = card_provider(settings).create_session(payment)
    _event(db, payment, "PAYMENT_INITIATED", "sandbox")
    if scenario:
        apply_sandbox_scenario(db, payment, scenario)
    db.commit()
    return _payment_out(payment, None)


def apply_sandbox_scenario(db: Session, payment: CommercialPayment, scenario: str) -> CommercialPayment:
    """Apply one deterministic test result. A sandbox approval does not pay the invoice."""
    if payment.environment != "sandbox":
        raise ApiError(409, "sandbox_only", "A live payment cannot take a test result.")
    name = scenario.strip().lower()
    if name not in SANDBOX_SCENARIOS:
        raise ApiError(422, "unknown_scenario", "Choose a sandbox scenario the test provider knows.")
    if payment.status in ("SANDBOX_APPROVED", "DECLINED", "FAILED", "CANCELLED"):
        raise ApiError(409, "payment_closed", "This test payment already has a final result.")
    payment.scenario = name
    if name == "pending":
        _event(db, payment, "PAYMENT_PENDING", "sandbox")
    elif name == "processing":
        transition(payment, "PROCESSING")
        _event(db, payment, "PAYMENT_PROCESSING", "sandbox")
    elif name == "approved":
        if payment.status == "PENDING":
            transition(payment, "PROCESSING")
        transition(payment, "SANDBOX_APPROVED")
        payment.completed_at = datetime.now(UTC)
        _event(db, payment, "SANDBOX_APPROVED", "TEST approved. No invoice was paid.")
    elif name == "declined":
        if payment.status == "PENDING":
            transition(payment, "PROCESSING")
        transition(payment, "DECLINED")
        payment.failure_reason = "The test provider declined this payment."
        _event(db, payment, "PAYMENT_DECLINED", "sandbox")
    elif name in ("timeout", "unknown"):
        if payment.status == "PENDING":
            transition(payment, "SANDBOX_UNKNOWN")
        elif payment.status == "PROCESSING":
            transition(payment, "SANDBOX_UNKNOWN")
        _event(db, payment, "PAYMENT_UNKNOWN", "sandbox timeout" if name == "timeout" else "sandbox unknown")
    elif name == "unavailable":
        transition(payment, "FAILED")
        payment.failure_reason = "The test provider was unavailable."
        _event(db, payment, "PAYMENT_FAILED", "sandbox unavailable")
    else:
        transition(payment, "FAILED")
        payment.failure_reason = "The test provider returned a response this server does not accept."
        _event(db, payment, "PAYMENT_FAILED", "sandbox invalid")
    if payment.invoice_id is not None:
        invoice = db.get(BillingInvoice, payment.invoice_id)
        if invoice is not None and invoice.status == "paid":
            raise ApiError(409, "sandbox_settlement", "A test result cannot settle an invoice.")
    return payment


def inquire_sandbox(db: Session, payment: CommercialPayment) -> CommercialPayment:
    """A timeout stays unknown until a later test result names approved or declined."""
    if payment.environment != "sandbox":
        raise ApiError(409, "sandbox_only", "Status inquiry for a live card is not available.")
    _event(db, payment, "STATUS_INQUIRY", payment.status)
    return payment


def list_sandbox_payments(db: Session) -> list[dict]:
    rows = db.scalars(
        select(CommercialPayment)
        .where(CommercialPayment.environment == "sandbox")
        .order_by(CommercialPayment.created_at.desc())
        .limit(50)
    )
    return [_payment_out(row, None) for row in rows]


def accept_sandbox_event(
    db: Session, settings: Settings, body: bytes, signature: str | None, timestamp: str | None
) -> dict:
    """A signed test notice. It cannot update a live payment or pay an invoice."""
    secret = (getattr(settings, "payment_sandbox_webhook_secret", None) or "").encode()
    if not secret or not sandbox_card_allowed(settings):
        raise ApiError(404, "sandbox_disabled", "Sandbox notices are not accepted on this server.")
    if not signature or not timestamp:
        raise ApiError(401, "invalid_signature", "The sandbox notice has no signature.")
    try:
        sent = int(timestamp)
    except ValueError as exc:
        raise ApiError(401, "invalid_signature", "The sandbox notice has no signature.") from exc
    if abs(int(datetime.now(UTC).timestamp()) - sent) > 300:
        raise ApiError(401, "replayed_event", "The sandbox notice is too old.")
    expected = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise ApiError(401, "invalid_signature", "The sandbox notice could not be verified.")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid_body", "The sandbox notice was not JSON.") from exc
    provider_ok = isinstance(payload, dict) and payload.get("environment") == "sandbox"
    provider_ok = provider_ok and payload.get("provider") == "axizpos_test"
    if not provider_ok:
        raise ApiError(422, "sandbox_only", "This notice is not an AxizPOS sandbox event.")
    event_id = str(payload.get("event_id") or "").strip()
    if len(event_id) < 8:
        raise ApiError(422, "event_id_required", "The sandbox notice needs an event id.")
    marker = f"sandbox-event:{event_id}"[:500]
    if db.scalar(select(CommercialPaymentEvent.id).where(CommercialPaymentEvent.note == marker)) is not None:
        raise ApiError(409, "duplicate_event", "This sandbox notice was already processed.")
    payment_id = payload.get("payment_id")
    try:
        found_id = uuid.UUID(str(payment_id))
    except ValueError as exc:
        raise ApiError(422, "unknown_payment", "The sandbox notice names no test payment.") from exc
    payment = db.get(CommercialPayment, found_id)
    if payment is None or payment.environment != "sandbox":
        raise ApiError(409, "sandbox_only", "A sandbox notice cannot update a live payment.")
    if int(payload.get("amount_fils") or -1) != payment.amount_fils or payload.get("currency") != payment.currency:
        raise ApiError(422, "amount_mismatch", "The sandbox notice does not match the quoted amount.")
    apply_sandbox_scenario(db, payment, str(payload.get("scenario") or ""))
    _event(db, payment, "SANDBOX_WEBHOOK", marker)
    db.commit()
    return _payment_out(payment, None)
