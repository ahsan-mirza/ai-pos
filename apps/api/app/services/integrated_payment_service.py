"""Card-terminal and buy-now-pay-later payments: push the amount to the provider, follow it to PAID by poll or
webhook (capturing BNPL authorisations at once), and refund through the same provider when goods come back.

The intent row is the state machine; adapters only talk to providers. Transitions out of an open state are
single atomic updates, so a webhook and a till poll racing each other settle it once."""

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.integrations.http import ProviderError
from app.integrations.payments import registry
from app.integrations.payments.base import LineItem, PaymentAdapter, PaymentRef, ProviderStatus, StartRequest
from app.integrations.payments.simulator import SimulatorAdapter
from app.models.payment_intent import PaymentIntent, PaymentRefund, PaymentTerminal
from app.models.sale import Sale
from app.models.store import Store
from app.schemas.payments import (
    BnplIntentCreate,
    CardIntentCreate,
    IntentOut,
    PaymentList,
    PaymentRow,
    PaymentsConfig,
    ProviderOut,
    RefundOut,
    TerminalCheck,
    TerminalIn,
    TerminalOut,
    TerminalPatch,
)
from app.services import audit
from app.services.payment_service import intent_fields
from app.services.settings_service import business_currency, cached_settings

log = logging.getLogger(__name__)

OPEN = ("PENDING", "AUTHORIZED")
BNPL_MINUTES = 30
REFUND_MAX_ATTEMPTS = 6
CHANNEL_OF_REFUND = {"original_card": "CARD", "original_bnpl": "BNPL"}


# --- Adapters and config -------------------------------------------------------------------------------------


def _adapter(settings: Settings, intent: PaymentIntent) -> PaymentAdapter:
    if intent.provider == "simulator" or (intent.provider_ref or "").startswith("sim-"):
        return registry.adapter(settings, "simulator", intent.channel)  # type: ignore[arg-type]
    return registry.adapter(settings, intent.provider, intent.channel)  # type: ignore[arg-type]


def simulator_controls(db: Session, settings: Settings) -> bool:
    """Approve/decline buttons for simulated payments: everywhere but live production tenants."""
    return settings.app_env != "production" or cached_settings(db).practice_mode


def _provider_out(info: registry.ProviderInfo) -> ProviderOut:
    return ProviderOut(
        name=info.name,
        label=info.label,
        channel=info.channel,
        configured=info.configured,
        simulated=info.simulated,
        missing=list(info.missing),
    )


def providers(settings: Settings) -> list[ProviderOut]:
    return [_provider_out(info) for info in registry.providers(settings)]


def _terminal_out(row: PaymentTerminal) -> TerminalOut:
    return TerminalOut(
        id=row.id,
        store_id=row.store_id,
        provider=row.provider,
        terminal_ref=row.terminal_ref,
        label=row.label,
        device_id=row.device_id,
        is_active=row.is_active,
        last_checked_at=row.last_checked_at,
        last_check_ok=row.last_check_ok,
    )


def _store_id(db: Session, scope: uuid.UUID | None, requested: uuid.UUID | None) -> uuid.UUID:
    store_id = scope or requested
    if store_id is None or db.get(Store, store_id) is None:
        raise ApiError(422, "validation_error", "Choose the store taking the payment.")
    return store_id


def active_terminals(db: Session, store_id: uuid.UUID) -> list[PaymentTerminal]:
    return list(
        db.scalars(
            select(PaymentTerminal)
            .where(PaymentTerminal.store_id == store_id, PaymentTerminal.is_active.is_(True))
            .order_by(PaymentTerminal.created_at)
        )
    )


def card_terminal_required(db: Session, store_id: uuid.UUID, *, at: datetime | None = None) -> bool:
    """A store with integrated terminals takes card payments through them; a manager can still override.
    `at` keeps sales rung up offline before the first terminal was added out of it."""
    if not has_capability(db, Capability.CARD_TERMINALS):
        return False
    filters = [PaymentTerminal.store_id == store_id, PaymentTerminal.is_active.is_(True)]
    if at is not None:
        filters.append(PaymentTerminal.created_at <= at)
    return (db.scalar(select(func.count(PaymentTerminal.id)).where(*filters)) or 0) > 0


def config(
    db: Session, settings: Settings, *, store_scope: uuid.UUID | None, store_id: uuid.UUID | None, device_id
) -> PaymentsConfig:
    infos = registry.providers(settings)
    card = next(info for info in infos if info.channel == "CARD")
    bnpl = [info for info in infos if info.channel == "BNPL"] if has_capability(db, Capability.BNPL) else []
    resolved = store_scope or store_id
    terminals = active_terminals(db, resolved) if resolved is not None else []
    if not has_capability(db, Capability.CARD_TERMINALS):
        terminals = []
    mine = next((row for row in terminals if device_id is not None and row.device_id == device_id), None)
    default = mine or (terminals[0] if terminals else None)
    return PaymentsConfig(
        card_provider=_provider_out(card),
        bnpl=[_provider_out(info) for info in bnpl],
        terminals=[_terminal_out(row) for row in terminals],
        card_terminal_required=bool(terminals),
        default_terminal_id=default.id if default is not None else None,
        simulator_controls=simulator_controls(db, settings),
    )


# --- Creating intents ----------------------------------------------------------------------------------------


def _new_intent(
    db: Session, *, store_id, channel: str, provider: str, amount_cents: int, minutes: int
) -> PaymentIntent:
    intent = PaymentIntent(
        store_id=store_id,
        channel=channel,
        provider=provider,
        amount_cents=amount_cents,
        currency=business_currency(db),
        reference=f"AIP{secrets.token_hex(4).upper()}",
        qr_payload="",
        status="PENDING",
        refunded_cents=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )
    db.add(intent)
    db.flush()
    return intent


def _urls(settings: Settings, intent: PaymentIntent) -> tuple[str, str]:
    base = settings.public_base_url.rstrip("/")
    return (
        f"{base}/api/v1/integrations/payments/return/{intent.id}",
        f"{base}/api/v1/integrations/payments/{intent.provider}/webhook",
    )


def _started(db: Session, intent: PaymentIntent, status: ProviderStatus) -> None:
    intent.provider_ref = status.provider_ref
    intent.customer_url = status.customer_url
    if status.status != "PENDING":
        intent.status = status.status
        intent.failure_reason = status.failure_reason
    db.commit()


def create_card(db: Session, settings: Settings, data: CardIntentCreate, principal) -> IntentOut:
    store_id = _store_id(db, principal.store_id, data.store_id)
    terminals = active_terminals(db, store_id)
    device_id = principal.device.id if principal.device is not None else None
    if data.terminal_id is not None:
        terminal = next((row for row in terminals if row.id == data.terminal_id), None)
    else:
        terminal = next((row for row in terminals if device_id and row.device_id == device_id), None) or (
            terminals[0] if terminals else None
        )
    if terminal is None:
        raise ApiError(422, "no_terminal", "No active card terminal is set up for this store.")
    intent = _new_intent(
        db,
        store_id=store_id,
        channel="CARD",
        provider=terminal.provider,
        amount_cents=data.amount_cents,
        minutes=settings.payment_intent_minutes,
    )
    intent.terminal_id = terminal.id
    return_url, webhook_url = _urls(settings, intent)
    adapter = _adapter(settings, intent)
    request = StartRequest(
        intent_id=str(intent.id),
        reference=intent.reference,
        amount_cents=intent.amount_cents,
        currency=intent.currency,
        terminal_ref=terminal.terminal_ref,
        return_url=return_url,
        webhook_url=webhook_url,
    )
    try:
        status = adapter.start(request)
    except ProviderError as exc:
        intent.status = "DECLINED"
        intent.failure_reason = str(exc)[:200]
        db.commit()
        return IntentOut(**intent_fields(intent))
    _started(db, intent, status)
    return IntentOut(**intent_fields(intent))


def create_bnpl(db: Session, settings: Settings, data: BnplIntentCreate, principal) -> IntentOut:
    store_id = _store_id(db, principal.store_id, data.store_id)
    if data.provider not in registry.bnpl_names(settings):
        raise ApiError(422, "provider_unavailable", "That pay-later provider is not offered here.")
    intent = _new_intent(
        db,
        store_id=store_id,
        channel="BNPL",
        provider=data.provider,
        amount_cents=data.amount_cents,
        minutes=BNPL_MINUTES,
    )
    intent.customer_phone = data.customer_phone.replace(" ", "")
    return_url, webhook_url = _urls(settings, intent)
    request = StartRequest(
        intent_id=str(intent.id),
        reference=intent.reference,
        amount_cents=intent.amount_cents,
        currency=intent.currency,
        customer_phone=intent.customer_phone,
        customer_name=data.customer_name.strip(),
        customer_email=data.customer_email.strip(),
        items=tuple(LineItem(item.name, item.quantity, item.unit_cents, item.sku) for item in data.items),
        return_url=return_url,
        webhook_url=webhook_url,
    )
    try:
        status = _adapter(settings, intent).start(request)
    except ProviderError as exc:
        intent.status = "DECLINED"
        intent.failure_reason = str(exc)[:200]
        db.commit()
        return IntentOut(**intent_fields(intent))
    _started(db, intent, status)
    return IntentOut(**intent_fields(intent))


# --- State transitions ---------------------------------------------------------------------------------------


def _ref(intent: PaymentIntent, db: Session) -> PaymentRef:
    terminal = db.get(PaymentTerminal, intent.terminal_id) if intent.terminal_id is not None else None
    return PaymentRef(
        provider_ref=intent.provider_ref,
        reference=intent.reference,
        amount_cents=intent.amount_cents,
        currency=intent.currency,
        terminal_ref=terminal.terminal_ref if terminal is not None else None,
    )


def _transition(db: Session, intent: PaymentIntent, values: dict, *, from_states=OPEN) -> bool:
    changed = db.execute(
        update(PaymentIntent)
        .where(PaymentIntent.id == intent.id, PaymentIntent.status.in_(from_states))
        .values(**values)
    ).rowcount
    db.commit()
    db.refresh(intent)
    return bool(changed)


def apply(db: Session, settings: Settings, intent: PaymentIntent, status: ProviderStatus) -> None:
    """Move an open intent to what the provider reports. PENDING reports change nothing."""
    if intent.status not in OPEN or status.status == "PENDING":
        return
    if status.amount_cents is not None and status.status in ("AUTHORIZED", "PAID"):
        if status.amount_cents != intent.amount_cents:
            _transition(
                db, intent, {"status": "DECLINED", "failure_reason": "The provider approved a different amount."}
            )
            return
    details = {
        key: value
        for key, value in {
            "auth_code": status.auth_code,
            "card_brand": status.card_brand,
            "card_last4": status.card_last4,
        }.items()
        if value
    }
    if status.status == "AUTHORIZED" and intent.channel == "BNPL":
        if intent.status == "PENDING":
            _transition(db, intent, {"status": "AUTHORIZED", **details}, from_states=("PENDING",))
        try:
            captured = _adapter(settings, intent).capture(_ref(intent, db))
        except ProviderError as exc:
            intent.failure_reason = f"Approved, capture pending: {exc}"[:200]
            db.commit()
            return
        details |= {"auth_code": captured.auth_code} if captured.auth_code else {}
        _transition(db, intent, {"status": "PAID", "paid_at": datetime.now(UTC), "failure_reason": None, **details})
        return
    if status.status in ("PAID", "AUTHORIZED"):
        _transition(db, intent, {"status": "PAID", "paid_at": datetime.now(UTC), "failure_reason": None, **details})
        return
    _transition(db, intent, {"status": status.status, "failure_reason": (status.failure_reason or "")[:200] or None})


def refresh(db: Session, settings: Settings, intent: PaymentIntent) -> None:
    """Called when the till polls. Expires stale intents; asks real providers for news."""
    if intent.status not in OPEN:
        return
    expires = intent.expires_at if intent.expires_at.tzinfo else intent.expires_at.replace(tzinfo=UTC)
    adapter = _adapter(settings, intent)
    if intent.status == "PENDING" and expires < datetime.now(UTC):
        if not adapter.simulated:
            try:
                adapter.cancel(_ref(intent, db))
            except ProviderError:
                log.warning("Could not cancel expired %s payment %s", intent.provider, intent.id)
        _transition(db, intent, {"status": "EXPIRED"}, from_states=("PENDING",))
        return
    if intent.status == "AUTHORIZED":
        apply(db, settings, intent, ProviderStatus(status="AUTHORIZED"))
        return
    if adapter.simulated or not intent.provider_ref:
        return
    try:
        status = adapter.fetch(_ref(intent, db))
    except ProviderError as exc:
        log.warning("Polling %s payment %s failed: %s", intent.provider, intent.id, exc)
        return
    apply(db, settings, intent, status)


def cancel(db: Session, settings: Settings, intent: PaymentIntent) -> None:
    if intent.status not in OPEN:
        return
    try:
        _adapter(settings, intent).cancel(_ref(intent, db))
    except ProviderError as exc:
        raise ApiError(502, "provider_error", f"The provider did not cancel the payment: {exc}") from exc
    _transition(db, intent, {"status": "CANCELLED"})


def _find(db: Session, intent_id: uuid.UUID, store_scope: uuid.UUID | None) -> PaymentIntent:
    intent = db.get(PaymentIntent, intent_id)
    if intent is None or (store_scope is not None and intent.store_id != store_scope) or intent.channel == "QR":
        raise ApiError(404, "not_found", "Payment was not found.")
    return intent


def simulate(
    db: Session, settings: Settings, intent_id: uuid.UUID, outcome: str, store_scope: uuid.UUID | None
) -> IntentOut:
    intent = _find(db, intent_id, store_scope)
    if not _adapter(settings, intent).simulated or not simulator_controls(db, settings):
        raise ApiError(404, "not_found", "Only simulated payments can be approved by hand.")
    if outcome == "approve":
        apply(db, settings, intent, SimulatorAdapter.approval(intent.channel))  # type: ignore[arg-type]
    else:
        reason = "Declined by the card issuer (simulated)." if intent.channel == "CARD" else "Not approved (simulated)."
        apply(db, settings, intent, ProviderStatus(status="DECLINED", failure_reason=reason))
    return IntentOut(**intent_fields(intent))


def handle_webhook(
    db: Session, settings: Settings, provider: str, body: bytes, headers: dict[str, str], query: dict[str, str]
) -> IntentOut:
    if provider not in (*registry.CARD_PROVIDERS, *registry.BNPL_PROVIDERS):
        raise ApiError(404, "not_found", "Unknown payment provider.")
    channel = "CARD" if provider in ("ngenius", "geidea") else "BNPL"
    adapter = registry.adapter(settings, provider, channel)  # type: ignore[arg-type]
    if not adapter.verify_webhook(body, headers, query):
        raise ApiError(401, "bad_signature", "Webhook signature does not match.")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise ApiError(422, "invalid_request", "Webhook body is not JSON.") from exc
    event = adapter.parse_webhook(payload if isinstance(payload, dict) else {})
    intent = None
    if event.provider_ref:
        intent = db.scalar(
            select(PaymentIntent).where(PaymentIntent.provider_ref == event.provider_ref, PaymentIntent.channel != "QR")
        )
    if intent is None and event.reference:
        intent = db.scalar(
            select(PaymentIntent).where(PaymentIntent.reference == event.reference, PaymentIntent.channel != "QR")
        )
    if intent is None:
        raise ApiError(404, "not_found", "No payment matches this notification.")
    status = event.status
    if not adapter.simulated and intent.provider_ref:
        # Notifications only say "look again"; the provider's own record decides.
        try:
            status = _adapter(settings, intent).fetch(_ref(intent, db))
        except ProviderError:
            status = event.status
    apply(db, settings, intent, status)
    return IntentOut(**intent_fields(intent))


# --- Refunds -------------------------------------------------------------------------------------------------


def queue_refunds(
    db: Session, *, sale_id: uuid.UUID, return_id: uuid.UUID, method: str, amount_cents: int
) -> list[PaymentRefund]:
    """Inside the return's transaction: book what each provider payment on the sale must give back. The job
    (and the portal's Retry) sends them once the return is committed."""
    channel = CHANNEL_OF_REFUND.get(method)
    if channel is None or amount_cents <= 0:
        return []
    intents = list(
        db.scalars(
            select(PaymentIntent)
            .where(PaymentIntent.sale_id == sale_id, PaymentIntent.channel == channel, PaymentIntent.status == "PAID")
            .order_by(PaymentIntent.paid_at, PaymentIntent.created_at)
        )
    )
    booked = {
        intent_id: int(total)
        for intent_id, total in db.execute(
            select(PaymentRefund.intent_id, func.sum(PaymentRefund.amount_cents))
            .where(PaymentRefund.intent_id.in_([intent.id for intent in intents] or [uuid.uuid4()]))
            .group_by(PaymentRefund.intent_id)
        )
    }
    left = amount_cents
    rows: list[PaymentRefund] = []
    for intent in intents:
        room = intent.amount_cents - booked.get(intent.id, 0)
        take = min(room, left)
        if take <= 0:
            continue
        row = PaymentRefund(intent_id=intent.id, return_id=return_id, amount_cents=take, status="PENDING", attempts=0)
        db.add(row)
        rows.append(row)
        left -= take
        if left == 0:
            break
    if channel == "BNPL" and left > 0:
        raise SyncRejected("The pay-later refund exceeds what is left on the provider payment.")
    return rows


def send_refund(db: Session, settings: Settings, refund: PaymentRefund) -> PaymentRefund:
    if refund.status == "SUCCEEDED":
        return refund
    intent = db.get(PaymentIntent, refund.intent_id)
    assert intent is not None
    claimed = db.execute(
        update(PaymentRefund)
        .where(PaymentRefund.id == refund.id, PaymentRefund.attempts == refund.attempts)
        .values(attempts=refund.attempts + 1, status="PENDING")
    ).rowcount
    db.commit()
    db.refresh(refund)
    if not claimed:
        return refund
    error = ""
    try:
        result = _adapter(settings, intent).refund(_ref(intent, db), refund.amount_cents, "Customer return")
    except ProviderError as exc:
        result = None
        error = str(exc)
    if result is not None and result.ok:
        refund.status = "SUCCEEDED"
        refund.provider_ref = result.provider_ref
        refund.error = None
        db.execute(
            update(PaymentIntent)
            .where(PaymentIntent.id == intent.id)
            .values(refunded_cents=PaymentIntent.refunded_cents + refund.amount_cents)
        )
    else:
        refund.status = "FAILED"
        refund.error = ((result.error if result is not None else error) or "Refund failed.")[:300]
    db.commit()
    db.refresh(refund)
    return refund


def process_refunds(db: Session, settings: Settings) -> str:
    """Job: send new refunds, and retry failed ones with backoff (1, 2, 4... minutes) up to six attempts."""
    now = datetime.now(UTC)
    rows = db.scalars(
        select(PaymentRefund)
        .where(PaymentRefund.status.in_(("PENDING", "FAILED")), PaymentRefund.attempts < REFUND_MAX_ATTEMPTS)
        .order_by(PaymentRefund.created_at)
        .limit(100)
    ).all()
    sent = failed = 0
    for row in rows:
        updated = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=UTC)
        if row.status == "FAILED" and updated > now - timedelta(minutes=2 ** max(0, row.attempts - 1)):
            continue
        result = send_refund(db, settings, row)
        sent += result.status == "SUCCEEDED"
        failed += result.status == "FAILED"
    return f"{sent} refunds sent, {failed} failed"


def retry_refund(db: Session, settings: Settings, refund_id: uuid.UUID, user) -> RefundOut:
    refund = db.get(PaymentRefund, refund_id)
    if refund is None:
        raise ApiError(404, "not_found", "Refund was not found.")
    if refund.status == "SUCCEEDED":
        raise ApiError(409, "already_refunded", "This refund already went through.")
    result = send_refund(db, settings, refund)
    audit.record(
        db,
        action_type="UPDATE",
        action="payment.refund_retry",
        target_entity="PaymentRefund",
        target_entity_id=refund.id,
        user=user,
        details={"status": result.status, "amount_cents": result.amount_cents},
    )
    db.commit()
    return _refund_out(db, result)


def _refund_out(db: Session, row: PaymentRefund, intent: PaymentIntent | None = None) -> RefundOut:
    intent = intent or db.get(PaymentIntent, row.intent_id)
    assert intent is not None
    return RefundOut(
        id=row.id,
        intent_id=row.intent_id,
        return_id=row.return_id,
        provider=intent.provider,
        channel=intent.channel,
        amount_cents=row.amount_cents,
        status=row.status,  # type: ignore[arg-type]
        provider_ref=row.provider_ref,
        error=row.error,
        attempts=row.attempts,
        created_at=row.created_at,
    )


def list_refunds(db: Session, *, status: str | None, store_scope: uuid.UUID | None) -> list[RefundOut]:
    statement = (
        select(PaymentRefund, PaymentIntent)
        .join(PaymentIntent, PaymentIntent.id == PaymentRefund.intent_id)
        .order_by(PaymentRefund.created_at.desc())
        .limit(200)
    )
    if status:
        statement = statement.where(PaymentRefund.status == status)
    if store_scope is not None:
        statement = statement.where(PaymentIntent.store_id == store_scope)
    return [_refund_out(db, refund, intent) for refund, intent in db.execute(statement)]


# --- Portal lists and terminals ------------------------------------------------------------------------------


def list_payments(
    db: Session,
    *,
    channel: str | None,
    status: str | None,
    store_id: uuid.UUID | None,
    store_scope: uuid.UUID | None,
    limit: int,
    offset: int,
) -> PaymentList:
    filters = []
    if channel:
        filters.append(PaymentIntent.channel == channel)
    if status:
        filters.append(PaymentIntent.status == status)
    scope = store_scope or store_id
    if scope is not None:
        filters.append(PaymentIntent.store_id == scope)
    total, paid, refunded = db.execute(
        select(
            func.count(PaymentIntent.id),
            func.coalesce(func.sum(PaymentIntent.amount_cents).filter(PaymentIntent.status == "PAID"), 0),
            func.coalesce(func.sum(PaymentIntent.refunded_cents), 0),
        ).where(*filters)
    ).one()
    rows = db.execute(
        select(PaymentIntent, Store.name, Sale.invoice_number)
        .join(Store, Store.id == PaymentIntent.store_id)
        .outerjoin(Sale, Sale.id == PaymentIntent.sale_id)
        .where(*filters)
        .order_by(PaymentIntent.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaymentList(
        items=[
            PaymentRow(
                **intent_fields(intent),
                store_id=intent.store_id,
                store_name=store_name,
                created_at=intent.created_at,
                sale_number=number,
            )
            for intent, store_name, number in rows
        ],
        total=int(total),
        paid_cents=int(paid),
        refunded_cents=int(refunded),
    )


def list_terminals(db: Session, store_scope: uuid.UUID | None) -> list[TerminalOut]:
    statement = select(PaymentTerminal).order_by(PaymentTerminal.created_at)
    if store_scope is not None:
        statement = statement.where(PaymentTerminal.store_id == store_scope)
    return [_terminal_out(row) for row in db.scalars(statement)]


def create_terminal(db: Session, data: TerminalIn, store_scope: uuid.UUID | None, user) -> TerminalOut:
    if store_scope is not None and data.store_id != store_scope:
        raise ApiError(403, "forbidden", "You can only add terminals to your own store.")
    if db.get(Store, data.store_id) is None:
        raise ApiError(422, "validation_error", "Choose the store for this terminal.")
    if db.scalar(
        select(PaymentTerminal.id).where(
            PaymentTerminal.provider == data.provider, PaymentTerminal.terminal_ref == data.terminal_ref
        )
    ):
        raise ApiError(409, "duplicate_terminal", "That terminal is already registered.")
    row = PaymentTerminal(
        store_id=data.store_id,
        provider=data.provider,
        terminal_ref=data.terminal_ref,
        label=data.label.strip(),
        device_id=data.device_id,
        is_active=data.is_active,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="payment.terminal_added",
        target_entity="PaymentTerminal",
        target_entity_id=row.id,
        user=user,
        store_id=row.store_id,
        details={"provider": row.provider, "terminal_ref": row.terminal_ref},
    )
    db.commit()
    return _terminal_out(row)


def update_terminal(
    db: Session, terminal_id: uuid.UUID, data: TerminalPatch, store_scope: uuid.UUID | None
) -> TerminalOut:
    row = db.get(PaymentTerminal, terminal_id)
    if row is None or (store_scope is not None and row.store_id != store_scope):
        raise ApiError(404, "not_found", "Terminal was not found.")
    if data.label is not None:
        row.label = data.label.strip()
    if data.clear_device:
        row.device_id = None
    elif data.device_id is not None:
        row.device_id = data.device_id
    if data.is_active is not None:
        row.is_active = data.is_active
    db.commit()
    return _terminal_out(row)


def check_terminal(
    db: Session, settings: Settings, terminal_id: uuid.UUID, store_scope: uuid.UUID | None
) -> TerminalCheck:
    row = db.get(PaymentTerminal, terminal_id)
    if row is None or (store_scope is not None and row.store_id != store_scope):
        raise ApiError(404, "not_found", "Terminal was not found.")
    adapter = registry.adapter(settings, row.provider, "CARD")
    try:
        message = adapter.check(row.terminal_ref)
        ok = True
    except ProviderError as exc:
        message, ok = str(exc), False
    if adapter.simulated and row.provider != "simulator":
        message = f"{message} (simulated: {registry.LABELS[row.provider]} credentials are not set)"
    row.last_checked_at = datetime.now(UTC)
    row.last_check_ok = ok
    db.commit()
    return TerminalCheck(ok=ok, message=message)
