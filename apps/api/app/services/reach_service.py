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
from app.models.reach import MessagingChannel, ReachCampaign, ReachUsage
from app.models.sale import Sale
from app.services.messaging_providers import CHANNEL_PROVIDERS
from app.services.messaging_service import PLACEHOLDER, marketing_consented
from app.services.settings_service import load_settings

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


def campaign_channel_ready(db: Session, channel: str) -> bool:
    """Campaigns need a channel the tenant turned on and tested. Log delivery is ready when enabled."""
    row = db.scalar(select(MessagingChannel).where(MessagingChannel.channel == channel))
    if row is None or not row.enabled:
        return False
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
    if not row.secret_encrypted and row.provider != "log":
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
        if row.provider != "log" and not row.secret_encrypted:
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
    if row.provider != "log" and not row.secret_encrypted:
        missing.append("credential")
    if missing:
        row.status = "not_configured"
        row.last_error = f"Add {', '.join(missing)} first."
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
        return customers[:AUDIENCE_CAP]
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
        if len(chosen) >= AUDIENCE_CAP:
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
    eligible = suppressed = estimated = 0
    for customer in people:
        for channel in channels:
            address = customer.email if channel == "email" else customer.phone
            if marketing_consented(customer, channel) and address and open_channels[channel]:
                eligible += 1
                estimated += prices[channel]
            else:
                suppressed += 1
    return {
        "recipients": len(people),
        "eligible": eligible,
        "suppressed": suppressed,
        "estimated_cents": estimated,
        "unknown_variables": unknown,
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
        raise ApiError(422, "channel_disabled", f"Turn on {', '.join(closed)} before this campaign can use them.")
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
    people = _audience(db, data.get("audience") or {}, data.get("store_id"))
    if len(people) >= AUDIENCE_CAP:
        raise ApiError(422, "audience_too_large", f"Narrow the audience to under {AUDIENCE_CAP} customers.")
    settings = load_settings(db)
    business = settings.legal_name or "AxizPOS"
    store_name = business
    campaign = ReachCampaign(
        name=data["name"].strip(),
        description=(data.get("description") or "").strip(),
        objective=data.get("objective") or "promotion",
        status="queued",
        channels=channels,
        audience=data.get("audience") or {},
        content=content,
        store_id=data.get("store_id"),
        scheduled_at=data.get("scheduled_at"),
        idempotency_key=data["idempotency_key"],
        created_by_id=actor_id,
    )
    db.add(campaign)
    db.flush()
    eligible = suppressed = 0
    when = data.get("scheduled_at") or datetime.now(UTC)
    for customer in people:
        for channel in channels:
            address = customer.email if channel == "email" else customer.phone
            piece = content.get(channel) or {}
            body = _render(piece.get("body") or "", customer, business, store_name)
            subject = _render(piece.get("subject") or campaign.name, customer, business, store_name)
            allowed = bool(address) and marketing_consented(customer, channel)
            status = "QUEUED" if allowed else "SKIPPED"
            error = None if allowed else "No marketing consent or contact address for this channel."
            if allowed:
                eligible += 1
            else:
                suppressed += 1
            db.add(
                OutboundMessage(
                    channel=channel,
                    to_address=address or "",
                    customer_id=customer.id,
                    template_key="campaign",
                    subject=subject[:200],
                    body=body,
                    status=status,
                    last_error=error,
                    dedupe_key=f"campaign:{campaign.id}:{customer.id}:{channel}",
                    context={"campaign_id": str(campaign.id), "customer_name": customer.name},
                    next_attempt_at=when,
                )
            )
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
        "by_channel": by_channel,
        "usage_cents": usage,
        "transactional_cents": transactional,
        "prices": _prices(db),
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
