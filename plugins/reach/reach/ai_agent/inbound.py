"""Persists an inbound WhatsApp message. It does not call a model or send a reply."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from reach.ai_agent.hold import note_customer_waiting, response_policy, suppress_pending
from reach.ai_agent.models import ReachAiConversation, ReachAiEvent, ReachAiMessage
from reach.models import ReachConnection

_STATUS = {"SERVER_ACK", "DELIVERY_ACK", "READ", "PLAYED", "ERROR", "FAILED"}


def capture(db: Session, connection: ReachConnection, data: dict) -> None:
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    if key.get("fromMe") is True:
        _device_message(db, connection, data)
        return
    text = _text(data).strip()
    raw_status = str(data.get("status") or "").upper()
    if raw_status in _STATUS and not text:
        return
    provider_id = str(data.get("keyId") or data.get("messageId") or key.get("id") or data.get("id") or "")[:120]
    if not provider_id:
        return
    if db.scalar(select(ReachAiMessage.id).where(ReachAiMessage.provider_message_id == provider_id)):
        return
    phone = _phone(key.get("remoteJid") or data.get("from") or "")
    if not phone:
        return
    customer = _customer(db, phone)
    name = ""
    if customer is not None:
        name = customer.company_name or customer.name
    elif data.get("pushName"):
        name = str(data.get("pushName"))[:120]
    conversation = _conversation(db, connection, phone, customer, name)
    body = text or "A media message arrived. It was not read."
    try:
        with db.begin_nested():
            db.add(
                ReachAiMessage(
                    conversation_id=conversation.id,
                    direction="in",
                    author="customer",
                    body=body[:4000],
                    provider_message_id=provider_id,
                    status="received" if text else "stored",
                )
            )
            db.flush()
    except IntegrityError:
        return
    conversation.last_preview = body[:180]
    conversation.last_message_at = utcnow()
    conversation.unread_count += 1
    if conversation.status == "resolved":
        conversation.status = "open"
        conversation.handler = "ai"
    if text:
        note_customer_waiting(db, conversation, body, response_policy(db))
    if not text:
        db.add(
            ReachAiEvent(
                conversation_id=conversation.id,
                kind="unsupported_media",
                detail="The attachment was stored without being interpreted.",
            )
        )


def _device_message(db: Session, connection: ReachConnection, data: dict) -> None:
    """A fromMe event is human only when it is not an echo of a message this server already queued."""
    text = _text(data).strip()
    raw_status = str(data.get("status") or "").upper()
    if raw_status in _STATUS and not text:
        return
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    provider_id = str(data.get("keyId") or data.get("messageId") or key.get("id") or data.get("id") or "")[:120]
    if not provider_id:
        return
    if db.scalar(select(ReachAiMessage.id).where(ReachAiMessage.provider_message_id == provider_id)):
        return
    phone = _phone(key.get("remoteJid") or data.get("from") or "")
    if not phone or not text:
        return
    if _echo_of_ours(db, phone, text, provider_id):
        return
    conversation = _conversation(db, connection, phone, _customer(db, phone), "")
    try:
        with db.begin_nested():
            db.add(
                ReachAiMessage(
                    conversation_id=conversation.id,
                    direction="out",
                    author="staff",
                    body=text[:4000],
                    provider_message_id=provider_id,
                    status="stored",
                    evidence={"origin": "human_device"},
                )
            )
            db.flush()
    except IntegrityError:
        return
    conversation.handler = "human"
    conversation.status = "waiting_customer"
    conversation.last_preview = text[:180]
    conversation.last_message_at = utcnow()
    suppress_pending(db, conversation)
    db.add(ReachAiEvent(conversation_id=conversation.id, kind="device_reply", detail=provider_id))


def _echo_of_ours(db: Session, phone: str, text: str, provider_id: str) -> bool:
    outbound = db.scalar(select(OutboundMessage).where(OutboundMessage.provider_message_id == provider_id))
    if outbound is not None:
        return True
    since = datetime.now(UTC) - timedelta(minutes=10)
    recent = db.scalars(select(OutboundMessage).where(OutboundMessage.created_at >= since)).all()
    folded = text.strip()
    for item in recent:
        digits = "".join(ch for ch in item.to_address if ch.isdigit())
        if item.body.strip() == folded and (phone == digits or phone.endswith(digits) or digits.endswith(phone)):
            return True
    return False


def _conversation(
    db: Session,
    connection: ReachConnection,
    phone: str,
    customer: Customer | None,
    name: str,
) -> ReachAiConversation:
    found = db.scalar(
        select(ReachAiConversation)
        .where(ReachAiConversation.connection_id == connection.id, ReachAiConversation.phone == phone)
        .order_by(ReachAiConversation.created_at.desc())
        .limit(1)
    )
    if found is not None:
        if name and not found.customer_name:
            found.customer_name = name
        if customer is not None and found.customer_id is None:
            found.customer_id = customer.id
        return found
    created = ReachAiConversation(
        connection_id=connection.id,
        customer_id=None if customer is None else customer.id,
        phone=phone,
        customer_name=name,
    )
    db.add(created)
    db.flush()
    return created


def _customer(db: Session, phone: str) -> Customer | None:
    rows = list(db.scalars(select(Customer).where(Customer.phone.is_not(None))))
    for customer in rows:
        digits = "".join(ch for ch in (customer.phone or "") if ch.isdigit())
        if digits and (digits.endswith(phone) or phone.endswith(digits)):
            return customer
    return None


def _text(data: dict) -> str:
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    return str(message.get("conversation") or data.get("text") or data.get("body") or "")


def _phone(raw: object) -> str:
    number = str(raw).split("@", 1)[0]
    return "".join(ch for ch in number if ch.isdigit())[:32]
