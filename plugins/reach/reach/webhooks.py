"""Evolution webhooks. The connection is found from its stored key, never from a tenant id in the body."""

from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.tenancy.context import use_tenant
from app.tenancy.registry import active_tenants, session_factory_for
from reach.models import ReachConnection, ReachRecipient, ReachWebhookEvent

_STATUS = {
    "SERVER_ACK": "sent",
    "DELIVERY_ACK": "delivered",
    "READ": "read",
    "PLAYED": "read",
    "ERROR": "failed",
    "FAILED": "failed",
}


def accept(db: Session, settings: Settings, webhook_key: str, payload: dict, api_key: str | None) -> dict:
    _authorize(settings, api_key)
    connection = db.scalar(select(ReachConnection).where(ReachConnection.webhook_key == webhook_key))
    if connection is None:
        raise ApiError(404, "not_found", "Connection not found.")
    return _apply(db, connection, payload)


def accept_across_tenants(settings: Settings, webhook_key: str, payload: dict, api_key: str | None) -> dict:
    _authorize(settings, api_key)
    for tenant in active_tenants(settings):
        with use_tenant(tenant):
            db = session_factory_for(tenant)()
            try:
                connection = db.scalar(select(ReachConnection).where(ReachConnection.webhook_key == webhook_key))
                if connection is None:
                    continue
                result = _apply(db, connection, payload)
                return result
            finally:
                db.close()
    raise ApiError(404, "not_found", "Connection not found.")


def _authorize(settings: Settings, api_key: str | None) -> None:
    expected = (settings.evolution_webhook_secret or "").strip()
    provided = (api_key or "").strip()
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        raise ApiError(401, "webhook_rejected", "Webhook authentication failed.")


def _apply(db: Session, connection: ReachConnection, payload: dict) -> dict:
    event_key = _event_key(payload)
    if db.scalar(select(ReachWebhookEvent.id).where(ReachWebhookEvent.event_key == event_key)):
        return {"ok": True, "duplicate": True}
    event_type = str(payload.get("event") or payload.get("type") or "")
    try:
        with db.begin_nested():
            db.add(
                ReachWebhookEvent(
                    connection_id=connection.id,
                    event_key=event_key,
                    event_type=event_type[:48],
                )
            )
            db.flush()
    except IntegrityError:
        return {"ok": True, "duplicate": True}
    _dispatch(db, connection, event_type.lower(), payload)
    db.commit()
    return {"ok": True, "duplicate": False}


def _dispatch(db: Session, connection: ReachConnection, event_type: str, payload: dict) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if "connection" in event_type:
        state = str(data.get("state") or data.get("status") or "").lower()
        if state in {"open", "connected"}:
            connection.status = "open"
            number = data.get("wuid") or data.get("number")
            if number:
                connection.phone_number = "".join(ch for ch in str(number) if ch.isdigit()) or connection.phone_number
            from reach.service import bind_evolution_channel

            bind_evolution_channel(db)
        elif state in {"close", "closed", "disconnected"}:
            connection.status = "close"
            from reach.models import ReachCampaign

            campaign_ids = set(
                db.scalars(select(ReachRecipient.campaign_id).where(ReachRecipient.connection_id == connection.id))
            )
            for campaign_id in campaign_ids:
                campaign = db.get(ReachCampaign, campaign_id)
                if campaign is not None and campaign.status in {"processing", "queued", "scheduled"}:
                    campaign.status = "paused"
        return
    if _unsubscribe(db, data):
        return
    message_id = _message_id(data)
    if not message_id:
        return
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.provider_message_id == message_id))
    if recipient is None:
        return
    raw_status = str(data.get("status") or data.get("state") or "").upper()
    mapped = _STATUS.get(raw_status)
    if mapped is None:
        return
    if mapped == "failed":
        recipient.status = "failed"
        recipient.failure_reason = str(data.get("error") or "Provider reported a failure.")[:500]
        return
    if recipient.status == "read" and mapped != "read":
        return
    recipient.status = mapped
    if mapped == "delivered":
        from datetime import UTC, datetime

        recipient.delivered_at = datetime.now(UTC)
    if mapped == "read":
        from datetime import UTC, datetime

        recipient.read_at = datetime.now(UTC)


def _unsubscribe(db: Session, data: dict) -> bool:
    text = _text(data).strip().lower()
    if text not in {"stop", "unsubscribe", "cancel"}:
        return False
    number = _remote_number(data)
    if not number:
        return True
    customers = list(db.scalars(select(Customer).where(Customer.phone.is_not(None))))
    for customer in customers:
        digits = "".join(ch for ch in (customer.phone or "") if ch.isdigit())
        if digits.endswith(number) or number.endswith(digits):
            customer.marketing_whatsapp_opt_in = False
            customer.marketing_sms_opt_in = False
            queued = db.scalars(
                select(OutboundMessage).where(
                    OutboundMessage.customer_id == customer.id,
                    OutboundMessage.template_key == "campaign",
                    OutboundMessage.status == "QUEUED",
                )
            )
            for message in queued:
                message.status = "SKIPPED"
                message.last_error = "Customer sent STOP."
                recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
                if recipient is not None and recipient.status in {"pending", "queued"}:
                    recipient.status = "cancelled"
                    recipient.failure_reason = message.last_error
                if (message.context or {}).get("reach_credit") == "1":
                    from reach.credits import release

                    raw = (message.context or {}).get("campaign_id")
                    campaign_id = None
                    if raw:
                        from uuid import UUID

                        try:
                            campaign_id = UUID(str(raw))
                        except ValueError:
                            campaign_id = None
                    release(db, message.id, campaign_id)
    return True


def _event_key(payload: dict) -> str:
    explicit = str(payload.get("eventId") or payload.get("id") or "")
    if explicit:
        return explicit[:120]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return digest[:40]


def _message_id(data: dict) -> str:
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    return str(data.get("keyId") or data.get("messageId") or key.get("id") or data.get("id") or "")


def _text(data: dict) -> str:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    return str(message.get("conversation") or data.get("text") or data.get("body") or "")


def _remote_number(data: dict) -> str:
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    raw = str(key.get("remoteJid") or data.get("from") or data.get("number") or "")
    return "".join(ch for ch in raw if ch.isdigit())
