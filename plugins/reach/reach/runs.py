"""Campaign executions. Sending still goes through the shared outbox at promotional priority."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.models.user import User
from app.services.messaging_service import marketing_consented, priority_for
from reach.models import ReachCampaign, ReachCampaignRun, ReachRecipient

ACTIVE = frozenset({"queued", "processing", "scheduled", "building", "preparing", "dispatching"})
TERMINAL = frozenset({"completed", "completed_with_errors", "cancelled", "failed"})


def begin_run(
    db: Session,
    campaign: ReachCampaign,
    actor_id: uuid.UUID | None,
    audience: dict,
    channels: list[str],
    total: int,
    *,
    retry_of: uuid.UUID | None = None,
    preparing: bool = False,
) -> ReachCampaignRun:
    """The next run number for this campaign. A unique constraint stops two users taking the same number."""
    statement = select(ReachCampaign).where(ReachCampaign.id == campaign.id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    db.execute(statement)
    for _ in range(3):
        current = db.scalar(
            select(func.max(ReachCampaignRun.run_number)).where(ReachCampaignRun.campaign_id == campaign.id)
        )
        chosen = list(dict.fromkeys(channels))
        kind = "retry" if retry_of is not None else "selected" if audience.get("customer_ids") else "filter"
        run = ReachCampaignRun(
            campaign_id=campaign.id,
            run_number=int(current or 0) + 1,
            status="preparing" if preparing else "processing",
            channel=chosen[0] if len(chosen) == 1 else ",".join(chosen),
            audience_type=kind,
            audience_snapshot=dict(audience),
            total_recipients=total,
            initiated_by_id=actor_id,
            started_at=datetime.now(UTC),
            retry_of_run_id=retry_of,
        )
        try:
            with db.begin_nested():
                db.add(run)
                db.flush()
            return run
        except IntegrityError:
            continue
    raise ApiError(409, "run_conflict", "The campaign run could not be numbered. Start it again.")


def finish_run(run: ReachCampaignRun, *, eligible: int, excluded: int, later: bool) -> None:
    run.eligible_recipients = eligible
    run.excluded_recipients = excluded
    run.queued_count = eligible
    run.skipped_count = excluded
    run.cancelled_count = 0
    if eligible == 0:
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.report_built_at = run.completed_at
    elif later:
        run.status = "scheduled"
    else:
        run.status = "processing"


def refresh_run(db: Session, run_id: uuid.UUID, *, delivery: bool = False) -> None:
    """Recount one run from its recipient rows. A person has one status, so counts are not added together."""
    run = db.get(ReachCampaignRun, run_id)
    if run is None:
        return
    rows = db.execute(
        select(ReachRecipient.status, func.count())
        .where(ReachRecipient.campaign_run_id == run_id)
        .group_by(ReachRecipient.status)
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    run.queued_count = counts.get("queued", 0) + counts.get("pending", 0)
    run.processing_count = counts.get("sending", 0)
    run.sent_count = counts.get("sent", 0)
    run.delivered_count = counts.get("delivered", 0)
    run.read_count = counts.get("read", 0)
    run.failed_count = counts.get("failed", 0)
    run.skipped_count = counts.get("skipped", 0)
    run.cancelled_count = counts.get("cancelled", 0)
    if delivery:
        run.delivery_updated_at = datetime.now(UTC)
        run.report_dirty = True
    if run.status in {"preparing", "cancelled"}:
        if run.status == "cancelled" and run.queued_count == 0 and run.completed_at is None:
            run.completed_at = datetime.now(UTC)
        return
    processed = (
        run.sent_count
        + run.delivered_count
        + run.read_count
        + run.failed_count
        + run.skipped_count
        + run.cancelled_count
    )
    if run.eligible_recipients and run.queued_count == 0 and processed >= run.eligible_recipients:
        run.status = "completed_with_errors" if run.failed_count else "completed"
        if run.completed_at is None:
            run.completed_at = datetime.now(UTC)
        if run.report_built_at is None:
            run.report_built_at = run.completed_at


def touch_message(db: Session, message: OutboundMessage) -> None:
    raw = (message.context or {}).get("campaign_run_id")
    if not raw:
        return
    try:
        refresh_run(db, uuid.UUID(str(raw)))
    except ValueError:
        return


def get_run(db: Session, run_id: uuid.UUID) -> ReachCampaignRun:
    run = db.get(ReachCampaignRun, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Campaign run not found.")
    return run


def list_runs(
    db: Session,
    *,
    campaign_id: uuid.UUID | None,
    status: str | None,
    channel: str | None,
    offset: int,
    limit: int,
) -> tuple[list[ReachCampaignRun], int]:
    query = select(ReachCampaignRun)
    if campaign_id is not None:
        query = query.where(ReachCampaignRun.campaign_id == campaign_id)
    if status:
        query = query.where(ReachCampaignRun.status == status)
    if channel:
        query = query.where(ReachCampaignRun.channel == channel)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        db.scalars(
            query.order_by(ReachCampaignRun.created_at.desc()).offset(offset).limit(min(max(limit, 1), 100))
        )
    )
    return rows, total


def active_runs(db: Session) -> list[ReachCampaignRun]:
    return list(
        db.scalars(
            select(ReachCampaignRun)
            .where(ReachCampaignRun.status.in_(tuple(ACTIVE)))
            .order_by(ReachCampaignRun.started_at.desc())
            .limit(20)
        )
    )


def present(db: Session, run: ReachCampaignRun) -> dict:
    campaign = db.get(ReachCampaign, run.campaign_id)
    user = db.get(User, run.initiated_by_id) if run.initiated_by_id else None
    accepted = run.sent_count + run.delivered_count + run.read_count
    delivered = run.delivered_count + run.read_count
    eligible = run.eligible_recipients
    done = max(0, eligible - run.queued_count - run.processing_count)
    return {
        "id": run.id,
        "campaign_id": run.campaign_id,
        "campaign_name": campaign.name if campaign is not None else "",
        "run_number": run.run_number,
        "status": run.status,
        "phase": _phase(run),
        "channel": run.channel,
        "audience_type": run.audience_type,
        "audience_snapshot": run.audience_snapshot or {},
        "total_recipients": run.total_recipients,
        "total_candidates": run.total_candidates,
        "eligible_recipients": eligible,
        "excluded_recipients": run.excluded_recipients,
        "queued_count": run.queued_count,
        "processing_count": run.processing_count,
        "sent_count": run.sent_count,
        "accepted_count": accepted,
        "delivered_count": delivered,
        "read_count": run.read_count,
        "failed_count": run.failed_count,
        "skipped_count": run.skipped_count,
        "cancelled_count": run.cancelled_count,
        "remaining": run.queued_count,
        "progress_percent": round(100 * done / eligible, 1) if eligible else 0,
        "delivery_rate": round(100 * delivered / accepted, 1) if accepted else None,
        "failure_rate": round(100 * run.failed_count / eligible, 1) if eligible else None,
        "initiated_by": (user.full_name or user.email) if user is not None else None,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "report_built_at": run.report_built_at,
        "delivery_updated_at": run.delivery_updated_at,
        "retry_of_run_id": run.retry_of_run_id,
        "report_version": run.report_version,
        "updated_at": run.updated_at,
    }


def _phase(run: ReachCampaignRun) -> str:
    if run.status == "preparing":
        return "preparing"
    if run.status in {"dispatching", "processing", "queued", "scheduled"}:
        return "sending"
    accepted = run.sent_count + run.delivered_count + run.read_count
    confirmed = run.delivered_count + run.read_count
    if run.status in {"completed", "completed_with_errors"} and accepted > confirmed:
        return "waiting_for_delivery"
    if run.status == "completed_with_errors":
        return "partially_completed"
    if run.status == "cancelled":
        return "cancelled"
    if run.status == "failed":
        return "failed"
    return "completed"


def mask_contact(value: str) -> str:
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:1]}***@{domain}" if name else f"***@{domain}"
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 4:
        return "••••"
    return f"••••{digits[-4:]}"


def recipients(
    db: Session, run_id: uuid.UUID, *, status: str | None, offset: int, limit: int
) -> tuple[list[dict], int]:
    get_run(db, run_id)
    query = select(ReachRecipient).where(ReachRecipient.campaign_run_id == run_id)
    if status:
        query = query.where(ReachRecipient.status == status)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        db.scalars(query.order_by(ReachRecipient.created_at).offset(offset).limit(min(max(limit, 1), 100)))
    )
    customers = {}
    ids = {row.customer_id for row in rows if row.customer_id}
    if ids:
        customers = {row.id: row for row in db.scalars(select(Customer).where(Customer.id.in_(ids)))}
    body = []
    for row in rows:
        person = customers.get(row.customer_id)
        body.append(
            {
                "id": row.id,
                "customer": (person.company_name or person.name) if person is not None else "",
                "contact": mask_contact(row.phone or ""),
                "status": row.status,
                "provider_message_id": row.provider_message_id,
                "sent_at": row.submitted_at,
                "delivered_at": row.delivered_at,
                "read_at": row.read_at,
                "failure_reason": row.failure_reason,
            }
        )
    return body, total


def cancel_run(db: Session, run_id: uuid.UUID) -> ReachCampaignRun:
    """Stop unsent promotional rows for this run. Accepted messages and receipts stay as they are."""
    run = get_run(db, run_id)
    if run.status == "cancelled":
        return run
    queued = db.scalars(
        select(OutboundMessage).where(
            OutboundMessage.template_key == "campaign",
            OutboundMessage.status == "QUEUED",
            OutboundMessage.priority >= 3,
        )
    )
    for message in queued:
        if str((message.context or {}).get("campaign_run_id") or "") != str(run.id):
            continue
        message.status = "SKIPPED"
        message.last_error = "Campaign cancelled before send."
        recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
        if recipient is not None and recipient.status in {"pending", "queued", "sending"}:
            recipient.status = "cancelled"
            recipient.failure_reason = message.last_error
    run.status = "cancelled"
    run.completed_at = datetime.now(UTC)
    if run.report_built_at is None:
        run.report_built_at = run.completed_at
    refresh_run(db, run.id)
    run.status = "cancelled"
    db.commit()
    db.refresh(run)
    return run


def retry_failed(db: Session, actor_id: uuid.UUID | None, run_id: uuid.UUID) -> ReachCampaignRun:
    """A new run for recipients that failed. The original run and its report stay unchanged."""
    source = get_run(db, run_id)
    failed = list(
        db.scalars(
            select(ReachRecipient).where(
                ReachRecipient.campaign_run_id == source.id,
                ReachRecipient.status == "failed",
            )
        )
    )
    if not failed:
        raise ApiError(422, "nothing_to_retry", "There are no failed messages to retry.")
    campaign = db.get(ReachCampaign, source.campaign_id)
    if campaign is None:
        raise ApiError(404, "not_found", "Campaign not found.")
    run = begin_run(
        db,
        campaign,
        actor_id,
        {"retry_of": str(source.id)},
        [source.channel] if source.channel in {"whatsapp", "sms", "email"} else source.channel.split(","),
        len(failed),
        retry_of=source.id,
    )
    eligible = 0
    now = datetime.now(UTC)
    for recipient in failed:
        if recipient.outbound_message_id is None or recipient.customer_id is None:
            continue
        message = db.get(OutboundMessage, recipient.outbound_message_id)
        if message is not None and (message.context or {}).get("ambiguous_timeout") == "1":
            continue
        customer = db.get(Customer, recipient.customer_id)
        if message is None or customer is None or not marketing_consented(customer, message.channel):
            db.add(
                ReachRecipient(
                    campaign_id=campaign.id,
                    campaign_run_id=run.id,
                    customer_id=recipient.customer_id,
                    phone=recipient.phone,
                    body=recipient.body,
                    status="cancelled",
                    failure_reason="Marketing consent was withdrawn before retry.",
                )
            )
            continue
        copy = OutboundMessage(
            channel=message.channel,
            to_address=message.to_address,
            customer_id=customer.id,
            template_key="campaign",
            priority=priority_for("campaign"),
            subject=message.subject,
            body=message.body,
            status="QUEUED",
            dedupe_key=f"campaign:{campaign.id}:{run.id}:{customer.id}:{message.channel}",
            context={"campaign_id": str(campaign.id), "campaign_run_id": str(run.id), "retry_of": str(source.id)},
            next_attempt_at=now,
        )
        db.add(copy)
        db.flush()
        db.add(
            ReachRecipient(
                campaign_id=campaign.id,
                campaign_run_id=run.id,
                customer_id=customer.id,
                outbound_message_id=copy.id,
                phone=recipient.phone,
                body=recipient.body,
                status="queued",
            )
        )
        eligible += 1
    finish_run(run, eligible=eligible, excluded=len(failed) - eligible, later=False)
    db.commit()
    db.refresh(run)
    return run


# Safety stop so a report cannot grow without a bound. The PDF says when the CSV hit this cap.
REPORT_CSV_MAX = 100_000


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + text
    return text


def report_csv(db: Session, run_id: uuid.UUID) -> str:
    get_run(db, run_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Customer", "Contact", "Status", "Provider reference", "Accepted at", "Delivered at", "Read at", "Failure"])
    offset = 0
    written = 0
    while offset < REPORT_CSV_MAX:
        rows, _total = recipients(db, run_id, status=None, offset=offset, limit=500)
        if not rows:
            break
        for row in rows:
            writer.writerow(
                [
                    _csv_cell(row["customer"]),
                    _csv_cell(row["contact"]),
                    _csv_cell(row["status"]),
                    _csv_cell(row["provider_message_id"] or ""),
                    _csv_cell(row["sent_at"] or ""),
                    _csv_cell(row["delivered_at"] or ""),
                    _csv_cell(row["read_at"] or ""),
                    _csv_cell(row["failure_reason"] or ""),
                ]
            )
            written += 1
            if written >= REPORT_CSV_MAX:
                break
        offset += len(rows)
        if len(rows) < 500 or written >= REPORT_CSV_MAX:
            break
    if written >= REPORT_CSV_MAX:
        writer.writerow(["NOTE", f"Stopped after {REPORT_CSV_MAX} rows.", "", "", "", "", "", ""])
    return buffer.getvalue()
