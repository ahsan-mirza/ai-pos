"""QR payment intents: create, render the QR (dev link or EMVCo merchant-presented code), confirm by signed
webhook, and consume exactly once as a sale's `qr` tender."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.models.payment_intent import PaymentIntent
from app.models.store import Store
from app.schemas.payments import IntentCreate, IntentOut
from app.services.settings_service import business_currency

ISO_NUMERIC = {"AED": "784", "SAR": "682", "USD": "840", "EUR": "978", "GBP": "826", "INR": "356", "PKR": "586"}


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def emvco_payload(settings: Settings, *, amount_cents: int, currency: str, reference: str) -> str:
    """EMVCo merchant-presented QR (dynamic, point of initiation 12) with the amount and our reference."""
    account = settings.emvco_merchant_account or "AIPOS-DEV-MERCHANT"
    body = "".join(
        [
            _tlv("00", "01"),
            _tlv("01", "12"),
            _tlv("26", _tlv("00", "ae.aipos") + _tlv("01", account[:25])),
            _tlv("52", settings.emvco_mcc),
            _tlv("53", ISO_NUMERIC.get(currency, "784")),
            _tlv("54", f"{amount_cents / 100:.2f}"),
            _tlv("58", "AE"),
            _tlv("59", settings.emvco_merchant_name[:25]),
            _tlv("60", settings.emvco_merchant_city[:15]),
            _tlv("62", _tlv("05", reference[:25])),
        ]
    )
    unsigned = body + "6304"
    return unsigned + crc16_ccitt(unsigned)


def _aware(value: datetime | None) -> datetime | None:
    return None if value is None else (value if value.tzinfo else value.replace(tzinfo=UTC))


def intent_fields(intent: PaymentIntent) -> dict:
    return {
        "id": intent.id,
        "channel": intent.channel or "QR",
        "provider": intent.provider,
        "amount_cents": intent.amount_cents,
        "currency": intent.currency,
        "reference": intent.reference,
        "qr_payload": intent.qr_payload,
        "status": intent.status,
        "expires_at": _aware(intent.expires_at),
        "paid_at": _aware(intent.paid_at),
        "sale_id": intent.sale_id,
        "customer_url": intent.customer_url,
        "auth_code": intent.auth_code,
        "card_brand": intent.card_brand,
        "card_last4": intent.card_last4,
        "failure_reason": intent.failure_reason,
        "refunded_cents": intent.refunded_cents or 0,
        "terminal_id": intent.terminal_id,
        "simulated": intent.provider == "simulator" or (intent.provider_ref or "").startswith("sim-"),
    }


def _out(intent: PaymentIntent) -> IntentOut:
    return IntentOut(**intent_fields(intent))


def _expire(db: Session, intent: PaymentIntent) -> None:
    expires = intent.expires_at if intent.expires_at.tzinfo else intent.expires_at.replace(tzinfo=UTC)
    if intent.status == "PENDING" and expires < datetime.now(UTC):
        intent.status = "EXPIRED"
        db.commit()


def create_intent(db: Session, settings: Settings, data: IntentCreate, store_scope: uuid.UUID | None) -> IntentOut:
    store_id = store_scope or data.store_id
    if store_id is None or db.get(Store, store_id) is None:
        raise ApiError(422, "validation_error", "Choose the store taking the payment.")
    currency = business_currency(db)
    reference = data.reference or f"AIP{secrets.token_hex(4).upper()}"
    intent = PaymentIntent(
        store_id=store_id,
        provider=settings.payment_provider,
        amount_cents=data.amount_cents,
        currency=currency,
        reference=reference,
        qr_payload="",
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.payment_intent_minutes),
    )
    db.add(intent)
    db.flush()
    if settings.payment_provider == "emvco":
        intent.qr_payload = emvco_payload(
            settings, amount_cents=data.amount_cents, currency=currency, reference=reference
        )
    else:
        intent.qr_payload = f"{settings.public_base_url}/api/v1/payments/dev/{intent.id}/pay"
    db.commit()
    return _out(intent)


def get_intent(
    db: Session, intent_id: uuid.UUID, store_scope: uuid.UUID | None, settings: Settings | None = None
) -> IntentOut:
    intent = db.get(PaymentIntent, intent_id)
    if intent is None or (store_scope is not None and intent.store_id != store_scope):
        raise ApiError(404, "not_found", "Payment was not found.")
    if intent.channel != "QR" and settings is not None:
        from app.services import integrated_payment_service

        integrated_payment_service.refresh(db, settings, intent)
    else:
        _expire(db, intent)
    return _out(intent)


def cancel_intent(
    db: Session, intent_id: uuid.UUID, store_scope: uuid.UUID | None, settings: Settings | None = None
) -> IntentOut:
    intent = db.get(PaymentIntent, intent_id)
    if intent is None or (store_scope is not None and intent.store_id != store_scope):
        raise ApiError(404, "not_found", "Payment was not found.")
    if intent.channel != "QR" and settings is not None:
        from app.services import integrated_payment_service

        integrated_payment_service.cancel(db, settings, intent)
        return _out(intent)
    if intent.status == "PENDING":
        intent.status = "CANCELLED"
        db.commit()
    return _out(intent)


def _mark_paid(db: Session, intent: PaymentIntent, provider_ref: str | None, amount_cents: int | None) -> IntentOut:
    if amount_cents is not None and amount_cents != intent.amount_cents:
        raise ApiError(422, "amount_mismatch", "The paid amount does not match the payment request.")
    changed = db.execute(
        update(PaymentIntent)
        .where(PaymentIntent.id == intent.id, PaymentIntent.status == "PENDING")
        .values(status="PAID", paid_at=datetime.now(UTC), provider_ref=provider_ref)
    ).rowcount
    db.commit()
    db.refresh(intent)
    if not changed and intent.status != "PAID":
        raise ApiError(409, "intent_closed", f"This payment is {intent.status.lower()}.")
    return _out(intent)


def simulate_payment(db: Session, settings: Settings, intent_id: uuid.UUID) -> IntentOut:
    if settings.payment_provider != "dev":
        raise ApiError(404, "not_found", "Payment simulation is only available with the dev provider.")
    intent = db.get(PaymentIntent, intent_id)
    if intent is None:
        raise ApiError(404, "not_found", "Payment was not found.")
    _expire(db, intent)
    return _mark_paid(db, intent, f"dev-{secrets.token_hex(4)}", None)


def verify_signature(settings: Settings, body: bytes, signature: str | None) -> None:
    secret = settings.payment_webhook_secret
    if not secret:
        raise ApiError(503, "not_configured", "PAYMENT_WEBHOOK_SECRET is not configured.")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if signature is None or not hmac.compare_digest(expected, signature.lower().removeprefix("sha256=")):
        raise ApiError(401, "bad_signature", "Webhook signature does not match.")


def handle_webhook(db: Session, settings: Settings, body: bytes, signature: str | None, payload: dict) -> IntentOut:
    verify_signature(settings, body, signature)
    reference = str(payload.get("reference") or "")
    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.reference == reference, PaymentIntent.channel == "QR"))
    if intent is None:
        raise ApiError(404, "not_found", "No payment has this reference.")
    if str(payload.get("status", "")).lower() not in ("paid", "succeeded", "success", "completed"):
        return _out(intent)
    amount = payload.get("amount_cents")
    return _mark_paid(
        db, intent, str(payload.get("transaction_id") or "") or None, int(amount) if amount is not None else None
    )


CHANNEL_OF_METHOD = {"qr": "QR", "card": "CARD", "bnpl": "BNPL"}
_NAMES = {"QR": "QR payment", "CARD": "card payment", "BNPL": "pay-later payment"}


def consume_for_sale(
    db: Session, intent_id: uuid.UUID, *, sale_id: uuid.UUID, amount_cents: int, store_id, method: str = "qr"
) -> None:
    """Called while recording a sale with a `qr`, `card` or `bnpl` tender that points at a provider payment.
    Rejects unpaid, mismatched, wrong-channel or already-used intents."""
    channel = CHANNEL_OF_METHOD[method]
    name = _NAMES[channel]
    intent = db.get(PaymentIntent, intent_id)
    if intent is None or intent.store_id != store_id or (intent.channel or "QR") != channel:
        raise SyncRejected(f"The {name} was not found for this store.")
    if intent.status != "PAID":
        raise SyncRejected(f"The {name} is {intent.status.lower()}, not paid.")
    if intent.sale_id is not None and intent.sale_id != sale_id:
        raise SyncRejected(f"This {name} already paid for another sale.")
    if intent.amount_cents != amount_cents:
        raise SyncRejected(f"The tender amount does not match the {name}.")
    intent.sale_id = sale_id
