"""Customer messaging: render a template, check consent, queue it in the outbox, and dispatch the outbox."""

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.messaging import MessageTemplate, OutboundMessage
from app.schemas.messaging import (
    MessagingSettingsOut,
    MessagingSettingsWrite,
    OutboundOut,
    TemplateOut,
    TemplateWrite,
)
from app.services import race
from app.services.email_brand import notice_html
from app.services.message_defaults import DEFAULT_EVENTS, DEFAULT_TEMPLATES
from app.services.messaging_providers import CHANNEL_PROVIDERS, Outgoing, ProviderError, deliver
from app.services.settings_service import load_settings

logger = logging.getLogger("ai_pos.messaging")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
MAX_ATTEMPTS = 5
CHANNELS = ("whatsapp", "sms", "email")


def render(text: str, context: dict[str, object]) -> str:
    return PLACEHOLDER.sub(lambda match: str(context.get(match.group(1), "")), text)


def ensure_templates(db: Session) -> None:
    existing = set(db.scalars(select(MessageTemplate.key)))
    race.add_if_absent(
        db,
        [
            MessageTemplate(key=key, name=name, subject=subject, body=body)
            for key, (name, subject, body) in DEFAULT_TEMPLATES.items()
            if key not in existing
        ],
    )


def providers(db: Session) -> dict[str, str]:
    configured = load_settings(db).messaging or {}
    return {channel: str(configured.get(channel, "log")) for channel in CHANNELS}


def events(db: Session) -> dict[str, bool]:
    return {**DEFAULT_EVENTS, **(load_settings(db).message_events or {})}


def address_for(customer: Customer, channel: str) -> str | None:
    if channel == "email":
        return customer.email
    return customer.phone


def consented(customer: Customer, channel: str) -> bool:
    return bool(getattr(customer, f"{channel}_opt_in", False))


def preferred_channel(customer: Customer) -> str | None:
    for channel in CHANNELS:
        if consented(customer, channel) and address_for(customer, channel):
            return channel
    return None


def enqueue(
    db: Session,
    *,
    template_key: str,
    customer: Customer,
    context: dict[str, object],
    channel: str | None = None,
    dedupe_key: str | None = None,
    attachment: tuple[str, str] | None = None,
) -> OutboundMessage | None:
    """Queues a templated message to a customer. Returns None when the event is switched off or deduplicated."""
    if not events(db).get(template_key, True):
        return None
    if dedupe_key is not None and db.scalar(select(OutboundMessage.id).where(OutboundMessage.dedupe_key == dedupe_key)):
        return None
    ensure_templates(db)
    template = db.scalar(select(MessageTemplate).where(MessageTemplate.key == template_key))
    if template is None or not template.is_active:
        return None
    chosen = channel or preferred_channel(customer)
    address = address_for(customer, chosen) if chosen else None
    full = {"customer": customer.company_name or customer.name, **context}
    status = "QUEUED"
    error = None
    if chosen is None or address is None:
        status, error = "SKIPPED", "The customer has not opted in to any channel with a contact address."
    elif not consented(customer, chosen):
        status, error = "SKIPPED", f"The customer has not opted in to {chosen}."
    message = OutboundMessage(
        channel=chosen or "none",
        to_address=address or "",
        customer_id=customer.id,
        template_key=template_key,
        subject=render(template.subject, full),
        body=render(template.body, full),
        status=status,
        last_error=error,
        dedupe_key=dedupe_key,
        context={key: str(value) for key, value in full.items()},
        attachment_kind=attachment[0] if attachment else None,
        attachment_ref=attachment[1] if attachment else None,
    )
    db.add(message)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return message


def _attachment(db: Session, settings: Settings, message: OutboundMessage) -> tuple[str, bytes] | None:
    """PDFs only travel by email; WhatsApp and SMS carry the text alone."""
    if message.channel != "email" or not message.attachment_ref:
        return None
    if message.attachment_kind == "invoice":
        from app.services.invoice_pdf import render_sale_invoice

        reference = uuid.UUID(message.attachment_ref)
        return f"invoice-{message.attachment_ref[:8]}.pdf", render_sale_invoice(db, settings, reference, None)
    if message.attachment_kind == "statement":
        from app.services.dunning_service import render_statement

        return "statement.pdf", render_statement(db, uuid.UUID(message.attachment_ref))
    return None


def dispatch_due(db: Session, settings: Settings, limit: int = 50) -> dict[str, int]:
    """Sends queued messages whose time has come. Transient failures back off exponentially."""
    now = datetime.now(UTC)
    chosen = providers(db)
    due = list(
        db.scalars(
            select(OutboundMessage)
            .where(OutboundMessage.status == "QUEUED", OutboundMessage.next_attempt_at <= now)
            .order_by(OutboundMessage.next_attempt_at)
            .limit(limit)
        )
    )
    counts = {"sent": 0, "failed": 0, "retry": 0}
    for message in due:
        provider = chosen.get(message.channel, "log")
        message.provider = provider
        message.attempts += 1
        try:
            html_body = None
            if message.channel == "email" and message.body:
                html_body = notice_html(
                    heading=message.subject or "AxizPOS",
                    body=message.body,
                    support_email=settings.support_email,
                )
            outgoing = Outgoing(
                to=message.to_address,
                subject=message.subject,
                body=message.body,
                attachment=_attachment(db, settings, message),
                html=html_body,
            )
            message.provider_message_id = deliver(settings, provider, outgoing)[:120] or None
            message.status = "SENT"
            message.sent_at = datetime.now(UTC)
            message.last_error = None
            counts["sent"] += 1
        except ProviderError as exc:
            message.last_error = str(exc)[:500]
            if exc.permanent or message.attempts >= MAX_ATTEMPTS:
                message.status = "FAILED"
                counts["failed"] += 1
            else:
                message.next_attempt_at = now + timedelta(minutes=2**message.attempts)
                counts["retry"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the batch
            logger.exception("message %s failed", message.id)
            message.last_error = str(exc)[:500]
            message.next_attempt_at = now + timedelta(minutes=2**message.attempts)
            counts["retry"] += 1
    db.commit()
    return counts


# --- Portal ----------------------------------------------------------------------------------------


def settings_out(db: Session) -> MessagingSettingsOut:
    ensure_templates(db)
    db.commit()
    return MessagingSettingsOut(
        providers=providers(db),
        available={channel: list(options) for channel, options in CHANNEL_PROVIDERS.items()},
        events=events(db),
    )


def update_settings(db: Session, data: MessagingSettingsWrite) -> MessagingSettingsOut:
    row = load_settings(db)
    for channel, provider in data.providers.items():
        if channel not in CHANNEL_PROVIDERS or provider not in CHANNEL_PROVIDERS[channel]:
            raise ApiError(422, "validation_error", f"{provider} is not a {channel} provider.")
    row.messaging = {**providers(db), **data.providers}
    row.message_events = {**events(db), **{key: value for key, value in data.events.items() if key in DEFAULT_EVENTS}}
    db.commit()
    return settings_out(db)


def list_templates(db: Session) -> list[TemplateOut]:
    ensure_templates(db)
    db.commit()
    return [
        TemplateOut.model_validate(row) for row in db.scalars(select(MessageTemplate).order_by(MessageTemplate.key))
    ]


def update_template(db: Session, key: str, data: TemplateWrite) -> TemplateOut:
    ensure_templates(db)
    row = db.scalar(select(MessageTemplate).where(MessageTemplate.key == key))
    if row is None:
        raise ApiError(404, "not_found", "Template was not found.")
    unknown = (
        set(PLACEHOLDER.findall(data.body + data.subject))
        - set(PLACEHOLDER.findall(DEFAULT_TEMPLATES[key][1] + DEFAULT_TEMPLATES[key][2]))
        - {"customer", "business"}
    )
    if unknown:
        raise ApiError(422, "validation_error", f"Unknown placeholders: {', '.join(sorted(unknown))}.")
    row.subject = data.subject
    row.body = data.body
    row.is_active = data.is_active
    db.commit()
    return TemplateOut.model_validate(row)


def outbox(db: Session, *, status: str | None, limit: int) -> list[OutboundOut]:
    query = select(OutboundMessage).order_by(OutboundMessage.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(OutboundMessage.status == status)
    rows = list(db.scalars(query))
    ids = {row.customer_id for row in rows if row.customer_id}
    names = (
        {row.id: row.company_name or row.name for row in db.scalars(select(Customer).where(Customer.id.in_(ids)))}
        if ids
        else {}
    )
    return [
        OutboundOut(
            id=row.id,
            channel=row.channel,
            to_address=row.to_address,
            customer_name=names.get(row.customer_id) if row.customer_id else None,
            template_key=row.template_key,
            subject=row.subject,
            body=row.body,
            status=row.status,  # type: ignore[arg-type]
            provider=row.provider,
            attempts=row.attempts,
            last_error=row.last_error,
            created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC),
            sent_at=row.sent_at,
        )
        for row in rows
    ]


def send_test(db: Session, settings: Settings, channel: str, to: str) -> OutboundOut:
    if channel not in CHANNELS:
        raise ApiError(422, "validation_error", "Unknown channel.")
    message = OutboundMessage(
        channel=channel,
        to_address=to,
        subject="AI POS test message",
        body="This is a test message from AI POS. Messaging is set up.",
        status="QUEUED",
    )
    db.add(message)
    db.commit()
    dispatch_due(db, settings, limit=10)
    db.refresh(message)
    return outbox(db, status=None, limit=1)[0] if message else None  # type: ignore[return-value]
