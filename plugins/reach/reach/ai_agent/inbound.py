"""Persists an inbound WhatsApp message. It does not call a model or send a reply."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.customer import Customer
from reach.ai_agent.models import ReachAiConversation, ReachAiEvent, ReachAiMessage
from reach.models import ReachConnection

_STATUS = {"SERVER_ACK", "DELIVERY_ACK", "READ", "PLAYED", "ERROR", "FAILED"}


def capture(db: Session, connection: ReachConnection, data: dict) -> None:
    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    if key.get("fromMe") is True:
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
    if not text:
        db.add(
            ReachAiEvent(
                conversation_id=conversation.id,
                kind="unsupported_media",
                detail="The attachment was stored without being interpreted.",
            )
        )


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
