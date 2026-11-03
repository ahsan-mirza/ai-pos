"""AxizReach campaigns. Delivery stays on the existing outbox; this service only prepares it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value, encrypt_value
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.models.sale import Sale
from app.services.messaging_providers import CHANNEL_PROVIDERS
from app.services.messaging_service import PLACEHOLDER, marketing_consented
from app.services.settings_service import load_settings
from reach import credits as credit_book
from reach.models import (
    MessagingChannel,
    ReachCampaign,
    ReachConnection,
    ReachCreditTransaction,
    ReachRecipient,
    ReachTemplate,
    ReachUsage,
)

CHANNELS = ("whatsapp", "sms", "email")
REQUIRED_CONFIG = {
    "whatsapp_cloud": ("phone_number_id",),
    "http_sms": ("url",),
    "smtp": ("host", "sender_email"),
}
VARIABLES = {"customer_name", "business_name", "store_name", "loyalty_points", "product_name", "discount"}
AUDIENCE_CAP = 1000
CLOSED = frozenset({"quote", "voided", "draft"})


def require_reach(db: Session) -> None:
    if not has_capability(db, Capability.AXIZ_REACH):
        raise ApiError(403, "addon_required", "AxizReach is not enabled for this business.")


def channel_enabled(db: Session, channel: str) -> bool:
    """A channel with no row stays available for existing transactional messages."""
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    return True if row is None else bool(row.enabled)


def _evolution_ready(db: Session) -> bool:
    return (
        db.scalar(select(ReachConnection.id).where(ReachConnection.status == "open").limit(1)) is not None
    )


def bind_evolution_channel(db: Session) -> None:
    """An open WhatsApp session sends as Evolution. A Cloud provider the store already saved is left as-is."""
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == "whatsapp"))
    if row is not None and row.provider not in {"log", "evolution"}:
        return
    if row is None:
        row = MessagingChannel(channel="whatsapp", public_config={})
        db.add(row)
    row.provider = "evolution"
    row.enabled = True
    row.status = "connected"
    row.last_error = None
    row.last_checked_at = datetime.now(UTC)


def _channel_provider(db: Session, channel: str) -> str:
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    return "log" if row is None else row.provider


def campaign_channel_ready(db: Session, channel: str) -> bool:
    """Campaigns need a channel the tenant turned on and tested. Log delivery is ready when enabled."""
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    if row is None or not row.enabled:
        return False
    if row.provider == "evolution":
        return _evolution_ready(db)
    return row.provider == "log" or row.status == "connected"


def _mask(secret: str | None) -> str | None:
    if not secret:
        return None
    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"••••{tail}"


def _status_for(row: MessagingChannel) -> str:
    if not row.enabled:
        return "disabled"
    if row.provider == "log":
        return "connected"
    if row.provider == "evolution":
        return row.status if row.status not in {"disabled"} else "not_configured"
    if not row.secret_encrypted:
        return "not_configured"
    return row.status if row.status not in {"disabled", "not_configured"} else "connected"


def list_channels(db: Session, settings: Settings) -> list[dict]:
    rows = {row.channel: row for row in db.scalars(select(MessagingChannel))}
    out = []
    for channel in CHANNELS:
        row = rows.get(channel)
        secret = None
        if row is not None and row.secret_encrypted:
            try:
                secret = decrypt_value(row.secret_encrypted, settings)
            except Exception:
                secret = None
        out.append(
            {
                "channel": channel,
                "enabled": False if row is None else row.enabled,
                "provider": "log" if row is None else row.provider,
                "providers": list(CHANNEL_PROVIDERS[channel]),
                "public_config": {} if row is None else dict(row.public_config or {}),
                "secret_set": secret is not None,
                "secret_hint": _mask(secret),
                "status": "not_configured" if row is None else _status_for(row),
                "last_error": None if row is None else row.last_error,
                "last_checked_at": None if row is None else row.last_checked_at,
            }
        )
    return out


def save_channel(db: Session, settings: Settings, data: dict) -> dict:
    channel = data["channel"]
    if channel not in CHANNELS or data["provider"] not in CHANNEL_PROVIDERS[channel]:
        raise ApiError(422, "invalid_request", "Choose a provider this channel supports.")
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    if row is None:
        row = MessagingChannel(channel=channel, public_config={})
        db.add(row)
    row.enabled = data["enabled"]
    row.provider = data["provider"]
    row.public_config = {
        key: value for key, value in (data.get("public_config") or {}).items() if value not in (None, "")
    }
    secret = (data.get("secret") or "").strip()
    if secret:
        row.secret_encrypted = encrypt_value(secret, settings)
    if row.enabled:
        missing = [key for key in REQUIRED_CONFIG.get(row.provider, ()) if not (row.public_config or {}).get(key)]
        if row.provider not in {"log", "evolution"} and not row.secret_encrypted:
            missing.append("credential")
        if missing:
            db.rollback()
            raise ApiError(422, "not_configured", f"Add {', '.join(missing)} before turning {channel} on.")
    if not row.enabled:
        row.status = "disabled"
    elif row.provider == "log":
        row.status = "connected"
    elif row.status != "connected":
        row.status = "not_configured"
    row.last_error = None
    db.commit()
    return list_channels(db, settings)[CHANNELS.index(channel)]


def test_channel(db: Session, settings: Settings, channel: str) -> dict:
    """Confirms the saved tenant settings. An SMTP check is not proof of inbox delivery."""
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    if row is None or not row.enabled:
        raise ApiError(422, "channel_disabled", "Turn the channel on before testing it.")
    missing = [key for key in REQUIRED_CONFIG.get(row.provider, ()) if not (row.public_config or {}).get(key)]
    if row.provider not in {"log", "evolution"} and not row.secret_encrypted:
        missing.append("credential")
    if missing:
        row.status = "not_configured"
        row.last_error = f"Add {', '.join(missing)} first."
        row.last_checked_at = datetime.now(UTC)
        db.commit()
        raise ApiError(422, "not_configured", row.last_error)
    if row.provider == "evolution" and not _evolution_ready(db):
        row.status = "not_configured"
        row.last_error = "Connect a WhatsApp number before this channel can send."
        row.last_checked_at = datetime.now(UTC)
        db.commit()
        raise ApiError(422, "not_configured", row.last_error)
    row.status = "connected"
    row.last_error = None
    row.last_checked_at = datetime.now(UTC)
    db.commit()
    return list_channels(db, settings)[CHANNELS.index(channel)]


def _prices(db: Session) -> dict[str, int]:
    raw = (load_settings(db).messaging or {}).get("prices") or {}
    return {channel: int(raw.get(channel) or 0) for channel in CHANNELS}


def save_prices(db: Session, prices: dict[str, int]) -> dict[str, int]:
    row = load_settings(db)
    current = dict(row.messaging or {})
    current["prices"] = {channel: int(prices.get(channel) or 0) for channel in CHANNELS}
    row.messaging = current
    db.commit()
    return _prices(db)


def _unknown_variables(*texts: str) -> list[str]:
    found = {match.group(1) for text in texts for match in PLACEHOLDER.finditer(text or "")}
    return sorted(found - VARIABLES)


def _audience(db: Session, audience: dict, store_id: uuid.UUID | None) -> list[Customer]:
    query = select(Customer).where(Customer.is_active.is_(True))
    chosen_ids = audience.get("customer_ids")
    if chosen_ids:
        query = query.where(Customer.id.in_(chosen_ids))
    minimum = int(audience.get("min_loyalty_points") or 0)
    if minimum:
        query = query.where(Customer.loyalty_points >= minimum)
    kind = audience.get("customer_type")
    if kind in {"RETAIL", "WHOLESALE"}:
        query = query.where(Customer.customer_type == kind)
    customers = list(db.scalars(query.order_by(Customer.created_at).limit(AUDIENCE_CAP + 1)))
    inactive_days = int(audience.get("inactive_days") or 0)
    min_spend = int(audience.get("min_spend_cents") or 0)
    if not inactive_days and not min_spend and store_id is None:
        return customers
    ids = [customer.id for customer in customers]
    if not ids:
        return []
    filters = [Sale.customer_id.in_(ids), Sale.status.not_in(CLOSED)]
    if store_id is not None:
        filters.append(Sale.store_id == store_id)
    stats = {
        customer_id: (last, int(spent or 0))
        for customer_id, last, spent in db.execute(
            select(Sale.customer_id, func.max(Sale.created_at), func.coalesce(func.sum(Sale.total_cents), 0))
            .where(*filters)
            .group_by(Sale.customer_id)
        )
    }
    cutoff = datetime.now(UTC) - timedelta(days=inactive_days) if inactive_days else None
    chosen = []
    for customer in customers:
        last, spent = stats.get(customer.id, (None, 0))
        if store_id is not None and last is None:
            continue
        if min_spend and spent < min_spend:
            continue
        if cutoff is not None and last is not None and last >= cutoff:
            continue
        chosen.append(customer)
        if len(chosen) > AUDIENCE_CAP:
            break
    return chosen


def _render(text: str, customer: Customer, business: str, store: str) -> str:
    values = {
        "customer_name": customer.company_name or customer.name,
        "business_name": business,
        "store_name": store,
        "loyalty_points": str(customer.loyalty_points),
        "product_name": "",
        "discount": "",
    }
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), ""), text)


def _json_audience(audience: dict) -> dict:
    stored = dict(audience)
    if stored.get("customer_ids"):
        stored["customer_ids"] = [str(item) for item in stored["customer_ids"]]
    return stored


def _phone_digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _gate(customer: Customer, channel: str, seen: set[str]) -> str | None:
    """Why this customer is excluded. None means the message may be queued."""
    address = customer.email if channel == "email" else customer.phone
    if not address:
        return "No contact address for this channel."
    if not marketing_consented(customer, channel):
        return "No marketing consent for this channel."
    if channel != "whatsapp":
        return None
    digits = _phone_digits(customer.phone)
    if len(digits) < 8:
        return "Phone number is not valid for WhatsApp."
    if digits in seen:
        return "Duplicate phone number in this campaign."
    seen.add(digits)
    return None


def preview(db: Session, data: dict) -> dict:
    require_reach(db)
    channels = [channel for channel in data["channels"] if channel in CHANNELS]
    unknown = _unknown_variables(
        *(
            piece
            for channel in channels
            for piece in (
                (data["content"].get(channel) or {}).get("body", ""),
                (data["content"].get(channel) or {}).get("subject", ""),
            )
        )
    )
    people = _audience(db, data.get("audience") or {}, data.get("store_id"))
    open_channels = {channel: campaign_channel_ready(db, channel) for channel in channels}
    prices = _prices(db)
    evolution = _channel_provider(db, "whatsapp") == "evolution"
    credit_state = credit_book.snapshot(db)
    eligible = suppressed = estimated = credits = 0
    seen: set[str] = set()
    sample = ""
    for customer in people:
        for channel in channels:
            reason = None if open_channels[channel] else f"Turn on {channel} before this campaign can use it."
            if reason is None:
                reason = _gate(customer, channel, seen)
            if reason is None:
                eligible += 1
                estimated += prices[channel]
                if evolution and channel == "whatsapp":
                    credits += 1
                if not sample and channel == channels[0]:
                    piece = data["content"].get(channel) or {}
                    settings = load_settings(db)
                    business = settings.legal_name or "AxizPOS"
                    sample = _render(piece.get("body") or "", customer, business, business)
            else:
                suppressed += 1
    return {
        "recipients": len(people),
        "eligible": eligible,
        "suppressed": suppressed,
        "estimated_cents": estimated,
        "estimated_credits": credits,
        "available_credits": None if credit_state is None else credit_state["available"],
        "unknown_variables": unknown,
        "sample": sample,
    }


def launch(db: Session, actor_id: uuid.UUID | None, data: dict) -> ReachCampaign:
    require_reach(db)
    existing = db.scalar(select(ReachCampaign).where(ReachCampaign.idempotency_key == data["idempotency_key"]))
    if existing is not None:
        return existing
    channels = list(dict.fromkeys(channel for channel in data["channels"] if channel in CHANNELS))
    if not channels:
        raise ApiError(422, "channel_required", "Choose at least one channel.")
    closed = [channel for channel in channels if not campaign_channel_ready(db, channel)]
    if closed:
        if "whatsapp" in closed and _channel_provider(db, "whatsapp") == "evolution":
            raise ApiError(
                422,
                "whatsapp_disconnected",
                "WhatsApp is not connected. Scan the QR and refresh until the session is open.",
            )
        raise ApiError(422, "channel_disabled", f"Turn on {', '.join(closed)} before this campaign can use them.")
    audience = data.get("audience") or {}
    if audience.get("customer_ids") is not None and not audience.get("customer_ids"):
        raise ApiError(422, "audience_required", "Select at least one customer.")
    content = data["content"]
    texts = []
    for channel in channels:
        piece = content.get(channel) or {}
        body = (piece.get("body") or "").strip()
        if len(body) < 2:
            raise ApiError(422, "message_required", f"Write the {channel} message.")
        texts.append(body)
        texts.append(piece.get("subject") or "")
    unknown = _unknown_variables(*texts)
    if unknown:
        raise ApiError(422, "invalid_variable", f"Unknown variable: {', '.join(unknown)}.")
    people = _audience(db, audience, data.get("store_id"))
    if len(people) > AUDIENCE_CAP:
        raise ApiError(
            422,
            "audience_too_large",
            f"This audience has more than {AUDIENCE_CAP} customers. Remove some or narrow the filters.",
        )
    settings = load_settings(db)
    business = settings.legal_name or "AxizPOS"
    store_name = business
    campaign = ReachCampaign(
        name=data["name"].strip(),
        description=(data.get("description") or "").strip(),
        objective=data.get("objective") or "promotion",
        status="queued",
        channels=channels,
        audience=_json_audience(audience),
        content=content,
        store_id=data.get("store_id"),
        scheduled_at=data.get("scheduled_at"),
        idempotency_key=data["idempotency_key"],
        created_by_id=actor_id,
    )
    db.add(campaign)
    db.flush()
    evolution = _channel_provider(db, "whatsapp") == "evolution"
    connection_id = None
    if evolution:
        connection_id = db.scalar(select(ReachConnection.id).where(ReachConnection.status == "open").limit(1))
    eligible = suppressed = credit_units = 0
    seen: set[str] = set()
    when = data.get("scheduled_at") or datetime.now(UTC)
    for customer in people:
        for channel in channels:
            address = customer.email if channel == "email" else customer.phone
            piece = content.get(channel) or {}
            body = _render(piece.get("body") or "", customer, business, store_name)
            subject = _render(piece.get("subject") or campaign.name, customer, business, store_name)
            error = _gate(customer, channel, seen)
            allowed = error is None
            status = "QUEUED" if allowed else "SKIPPED"
            charged = allowed and evolution and channel == "whatsapp"
            if allowed:
                eligible += 1
            else:
                suppressed += 1
            if charged:
                credit_units += 1
            context = {"campaign_id": str(campaign.id), "customer_name": customer.name}
            if charged:
                context["reach_credit"] = "1"
            message = OutboundMessage(
                channel=channel,
                to_address=address or "",
                customer_id=customer.id,
                template_key="campaign",
                subject=subject[:200],
                body=body,
                status=status,
                last_error=error,
                dedupe_key=f"campaign:{campaign.id}:{customer.id}:{channel}",
                context=context,
                next_attempt_at=when,
            )
            db.add(message)
            db.flush()
            db.add(
                ReachRecipient(
                    campaign_id=campaign.id,
                    customer_id=customer.id,
                    outbound_message_id=message.id,
                    connection_id=connection_id if channel == "whatsapp" else None,
                    phone=(_phone_digits(address) or address or "") if channel == "whatsapp" else (address or ""),
                    body=body,
                    status="queued" if allowed else "cancelled",
                    failure_reason=error,
                )
            )
    if credit_units:
        try:
            credit_book.reserve(db, campaign.id, credit_units)
        except ApiError:
            db.rollback()
            raise
    campaign.eligible_count = len(people)
    campaign.suppressed_count = suppressed
    campaign.queued_count = eligible
    later = data.get("scheduled_at") is not None and data["scheduled_at"] > datetime.now(UTC)
    if eligible == 0:
        campaign.status = "completed"
    elif later:
        campaign.status = "scheduled"
    else:
        campaign.status = "processing"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        again = db.scalar(select(ReachCampaign).where(ReachCampaign.idempotency_key == data["idempotency_key"]))
        if again is not None:
            return again
        raise
    db.refresh(campaign)
    return campaign


def cancel(db: Session, campaign_id: uuid.UUID) -> ReachCampaign:
    require_reach(db)
    campaign = db.get(ReachCampaign, campaign_id)
    if campaign is None:
        raise ApiError(404, "not_found", "Campaign not found.")
    if campaign.status == "cancelled":
        return campaign
    campaign.status = "cancelled"
    queued = db.scalars(
        select(OutboundMessage).where(
            OutboundMessage.template_key == "campaign",
            OutboundMessage.status == "QUEUED",
            OutboundMessage.dedupe_key.like(f"campaign:{campaign.id}:%"),
        )
    )
    for message in queued:
        message.status = "SKIPPED"
        message.last_error = "Campaign cancelled before send."
        _release_message(db, message)
        recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
        if recipient is not None and recipient.status in {"pending", "queued"}:
            recipient.status = "cancelled"
            recipient.failure_reason = message.last_error
    db.commit()
    db.refresh(campaign)
    return campaign


def overview(db: Session) -> dict:
    require_reach(db)
    total_campaigns = int(db.scalar(select(func.count()).select_from(ReachCampaign)) or 0)
    active = int(
        db.scalar(
            select(func.count())
            .select_from(ReachCampaign)
            .where(ReachCampaign.status.in_(("queued", "processing", "scheduled")))
        )
        or 0
    )
    campaigns = list(db.scalars(select(ReachCampaign).order_by(ReachCampaign.created_at.desc()).limit(8)))
    sent = int(
        db.scalar(
            select(func.count()).select_from(OutboundMessage).where(
                OutboundMessage.template_key == "campaign", OutboundMessage.status == "SENT"
            )
        )
        or 0
    )
    failed = int(
        db.scalar(
            select(func.count()).select_from(OutboundMessage).where(
                OutboundMessage.template_key == "campaign", OutboundMessage.status == "FAILED"
            )
        )
        or 0
    )
    delivered = int(
        db.scalar(
            select(func.count()).select_from(ReachRecipient).where(ReachRecipient.status.in_(("delivered", "read")))
        )
        or 0
    )
    read = int(
        db.scalar(select(func.count()).select_from(ReachRecipient).where(ReachRecipient.status == "read")) or 0
    )
    credit_state = credit_book.snapshot(db)
    open_connection = db.scalar(select(ReachConnection.status).where(ReachConnection.status == "open").limit(1))
    delivered_base = sent + failed
    by_channel = {channel: 0 for channel in CHANNELS}
    for channel, count in db.execute(
        select(OutboundMessage.channel, func.count())
        .where(OutboundMessage.template_key == "campaign", OutboundMessage.status == "SENT")
        .group_by(OutboundMessage.channel)
    ):
        if channel in by_channel:
            by_channel[channel] = int(count)
    usage = int(
        db.scalar(
            select(func.coalesce(func.sum(ReachUsage.cost_cents), 0)).where(ReachUsage.purpose == "marketing")
        )
        or 0
    )
    transactional = int(
        db.scalar(
            select(func.coalesce(func.sum(ReachUsage.cost_cents), 0)).where(ReachUsage.purpose == "transactional")
        )
        or 0
    )
    recent = campaigns
    failures = list(
        db.scalars(
            select(OutboundMessage)
            .where(OutboundMessage.template_key == "campaign", OutboundMessage.status == "FAILED")
            .order_by(OutboundMessage.created_at.desc())
            .limit(8)
        )
    )
    return {
        "campaigns": total_campaigns,
        "active": active,
        "sent": sent,
        "failed": failed,
        "delivery_rate": round(sent / delivered_base, 4) if delivered_base else None,
        "delivered": delivered,
        "read": read,
        "by_channel": by_channel,
        "usage_cents": usage,
        "transactional_cents": transactional,
        "prices": _prices(db),
        "credits_available": None if credit_state is None else credit_state["available"],
        "credits_reserved": None if credit_state is None else credit_state["reserved"],
        "connection_status": open_connection or "not_connected",
        "recent": recent,
        "failures": failures,
    }


def record_usage(db: Session, message: OutboundMessage) -> None:
    """Post one usage row per sent message. Skipped recipients never arrive here, and the unique key blocks a retry."""
    if message.status != "SENT":
        return
    purpose = "marketing" if message.template_key in {"campaign", "coupon_issued"} else "transactional"
    campaign_id = None
    raw = (message.context or {}).get("campaign_id")
    if raw:
        try:
            campaign_id = uuid.UUID(str(raw))
        except ValueError:
            campaign_id = None
    prices = _prices(db)
    units = 1
    if message.channel == "sms":
        units = max(1, (len(message.body) + 159) // 160)
    try:
        with db.begin_nested():
            db.add(
                ReachUsage(
                    outbound_message_id=message.id,
                    campaign_id=campaign_id,
                    channel=message.channel,
                    purpose=purpose,
                    units=units,
                    cost_cents=units * prices.get(message.channel, 0),
                )
            )
    except IntegrityError:
        return
    if campaign_id is None:
        return
    pending = db.scalar(
        select(func.count())
        .select_from(OutboundMessage)
        .where(
            OutboundMessage.status == "QUEUED",
            OutboundMessage.dedupe_key.like(f"campaign:{campaign_id}:%"),
        )
    )
    if not pending:
        campaign = db.get(ReachCampaign, campaign_id)
        if campaign is not None and campaign.status in {"processing", "scheduled", "queued"}:
            campaign.status = "completed"


def _campaign_id(message: OutboundMessage) -> uuid.UUID | None:
    raw = (message.context or {}).get("campaign_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _release_message(db: Session, message: OutboundMessage) -> None:
    if (message.context or {}).get("reach_credit") != "1":
        return
    credit_book.release(db, message.id, _campaign_id(message))


def hold_reason(db: Session, message: OutboundMessage) -> str | None:
    """Paused and already-finished recipients stay in the outbox until they are skipped or resumed."""
    if message.template_key != "campaign":
        return None
    campaign_id = _campaign_id(message)
    if campaign_id is None:
        return None
    campaign = db.get(ReachCampaign, campaign_id)
    if campaign is not None and campaign.status == "paused":
        return "Campaign is paused."
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    if recipient is not None and recipient.connection_id is not None:
        connection = db.get(ReachConnection, recipient.connection_id)
        if connection is None or connection.status != "open":
            if campaign is not None and campaign.status in {"processing", "scheduled", "queued"}:
                campaign.status = "paused"
            return "WhatsApp session is disconnected. Reconnect, then resume the campaign."
    if recipient is not None and recipient.status in {"cancelled", "failed", "sent", "delivered", "read"}:
        return recipient.status
    return None


def after_sent(db: Session, message: OutboundMessage) -> None:
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    if recipient is not None and recipient.status in {"pending", "queued", "sending"}:
        recipient.status = "sent"
        recipient.provider_message_id = message.provider_message_id
        recipient.submitted_at = datetime.now(UTC)
        recipient.failure_reason = None
    if (message.context or {}).get("reach_credit") == "1":
        credit_book.consume(db, message.id, _campaign_id(message))


def after_skipped(db: Session, message: OutboundMessage) -> None:
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    if recipient is not None and recipient.status not in {"delivered", "read", "sent", "failed"}:
        recipient.status = "cancelled"
        recipient.failure_reason = message.last_error
    _release_message(db, message)


def after_failed(db: Session, message: OutboundMessage) -> None:
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    if recipient is not None and recipient.status not in {"delivered", "read", "cancelled"}:
        recipient.status = "failed"
        recipient.failure_reason = message.last_error
    _release_message(db, message)


_PROGRESS_EMPTY = {
    "pending_count": 0,
    "processing_count": 0,
    "accepted_count": 0,
    "delivered_count": 0,
    "read_count": 0,
    "failed_count": 0,
    "skipped_count": 0,
    "credits_reserved": 0,
    "credits_consumed": 0,
}
_STATUS_FIELD = {
    "pending": "pending_count",
    "queued": "pending_count",
    "sending": "processing_count",
    "sent": "accepted_count",
    "delivered": "delivered_count",
    "read": "read_count",
    "failed": "failed_count",
    "cancelled": "skipped_count",
}


def _open_phone(db: Session) -> str | None:
    return db.scalar(
        select(ReachConnection.phone_number).where(ReachConnection.status == "open").limit(1)
    )


def _progress(db: Session, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    found = {campaign_id: dict(_PROGRESS_EMPTY) for campaign_id in campaign_ids}
    if not campaign_ids:
        return found
    counts = db.execute(
        select(ReachRecipient.campaign_id, ReachRecipient.status, func.count())
        .where(ReachRecipient.campaign_id.in_(campaign_ids))
        .group_by(ReachRecipient.campaign_id, ReachRecipient.status)
    )
    for campaign_id, status, count in counts:
        bucket = _STATUS_FIELD.get(status)
        if bucket and campaign_id in found:
            found[campaign_id][bucket] += int(count)
    ledger = db.execute(
        select(
            ReachCreditTransaction.campaign_id,
            ReachCreditTransaction.kind,
            func.coalesce(func.sum(ReachCreditTransaction.units), 0),
        )
        .where(ReachCreditTransaction.campaign_id.in_(campaign_ids))
        .group_by(ReachCreditTransaction.campaign_id, ReachCreditTransaction.kind)
    )
    rolled: dict[uuid.UUID, dict[str, int]] = {}
    for campaign_id, kind, units in ledger:
        if campaign_id is None:
            continue
        rolled.setdefault(campaign_id, {})[kind] = int(units)
    for campaign_id, kinds in rolled.items():
        if campaign_id not in found:
            continue
        consumed = kinds.get("consume", 0)
        released = kinds.get("release", 0)
        reserved = kinds.get("reserve", 0)
        found[campaign_id]["credits_consumed"] = consumed
        found[campaign_id]["credits_reserved"] = max(0, reserved - consumed - released)
    return found


def present_campaign(db: Session, campaign: ReachCampaign) -> dict:
    from reach.schemas import CampaignOut

    body = CampaignOut.model_validate(campaign).model_dump()
    body.update(_progress(db, [campaign.id]).get(campaign.id, dict(_PROGRESS_EMPTY)))
    body["connection_phone"] = _open_phone(db)
    return body


def present_campaigns(db: Session, campaigns: list[ReachCampaign]) -> list[dict]:
    progress = _progress(db, [campaign.id for campaign in campaigns])
    phone = _open_phone(db)
    from reach.schemas import CampaignOut

    rows = []
    for campaign in campaigns:
        body = CampaignOut.model_validate(campaign).model_dump()
        body.update(progress.get(campaign.id, dict(_PROGRESS_EMPTY)))
        body["connection_phone"] = phone
        rows.append(body)
    return rows


def retry_failed(db: Session, campaign_id: uuid.UUID) -> ReachCampaign:
    """Queues failed recipients again. Consent is checked, and one credit is held per WhatsApp retry."""
    campaign = get_campaign(db, campaign_id)
    if "whatsapp" in (campaign.channels or []) and _channel_provider(db, "whatsapp") == "evolution":
        if not _evolution_ready(db):
            raise ApiError(422, "whatsapp_disconnected", "Reconnect WhatsApp and refresh until the session is open.")
    failed = list(
        db.scalars(
            select(ReachRecipient).where(
                ReachRecipient.campaign_id == campaign.id,
                ReachRecipient.status == "failed",
            )
        )
    )
    if not failed:
        raise ApiError(422, "nothing_to_retry", "There are no failed messages to retry.")
    now = datetime.now(UTC)
    retried = 0
    for recipient in failed:
        if recipient.outbound_message_id is None:
            continue
        message = db.get(OutboundMessage, recipient.outbound_message_id)
        customer = db.get(Customer, recipient.customer_id) if recipient.customer_id else None
        if message is None or customer is None or not marketing_consented(customer, message.channel):
            continue
        if message.channel == "whatsapp" and _channel_provider(db, "whatsapp") == "evolution":
            credit_book.reserve_one(db, campaign.id, message.id)
            context = dict(message.context or {})
            context["reach_credit"] = "1"
            message.context = context
        message.status = "QUEUED"
        message.last_error = None
        message.next_attempt_at = now
        recipient.status = "queued"
        recipient.failure_reason = None
        retried += 1
    if retried == 0:
        raise ApiError(422, "nothing_to_retry", "Failed recipients are no longer eligible to receive this message.")
    if campaign.status in {"paused", "completed", "cancelled"}:
        campaign.status = "processing"
    db.commit()
    db.refresh(campaign)
    return campaign


def list_campaigns(db: Session) -> list[ReachCampaign]:
    require_reach(db)
    return list(db.scalars(select(ReachCampaign).order_by(ReachCampaign.created_at.desc()).limit(100)))


def get_campaign(db: Session, campaign_id: uuid.UUID) -> ReachCampaign:
    require_reach(db)
    campaign = db.get(ReachCampaign, campaign_id)
    if campaign is None:
        raise ApiError(404, "not_found", "Campaign not found.")
    return campaign


def pause(db: Session, campaign_id: uuid.UUID) -> ReachCampaign:
    require_reach(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status not in {"processing", "scheduled", "queued"}:
        raise ApiError(422, "invalid_status", "Only a running campaign can be paused.")
    campaign.status = "paused"
    db.commit()
    db.refresh(campaign)
    return campaign


def resume(db: Session, campaign_id: uuid.UUID) -> ReachCampaign:
    require_reach(db)
    campaign = get_campaign(db, campaign_id)
    if campaign.status != "paused":
        raise ApiError(422, "invalid_status", "Only a paused campaign can resume.")
    campaign.status = "processing"
    now = datetime.now(UTC)
    waiting = db.scalars(
        select(OutboundMessage).where(
            OutboundMessage.status == "QUEUED",
            OutboundMessage.dedupe_key.like(f"campaign:{campaign.id}:%"),
        )
    )
    for message in waiting:
        if message.next_attempt_at > now:
            message.next_attempt_at = now
    db.commit()
    db.refresh(campaign)
    return campaign


def recipients(db: Session, campaign_id: uuid.UUID | None, status: str | None, limit: int) -> list[ReachRecipient]:
    require_reach(db)
    query = select(ReachRecipient).order_by(ReachRecipient.created_at.desc())
    if campaign_id is not None:
        query = query.where(ReachRecipient.campaign_id == campaign_id)
    if status:
        query = query.where(ReachRecipient.status == status)
    return list(db.scalars(query.limit(min(limit, 200))))


def search_customers(db: Session, q: str, *, whatsapp_opt_in: bool = False, limit: int = 50) -> list[dict]:
    require_reach(db)
    query = select(Customer).where(Customer.is_active.is_(True))
    if whatsapp_opt_in:
        query = query.where(Customer.marketing_whatsapp_opt_in.is_(True))
    text = q.strip()
    if text:
        like = f"%{text}%"
        query = query.where((Customer.name.ilike(like)) | (Customer.phone.ilike(like)) | (Customer.email.ilike(like)))
    rows = list(db.scalars(query.order_by(Customer.name).limit(min(max(limit, 1), AUDIENCE_CAP))))
    return [
        {
            "id": row.id,
            "name": row.name,
            "phone": row.phone,
            "email": row.email,
            "marketing_whatsapp_opt_in": bool(row.marketing_whatsapp_opt_in),
            "marketing_sms_opt_in": bool(row.marketing_sms_opt_in),
            "marketing_email_opt_in": bool(row.marketing_email_opt_in),
        }
        for row in rows
    ]


def list_templates(db: Session) -> list[ReachTemplate]:
    require_reach(db)
    return list(db.scalars(select(ReachTemplate).order_by(ReachTemplate.name)))


def save_template(db: Session, data: dict) -> ReachTemplate:
    require_reach(db)
    unknown = _unknown_variables(data["body"])
    if unknown:
        raise ApiError(422, "invalid_variable", f"Unknown variable: {', '.join(unknown)}.")
    row = db.scalar(select(ReachTemplate).where(ReachTemplate.name == data["name"].strip()))
    if row is None:
        row = ReachTemplate(name=data["name"].strip(), body=data["body"], channel=data["channel"])
        db.add(row)
    row.body = data["body"]
    row.channel = data["channel"]
    row.media_kind = data.get("media_kind")
    db.commit()
    db.refresh(row)
    return row


def delete_template(db: Session, template_id: uuid.UUID) -> None:
    require_reach(db)
    row = db.get(ReachTemplate, template_id)
    if row is None:
        raise ApiError(404, "not_found", "Template not found.")
    db.delete(row)
    db.commit()
