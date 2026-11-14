"""Build a campaign audience in batches. Sending stays on the shared outbox."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.services.messaging_service import priority_for
from app.services.settings_service import load_settings
from reach.models import ReachCampaign, ReachCampaignRun, ReachRecipient, ReachReportArtifact
from reach.report_pdf import render_run
from reach.runs import present, recipients as list_recipients, refresh_run, report_csv
from reach.service import _gate, _render

_BATCH_DEFAULT = 200


def prepare_due(db: Session, settings: Settings) -> int:
    """Prepare a few pages of any run still marked preparing. Safe to call again."""
    recover_leases(db)
    made = 0
    pages = 5
    for _ in range(pages):
        query = (
            select(ReachCampaignRun)
            .where(ReachCampaignRun.status == "preparing")
            .order_by(ReachCampaignRun.created_at)
            .limit(1)
        )
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        run = db.scalar(query)
        if run is None:
            break
        if _prepare_page(db, settings, run) == 0 and run.status != "preparing":
            break
        made += 1
        db.commit()
    publish_due_reports(db)
    db.commit()
    return made


def _prepare_page(db: Session, settings: Settings, run: ReachCampaignRun) -> int:
    campaign = db.get(ReachCampaign, run.campaign_id)
    if campaign is None:
        run.status = "failed"
        return 0
    batch = max(1, int(getattr(settings, "reach_prepare_batch", _BATCH_DEFAULT)))
    people = _page(db, run, batch)
    if not people:
        _finish_preparing(db, run, campaign)
        return 0
    business = load_settings(db).legal_name or "AxizPOS"
    content = run.content_snapshot or campaign.content or {}
    channels = [part for part in (run.channel or "").split(",") if part]
    when = campaign.scheduled_at or datetime.now(UTC)
    from reach.service import _channel_provider, _evolution_ready, _phone_digits

    evolution = _channel_provider(db, "whatsapp") == "evolution" and _evolution_ready(db)
    connection_id = None
    if evolution:
        from reach.models import ReachConnection

        connection_id = db.scalar(select(ReachConnection.id).where(ReachConnection.status == "open").limit(1))
    seen: set[str] = set()
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    used = int(
        db.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(
                OutboundMessage.template_key == "campaign",
                OutboundMessage.channel == "whatsapp",
                OutboundMessage.created_at >= start,
            )
        )
        or 0
    )
    room = [max(0, int(getattr(settings, "reach_daily_recipient_limit", 1000)) - used)]
    for customer in people:
        run.total_candidates += 1
        for channel in channels:
            _one(
                db, run, campaign, customer, channel, content, business, when,
                evolution, connection_id, seen, _phone_digits, room,
            )
    run.prepare_after_id = people[-1].id
    if len(people) < batch:
        _finish_preparing(db, run, campaign)
    return len(people)


def _page(db: Session, run: ReachCampaignRun, batch: int) -> list[Customer]:
    from uuid import UUID

    snapshot = run.audience_snapshot or {}
    query = select(Customer).where(Customer.is_active.is_(True))
    if run.prepare_after_id is not None:
        query = query.where(Customer.id > run.prepare_after_id)
    chosen = snapshot.get("customer_ids")
    if chosen:
        query = query.where(Customer.id.in_([UUID(str(item)) for item in chosen]))
    if snapshot.get("group_id"):
        query = query.where(Customer.group_id == UUID(str(snapshot["group_id"])))
    location = (snapshot.get("location") or "").strip()
    if location:
        query = query.where(Customer.address.ilike(f"%{location}%"))
    product_id = snapshot.get("product_id")
    category_name = (snapshot.get("category") or "").strip()
    if product_id or category_name:
        from app.models.product import Product
        from app.models.sale import Sale
        from app.models.sale_item import SaleItem

        buyers = select(Sale.customer_id).join(SaleItem, SaleItem.sale_id == Sale.id)
        if product_id:
            buyers = buyers.where(SaleItem.product_id == UUID(str(product_id)))
        if category_name:
            buyers = buyers.join(Product, Product.id == SaleItem.product_id).where(Product.category.ilike(category_name))
        query = query.where(Customer.id.in_(buyers))
    minimum = int(snapshot.get("min_loyalty_points") or 0)
    if minimum:
        query = query.where(Customer.loyalty_points >= minimum)
    kind = snapshot.get("customer_type")
    if kind in {"RETAIL", "WHOLESALE"}:
        query = query.where(Customer.customer_type == kind)
    query = _spend_filters(query, snapshot)
    return list(db.scalars(query.order_by(Customer.id).limit(batch)))


def _spend_filters(query, snapshot: dict):
    """Keep inactive, spend, and branch filters in SQL so a page stays stable."""
    from uuid import UUID

    from sqlalchemy import func

    from app.models.sale import Sale
    from reach.service import CLOSED

    inactive_days = int(snapshot.get("inactive_days") or 0)
    min_spend = int(snapshot.get("min_spend_cents") or 0)
    store_id = snapshot.get("store_id")
    if not inactive_days and not min_spend and not store_id:
        return query
    stats = select(Sale.customer_id).where(Sale.status.not_in(tuple(CLOSED)))
    if store_id:
        stats = stats.where(Sale.store_id == UUID(str(store_id)))
    grouped = stats.group_by(Sale.customer_id)
    if min_spend:
        grouped = grouped.having(func.coalesce(func.sum(Sale.total_cents), 0) >= min_spend)
    if inactive_days:
        cutoff = datetime.now(UTC) - timedelta(days=inactive_days)
        grouped = grouped.having(func.max(Sale.created_at) < cutoff)
    if store_id or min_spend or inactive_days:
        if inactive_days and not store_id and not min_spend:
            recent = (
                select(Sale.customer_id)
                .where(Sale.status.not_in(tuple(CLOSED)), Sale.created_at >= cutoff)
                .group_by(Sale.customer_id)
            )
            return query.where(Customer.id.not_in(recent))
        return query.where(Customer.id.in_(grouped))
    return query


def _one(db, run, campaign, customer, channel, content, business, when, evolution, connection_id, seen, phone_digits, room) -> None:
    piece = content.get(channel) or {}
    body = _render(piece.get("body") or "", customer, business, business)
    subject = _render(piece.get("subject") or campaign.name, customer, business, business)
    error = _gate(customer, channel, seen)
    if error:
        _count_exclusion(run, error)
        db.add(
            ReachRecipient(
                campaign_id=campaign.id,
                campaign_run_id=run.id,
                customer_id=customer.id,
                phone=(phone_digits(customer.phone) or customer.email or "")[:254],
                body=body,
                status="skipped",
                failure_reason=error,
            )
        )
        return
    if channel == "whatsapp" and room[0] <= 0:
        _count_exclusion(run, "Daily WhatsApp limit reached.")
        db.add(
            ReachRecipient(
                campaign_id=campaign.id,
                campaign_run_id=run.id,
                customer_id=customer.id,
                phone=(phone_digits(customer.phone) or customer.email or "")[:254],
                body=body,
                status="skipped",
                failure_reason="Daily WhatsApp limit reached.",
            )
        )
        return
    address = customer.email if channel == "email" else customer.phone
    context = {"campaign_id": str(campaign.id), "campaign_run_id": str(run.id)}
    charged = evolution and channel == "whatsapp"
    if charged:
        context["reach_credit"] = "1"
    message = OutboundMessage(
        channel=channel,
        to_address=address or "",
        customer_id=customer.id,
        template_key="campaign",
        priority=priority_for("campaign"),
        subject=subject[:200],
        body=body,
        status="QUEUED",
        dedupe_key=f"campaign:{campaign.id}:{run.id}:{customer.id}:{channel}",
        context=context,
        next_attempt_at=when,
    )
    try:
        with db.begin_nested():
            db.add(message)
            db.flush()
            db.add(
                ReachRecipient(
                    campaign_id=campaign.id,
                    campaign_run_id=run.id,
                    customer_id=customer.id,
                    outbound_message_id=message.id,
                    connection_id=connection_id if channel == "whatsapp" else None,
                    phone=(phone_digits(address) or address or "")[:254],
                    body=body,
                    status="queued",
                )
            )
            db.flush()
    except IntegrityError:
        run.duplicate_count += 1
        return
    if charged:
        from reach import credits as credit_book

        try:
            credit_book.reserve_one(db, campaign.id, message.id)
        except Exception:
            message.status = "SKIPPED"
            message.last_error = "Not enough message credit."
            recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
            if recipient is not None:
                recipient.status = "skipped"
                recipient.failure_reason = message.last_error
            run.eligible_recipients = max(0, run.eligible_recipients)
            return
    run.eligible_recipients += 1
    run.queued_count += 1
    if channel == "whatsapp":
        room[0] -= 1


def _count_exclusion(run: ReachCampaignRun, error: str) -> None:
    run.excluded_recipients += 1
    text = error.lower()
    if "consent" in text:
        run.no_consent_count += 1
    elif "duplicate" in text:
        run.duplicate_count += 1
    elif "address" in text or "not valid" in text:
        run.invalid_contact_count += 1


def _finish_preparing(db: Session, run: ReachCampaignRun, campaign: ReachCampaign) -> None:
    run.status = "dispatching" if run.eligible_recipients else "completed"
    if run.status == "completed":
        run.completed_at = datetime.now(UTC)
    campaign.eligible_count = run.eligible_recipients
    campaign.suppressed_count = run.excluded_recipients
    campaign.queued_count = run.queued_count
    campaign.status = run.status
    if not run.total_recipients:
        run.total_recipients = run.total_candidates
    refresh_run(db, run.id)


def recover_leases(db: Session) -> int:
    """A send that died after the lease, and before a provider id, can be queued again."""
    now = datetime.now(UTC)
    rows = list(
        db.scalars(
            select(ReachRecipient).where(
                ReachRecipient.status == "sending",
                ReachRecipient.lease_until.is_not(None),
                ReachRecipient.lease_until < now,
            )
        )
    )
    recovered = 0
    for recipient in rows:
        message = db.get(OutboundMessage, recipient.outbound_message_id) if recipient.outbound_message_id else None
        if message is not None and message.provider_message_id:
            message.status = "SENT"
            recipient.status = "sent"
            _refresh_recipient_run(db, recipient)
            continue
        if message is not None and (message.context or {}).get("ambiguous_timeout") == "1":
            recipient.status = "failed"
            _refresh_recipient_run(db, recipient)
            continue
        if message is not None and message.status == "QUEUED":
            message.next_attempt_at = now
        recipient.status = "queued"
        recipient.lease_until = None
        recovered += 1
        _refresh_recipient_run(db, recipient)
    return recovered


def _refresh_recipient_run(db: Session, recipient: ReachRecipient) -> None:
    if recipient.campaign_run_id is None:
        return
    from reach.runs import refresh_run

    refresh_run(db, recipient.campaign_run_id)


def lease_recipient(db: Session, message: OutboundMessage, seconds: int = 120) -> None:
    recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    if recipient is None:
        return
    until = datetime.now(UTC) + timedelta(seconds=seconds)
    recipient.status = "sending"
    recipient.processing_started_at = datetime.now(UTC)
    recipient.lease_until = until
    message.next_attempt_at = until
    _refresh_recipient_run(db, recipient)


def publish_due_reports(db: Session) -> None:
    now = datetime.now(UTC)
    runs = list(
        db.scalars(
            select(ReachCampaignRun).where(
                ReachCampaignRun.status.in_(("completed", "completed_with_errors", "cancelled", "failed")),
                or_(ReachCampaignRun.report_version == 0, ReachCampaignRun.report_dirty.is_(True)),
            )
        )
    )
    for run in runs:
        stale = run.report_dirty and (
            run.report_built_at is None or run.report_built_at < now - timedelta(seconds=60)
        )
        if run.report_version and not stale:
            continue
        if not run.report_version or stale:
            _write_version(db, run)


def _write_version(db: Session, run: ReachCampaignRun) -> None:
    from reach.report_pdf import PDF_RECIPIENT_CAP
    from reach.report_store import put

    version = int(run.report_version or 0) + 1
    body = present(db, run)
    people: list[dict] = []
    offset = 0
    total_rows = 0
    while True:
        page, total_rows = list_recipients(db, run.id, status=None, offset=offset, limit=500)
        if not page:
            break
        if len(people) < PDF_RECIPIENT_CAP:
            people.extend(page[: PDF_RECIPIENT_CAP - len(people)])
        offset += len(page)
        if len(page) < 500:
            break
    body["recipient_rows"] = total_rows
    pdf = render_run(body, people)
    csv_text = report_csv(db, run.id).encode()
    for name, data, kind, content_type in (
        ("report.pdf", pdf, "pdf", "application/pdf"),
        ("recipients.csv", csv_text, "csv", "text/csv"),
    ):
        key = f"reach-reports/{run.campaign_id}/{run.id}/v{version}/{name}"
        digest = put(key, data)
        db.add(
            ReachReportArtifact(
                run_id=run.id,
                version=version,
                kind=kind,
                storage_key=key,
                file_name=name,
                content_type=content_type,
                size_bytes=len(data),
                checksum=digest,
            )
        )
    run.report_version = version
    run.report_dirty = False
    run.report_built_at = datetime.now(UTC)


def read_artifact(db: Session, run_id, kind: str) -> tuple[bytes, str] | None:
    from reach.report_store import checksum, get

    row = db.scalar(
        select(ReachReportArtifact)
        .where(ReachReportArtifact.run_id == run_id, ReachReportArtifact.kind == kind)
        .order_by(ReachReportArtifact.version.desc())
        .limit(1)
    )
    if row is None:
        return None
    data = get(row.storage_key)
    if data is None or checksum(data) != row.checksum:
        return None
    return data, row.content_type
