"""Customer messaging: render a template, check consent, queue it in the outbox, and dispatch the outbox."""

import logging
import re
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
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
from app.services.messaging_providers import CHANNEL_PROVIDERS, Outgoing, ProviderError
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
    """Transactional consent: receipts, statements, and other essential notices."""
    return bool(getattr(customer, f"{channel}_opt_in", False))


def marketing_consented(customer: Customer, channel: str) -> bool:
    """Marketing consent is separate. A receipt opt-in does not allow a campaign."""
    return bool(getattr(customer, f"marketing_{channel}_opt_in", False))


MARKETING_KEYS = frozenset({"campaign", "coupon_issued"})
# Lower number wins. Promotional keys are the only low-priority class.
# Anything the server does not recognise stays transactional, so a caller cannot demote a receipt
# or promote a campaign by inventing a template name.
_OPERATIONAL_KEYS = frozenset(
    {"overdue_reminder", "warranty_expiry", "layaway_reminder", "reorder_due", "ai_agent"}
)


def priority_for(template_key: str | None) -> int:
    """Trusted classification. There is no argument for a client-supplied priority."""
    if template_key in MARKETING_KEYS:
        return 3
    if template_key in _OPERATIONAL_KEYS:
        return 2
    return 1


def choose_next(candidates: list[tuple[str, int, datetime]], *, allow_marketing: bool) -> int | None:
    """Index of the next queued message.

    The choice is made between sends. A provider call that has already started is not a candidate,
    so it is never cancelled. Lower priority number wins. At the same priority the older message
    wins, which keeps one tenant's campaign from sitting in front of another's.
    """
    best: tuple[tuple[int, datetime, str], int] | None = None
    for index, (tenant, priority, created) in enumerate(candidates):
        if not allow_marketing and priority >= 3:
            continue
        key = (priority, created, tenant)
        if best is None or key < best[0]:
            best = (key, index)
    return None if best is None else best[1]


def preferred_channel(customer: Customer, db: Session | None = None) -> str | None:
    from app.services.reach_bridge import channel_enabled

    for channel in CHANNELS:
        if db is not None and not channel_enabled(db, channel):
            continue
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
    from app.services.reach_bridge import channel_enabled

    chosen = channel or preferred_channel(customer, db)
    if channel is not None and not channel_enabled(db, channel):
        chosen = None
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
        priority=priority_for(template_key),
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


def _delivery(db: Session, settings: Settings, channel: str) -> tuple[str, dict]:
    """Tenant channel row wins. No row keeps the existing server provider, so current tenants keep working."""
    from app.services.reach_bridge import channel_credentials

    return channel_credentials(db, settings, channel)


def _ready_clause(now: datetime, reach_on: bool):
    ready = OutboundMessage.next_attempt_at <= now
    if not reach_on:
        return ready
    return or_(
        ready,
        and_(
            OutboundMessage.template_key.in_(("campaign", "ai_agent")),
            OutboundMessage.last_error.like("AxizReach is off%"),
        ),
    )


def _next_message(
    db: Session,
    now: datetime,
    *,
    reach_on: bool,
    template_key: str | None,
    allow_marketing: bool,
) -> OutboundMessage | None:
    """The next queued row for this tenant. Re-read each time so a receipt queued mid-batch jumps ahead."""
    waiting = select(OutboundMessage).where(OutboundMessage.status == "QUEUED", _ready_clause(now, reach_on))
    if template_key is not None:
        waiting = waiting.where(OutboundMessage.template_key == template_key)
    if not allow_marketing:
        waiting = waiting.where(OutboundMessage.priority < 3)
    return db.scalars(
        waiting.order_by(OutboundMessage.priority, OutboundMessage.created_at, OutboundMessage.id).limit(1)
    ).first()


def dispatch_due(
    db: Session,
    settings: Settings,
    limit: int = 50,
    template_key: str | None = None,
    allow_marketing: bool | None = None,
) -> dict[str, int]:
    """Sends queued messages whose time has come. Transient failures back off exponentially.

    Each pass picks one row. A receipt that lands while a campaign is going out is selected
    before the next promotional row. The provider call already in progress is left to finish.
    """
    from app.core.capabilities import Capability, has_capability

    now = datetime.now(UTC)
    try:
        from reach.prepare import recover_leases

        recover_leases(db)
    except Exception:  # noqa: BLE001 - preparation recovery must not stop other mail
        logger.exception("expired send leases were not recovered")
    reach_on = has_capability(db, Capability.AXIZ_REACH)
    if allow_marketing is True:
        marketing_cap = limit
    elif allow_marketing is False:
        marketing_cap = 0
    else:
        reserve = min(settings.reach_transactional_reserve, limit)
        marketing_cap = max(0, limit - reserve)
    counts = {"sent": 0, "failed": 0, "retry": 0}
    evolution_sent = 0
    marketing_sent = 0
    for _ in range(limit):
        # The gap is between provider calls. The next row is chosen after it, so a receipt
        # that arrived during the gap goes out before the next promotional message.
        if evolution_sent and settings.reach_send_interval_seconds:
            time.sleep(settings.reach_send_interval_seconds)
        db.flush()
        message = _next_message(
            db,
            now,
            reach_on=reach_on,
            template_key=template_key,
            allow_marketing=marketing_sent < marketing_cap,
        )
        if message is None:
            break
        if message.template_key == "campaign" and not reach_on:
            message.next_attempt_at = now + timedelta(hours=6)
            message.last_error = "AxizReach is off. This campaign stays queued until the add-on is on."
            counts["retry"] += 1
            continue
        from app.services.reach_bridge import hold_reason

        reason = hold_reason(db, message)
        if reason:
            if " " in reason:
                message.last_error = reason[:500]
            message.next_attempt_at = now + timedelta(minutes=15)
            counts["retry"] += 1
            continue
        if message.template_key in MARKETING_KEYS and message.customer_id is not None:
            person = db.get(Customer, message.customer_id)
            if person is None or not marketing_consented(person, message.channel):
                message.status = "SKIPPED"
                message.last_error = "Marketing consent was withdrawn before send."
                from app.services.reach_bridge import after_skipped

                after_skipped(db, message)
                continue
        try:
            provider, creds = _delivery(db, settings, message.channel)
        except ProviderError as exc:
            message.last_error = str(exc)[:500]
            if exc.permanent:
                message.status = "FAILED"
                counts["failed"] += 1
            else:
                message.next_attempt_at = now + timedelta(minutes=15)
                counts["retry"] += 1
            continue
        if provider == "evolution" and evolution_sent >= settings.reach_send_batch:
            message.next_attempt_at = now + timedelta(seconds=max(settings.reach_send_interval_seconds, 1))
            counts["retry"] += 1
            continue
        if message.template_key == "ai_agent":
            try:
                from reach.ai_agent.hold import release_if_stale
            except Exception:  # noqa: BLE001 - a missing plugin must not stop other outbox mail
                release_if_stale = None
            if release_if_stale is not None and release_if_stale(db, message):
                continue
        message.provider = provider
        message.attempts += 1
        try:
            from reach.prepare import lease_recipient

            lease_recipient(db, message)
            db.commit()
        except Exception:  # noqa: BLE001 - a missing plugin must not stop the send
            logger.exception("message %s was not marked in progress", message.id)
        if message.template_key == "campaign" and message.customer_id is not None:
            person = db.get(Customer, message.customer_id)
            if person is None or not marketing_consented(person, message.channel):
                message.status = "SKIPPED"
                message.last_error = "Marketing consent was withdrawn before sending."
                from app.services.reach_bridge import after_skipped

                after_skipped(db, message)
                continue
        if message.template_key == "ai_agent":
            logger.info(
                "[AXIZREACH_AI] stage=outbound_dispatch_started message_id=%s retry_count=%s",
                message.id,
                message.attempts,
            )
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
            from app.services.reach_bridge import after_sent, record_usage, submit_message

            message.provider_message_id = submit_message(db, settings, provider, outgoing, creds, message)[:120] or None
            message.status = "SENT"
            message.sent_at = datetime.now(UTC)
            message.last_error = None
            if message.template_key == "ai_agent" and provider == "evolution":
                logger.info(
                    "[AXIZREACH_AI] stage=evolution_send_accepted message_id=%s provider_message_id=%s retry_count=%s",
                    message.id,
                    message.provider_message_id,
                    message.attempts,
                )
            record_usage(db, message)
            after_sent(db, message)
            counts["sent"] += 1
            if provider == "evolution":
                evolution_sent += 1
            if message.template_key in MARKETING_KEYS:
                marketing_sent += 1
        except ProviderError as exc:
            if getattr(exc, "ambiguous", False):
                message.status = "FAILED"
                message.last_error = "Ambiguous provider timeout."
                message.context = {**(message.context or {}), "ambiguous_timeout": "1"}
                from app.services.reach_bridge import after_failed

                after_failed(db, message)
                counts["failed"] += 1
                continue
            message.last_error = str(exc)[:500]
            if message.template_key == "ai_agent":
                logger.info(
                    "[AXIZREACH_AI] stage=evolution_send_failed message_id=%s retry_count=%s",
                    message.id,
                    message.attempts,
                )
            if exc.permanent or message.attempts >= MAX_ATTEMPTS:
                message.status = "FAILED"
                from app.services.reach_bridge import after_failed

                after_failed(db, message)
                counts["failed"] += 1
            else:
                message.next_attempt_at = now + timedelta(minutes=2**message.attempts)
                counts["retry"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the batch
            logger.exception("message %s failed", message.id)
            message.last_error = str(exc)[:500]
            message.next_attempt_at = now + timedelta(minutes=2**message.attempts)
            counts["retry"] += 1
        if message.template_key in MARKETING_KEYS and message.status == "QUEUED":
            marketing_sent += 1
        db.flush()
    db.commit()
    note_backlog(db, settings)
    return counts


def note_backlog(db: Session, settings: Settings) -> None:
    """Log when transactional mail is waiting too long, or a campaign queue is deep. Counts stay inside this store."""
    metrics = queue_metrics(db)
    wait = metrics["oldest_transactional_seconds"]
    if wait is not None and wait > settings.reach_alert_transactional_wait_seconds:
        logger.warning("transactional messages have been queued for %ss", wait)
    if metrics["campaign_queued"] >= settings.reach_alert_campaign_backlog:
        logger.warning("promotional queue depth is %s", metrics["campaign_queued"])


def queue_metrics(db: Session) -> dict[str, object]:
    now = datetime.now(UTC)
    rows = db.execute(
        select(OutboundMessage.priority, func.count(), func.min(OutboundMessage.created_at)).where(
            OutboundMessage.status == "QUEUED"
        ).group_by(OutboundMessage.priority)
    ).all()
    by_priority = {1: 0, 2: 0, 3: 0}
    oldest: datetime | None = None
    oldest_by_priority: dict[int, datetime | None] = {1: None, 2: None, 3: None}
    for priority, count, created in rows:
        by_priority[int(priority)] = int(count)
        if created is not None and (oldest is None or created < oldest):
            oldest = created
        if int(priority) in oldest_by_priority and created is not None:
            oldest_by_priority[int(priority)] = created

    def age(value: datetime | None) -> int | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return max(0, int((now - value).total_seconds()))

    return {
        "queued": sum(by_priority.values()),
        "by_priority": by_priority,
        "transactional_queued": by_priority[1],
        "operational_queued": by_priority[2],
        "campaign_queued": by_priority[3],
        "oldest_queued_seconds": age(oldest),
        "oldest_transactional_seconds": age(oldest_by_priority[1]),
        "oldest_operational_seconds": age(oldest_by_priority[2]),
        "oldest_promotional_seconds": age(oldest_by_priority[3]),
    }


def dispatch_across_tenants(settings: Settings) -> dict[str, int]:
    """One shared pass over every open tenant.

    Each step peeks one due row per tenant and sends only the winner. A receipt in one store
    is sent before a promotional row in another. Rows are still read inside that store's
    tenant scope, so one store never loads another's messages.
    """
    from app.core.database import get_session_factory
    from app.jobs.runner import note_result
    from app.tenancy.context import use_tenant
    from app.tenancy.registry import active_tenants

    tenants = list(active_tenants(settings))
    totals = {"sent": 0, "failed": 0, "retry": 0}
    if not tenants:
        return totals
    if not _hold_dispatch_lock(tenants[0]):
        return totals
    per_tenant: dict[str, dict[str, int]] = {
        tenant.id: {"sent": 0, "failed": 0, "retry": 0} for tenant in tenants
    }
    try:
        budget = settings.reach_send_batch
        reserve = min(settings.reach_transactional_reserve, budget)
        marketing_cap = max(0, budget - reserve)
        marketing_sent = 0
        pace = False
        for _ in range(budget):
            if pace and settings.reach_send_interval_seconds:
                time.sleep(settings.reach_send_interval_seconds)
            allow_marketing = marketing_sent < marketing_cap
            candidates: list[tuple[object, object, int, datetime, str]] = []
            for tenant in tenants:
                with use_tenant(tenant), get_session_factory()() as db:
                    now = datetime.now(UTC)
                    from app.core.capabilities import Capability, has_capability

                    message = _next_message(
                        db,
                        now,
                        reach_on=has_capability(db, Capability.AXIZ_REACH),
                        template_key=None,
                        allow_marketing=allow_marketing,
                    )
                    if message is None:
                        continue
                    created = message.created_at or datetime.now(UTC)
                    candidates.append((tenant, message.id, message.priority, created, message.channel))
            if not candidates:
                break
            picked = choose_next(
                [
                    (str(tenant.slug), priority, created)
                    for tenant, _message_id, priority, created, _channel in candidates
                ],
                allow_marketing=allow_marketing,
            )
            if picked is None:
                break
            tenant, _message_id, priority, _created, channel = candidates[picked]
            with use_tenant(tenant), get_session_factory()() as db:
                counts = dispatch_due(db, settings, limit=1, allow_marketing=allow_marketing)
            for key in totals:
                totals[key] += counts[key]
                per_tenant[tenant.id][key] += counts[key]
            pace = channel == "whatsapp" and counts["sent"] > 0
            if priority >= 3 and counts["sent"]:
                marketing_sent += 1
            elif counts["sent"] == 0 and counts["failed"] == 0 and counts["retry"] == 0:
                break
    except Exception:
        logger.exception("fair dispatch failed")
    finally:
        _release_dispatch_lock()
    summary = ", ".join(f"{value} {key}" for key, value in totals.items())
    for tenant in tenants:
        counts = per_tenant[tenant.id]
        line = ", ".join(f"{value} {key}" for key, value in counts.items())
        try:
            with use_tenant(tenant), get_session_factory()() as db:
                note_result(db, "dispatch_messages", "ok", f"{line} (shared {summary})")
        except Exception:  # noqa: BLE001 - a jobs-page note must not undo a send
            logger.exception("dispatch result was not recorded for %s", tenant.slug)
    return totals


_LOCK_SESSION: Session | None = None


def _hold_dispatch_lock(tenant: object) -> bool:
    """One API process drains a shared database. The connection stays open so the lock stays held."""
    global _LOCK_SESSION
    from sqlalchemy import text

    from app.core.database import get_session_factory
    from app.tenancy.context import use_tenant

    with use_tenant(tenant):
        db = get_session_factory()()
        try:
            if db.get_bind().dialect.name != "postgresql":
                return True
            if not db.execute(text("SELECT pg_try_advisory_lock(48291017)")).scalar():
                return False
            _LOCK_SESSION = db
            db = None
            return True
        finally:
            if db is not None:
                db.close()


def _release_dispatch_lock() -> None:
    global _LOCK_SESSION
    from sqlalchemy import text

    db = _LOCK_SESSION
    _LOCK_SESSION = None
    if db is None:
        return
    try:
        db.execute(text("SELECT pg_advisory_unlock(48291017)"))
        db.commit()
    finally:
        db.close()


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


def outbox_summary(db: Session) -> dict:
    """Campaign rows stay in the marketing bucket so an overview does not count them twice."""
    marketing = {"campaign", "coupon_issued"}
    buckets = {
        "transactional": {"SENT": 0, "FAILED": 0, "QUEUED": 0, "SKIPPED": 0},
        "marketing": {"SENT": 0, "FAILED": 0, "QUEUED": 0, "SKIPPED": 0},
    }
    rows = db.execute(
        select(OutboundMessage.template_key, OutboundMessage.status, func.count()).group_by(
            OutboundMessage.template_key, OutboundMessage.status
        )
    ).all()
    for key, status, count in rows:
        bucket = "marketing" if key in marketing else "transactional"
        if status in buckets[bucket]:
            buckets[bucket][status] += int(count)
    return buckets


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
        subject="AxizPOS test message",
        body="This is a test message from AxizPOS. Messaging is set up.",
        status="QUEUED",
    )
    db.add(message)
    db.commit()
    dispatch_due(db, settings, limit=10)
    db.refresh(message)
    return outbox(db, status=None, limit=1)[0] if message else None  # type: ignore[return-value]
