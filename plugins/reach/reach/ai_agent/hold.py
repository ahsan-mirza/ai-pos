"""Human-first waiting window. Settings live in an existing knowledge row, so no new table is required."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.messaging import OutboundMessage
from reach.ai_agent.models import ReachAiAction, ReachAiConversation, ReachAiEvent, ReachAiKnowledge, ReachAiMessage
from reach.ai_agent.trace import trace

POLICY_KIND = "policy"
POLICY_TITLE = "response"
PRIORITIES = frozenset({"human_first", "ai_first", "human_only", "ai_only"})
DEFAULT_POLICY = {"response_priority": "human_first", "human_wait_seconds": 60, "notify_staff": True}


def response_policy(db: Session) -> dict:
    row = db.scalar(
        select(ReachAiKnowledge).where(ReachAiKnowledge.kind == POLICY_KIND, ReachAiKnowledge.title == POLICY_TITLE)
    )
    if row is None:
        return dict(DEFAULT_POLICY)
    try:
        saved = json.loads(row.body)
    except (TypeError, ValueError):
        return dict(DEFAULT_POLICY)
    priority = saved.get("response_priority")
    if priority not in PRIORITIES:
        priority = DEFAULT_POLICY["response_priority"]
    return {
        "response_priority": priority,
        "human_wait_seconds": _stored_wait(saved.get("human_wait_seconds")),
        "notify_staff": bool(saved.get("notify_staff", True)),
    }


def write_policy(db: Session, payload: dict) -> dict:
    current = response_policy(db)
    if payload.get("response_priority") is not None:
        priority = payload["response_priority"]
        if priority not in PRIORITIES:
            raise ApiError(422, "invalid_priority", "Choose a response priority.")
        current["response_priority"] = priority
    if payload.get("human_wait_seconds") is not None:
        current["human_wait_seconds"] = _wait(payload["human_wait_seconds"])
    if payload.get("notify_staff") is not None:
        current["notify_staff"] = bool(payload["notify_staff"])
    body = json.dumps(current)
    row = db.scalar(
        select(ReachAiKnowledge).where(ReachAiKnowledge.kind == POLICY_KIND, ReachAiKnowledge.title == POLICY_TITLE)
    )
    if row is None:
        db.add(ReachAiKnowledge(kind=POLICY_KIND, title=POLICY_TITLE, body=body, status="ready"))
    else:
        row.body = body
    return current


def wait_seconds(policy: dict) -> int:
    if policy["response_priority"] in {"ai_first", "ai_only"}:
        return 0
    return int(policy["human_wait_seconds"])


def due(created_at: datetime, policy: dict, now: datetime | None = None) -> bool:
    moment = aware(now or datetime.now(UTC))
    return aware(created_at) + timedelta(seconds=wait_seconds(policy)) <= moment


def note_customer_waiting(
    db: Session,
    conversation: ReachAiConversation,
    preview: str,
    policy: dict,
    *,
    message_id=None,
    provider_message_id: str | None = None,
) -> None:
    """Start or restart the staff window from the latest customer line. The handler stays as it is."""
    if policy["response_priority"] not in {"human_first", "human_only"}:
        return
    if conversation.status != "resolved":
        conversation.status = "waiting_staff"
    seconds = wait_seconds(policy)
    detail = f"Staff have {seconds} seconds before an AI reply."
    latest = db.scalar(
        select(ReachAiEvent)
        .where(ReachAiEvent.conversation_id == conversation.id, ReachAiEvent.kind == "waiting_human")
        .order_by(ReachAiEvent.created_at.desc())
        .limit(1)
    )
    refreshed = latest is not None
    if latest is None:
        db.add(ReachAiEvent(conversation_id=conversation.id, kind="waiting_human", detail=detail))
    else:
        latest.detail = detail
    trace(
        "human_wait_refreshed" if refreshed else "human_wait_started",
        conversation_id=conversation.id,
        message_id=message_id,
        provider_message_id=provider_message_id,
        wait_seconds=seconds,
        elapsed_seconds=0,
    )
    if not policy.get("notify_staff", True):
        return
    key = f"wait:{conversation.id}"[:80]
    existing = db.scalar(select(ReachAiAction).where(ReachAiAction.dedupe_key == key))
    if existing is not None:
        existing.details = preview[:1000]
        if existing.status in {"completed", "rejected", "cancelled"}:
            existing.status = "needs_review"
            existing.result = ""
        return
    try:
        with db.begin_nested():
            db.add(
                ReachAiAction(
                    conversation_id=conversation.id,
                    dedupe_key=key,
                    category="human_wait",
                    title="Customer is waiting",
                    details=preview[:1000],
                    priority="normal",
                    confidence=0,
                    consequential=False,
                )
            )
            db.flush()
    except IntegrityError:
        return


def close_wait(db: Session, conversation_id) -> None:
    _close_wait(db, conversation_id)


def latest_staff_at(db: Session, conversation_id) -> datetime | None:
    """The latest real staff reply. A phone echo of the customer's own text does not count."""
    rows = db.scalars(
        select(ReachAiMessage)
        .where(ReachAiMessage.conversation_id == conversation_id, ReachAiMessage.author == "staff")
        .order_by(ReachAiMessage.created_at.desc())
    ).all()
    for row in rows:
        if row.direction != "out":
            continue
        echo = isinstance(row.evidence, dict) and row.evidence.get("origin") == "human_device"
        if echo and _copied_existing_text(db, conversation_id, row.body):
            continue
        return aware(row.created_at)
    return None


def _copied_existing_text(db: Session, conversation_id, body: str) -> bool:
    """True when this text is already a customer line or an AI reply. A phone echo is not a person."""
    folded = body.strip()
    if not folded:
        return False
    return (
        db.scalar(
            select(ReachAiMessage.id).where(
                ReachAiMessage.conversation_id == conversation_id,
                ReachAiMessage.author.in_(("customer", "ai")),
                ReachAiMessage.body == folded,
            )
        )
        is not None
    )


def staff_has_answered(staff_at: datetime | None, message_at: datetime) -> bool:
    """A person answered this line when their message is at least as new as the customer's."""
    return staff_at is not None and staff_at >= aware(message_at)


def reopen_unanswered(db: Session) -> None:
    """Put an unanswered customer line back where the idle checker can see it.

    The checker only reads status "received". A staff event used to mark every later
    customer line stored, so the fallback skipped it even after the person went idle.
    """
    waiting = db.scalars(
        select(ReachAiMessage).where(ReachAiMessage.author == "customer", ReachAiMessage.status == "stored")
    ).all()
    if not waiting:
        return
    answered = set(
        db.scalars(
            select(ReachAiMessage.reply_to_id).where(
                ReachAiMessage.reply_to_id.is_not(None),
                ReachAiMessage.status.notin_(("cancelled", "failed")),
            )
        ).all()
    )
    for message in waiting:
        if message.id in answered or message.body.startswith("A media message arrived."):
            continue
        conversation = db.get(ReachAiConversation, message.conversation_id)
        if conversation is None or conversation.status == "resolved":
            continue
        if staff_has_answered(latest_staff_at(db, conversation.id), message.created_at):
            continue
        soon = aware(message.created_at) + timedelta(minutes=2)
        bundled = db.scalar(
            select(ReachAiMessage.id).where(
                ReachAiMessage.conversation_id == message.conversation_id,
                ReachAiMessage.author == "ai",
                ReachAiMessage.direction == "out",
                ReachAiMessage.created_at >= message.created_at,
                ReachAiMessage.created_at <= soon,
            )
        )
        if bundled is not None:
            continue
        message.status = "received"


def suppress_pending(
    db: Session,
    conversation: ReachAiConversation,
    answered_through: datetime | None = None,
    *,
    reason: str = "staff_replied",
) -> None:
    """A staff reply wins the lines already waiting. Later customer lines stay open for the idle fallback."""
    waiting = (
        ReachAiMessage.conversation_id == conversation.id,
        ReachAiMessage.author == "customer",
        ReachAiMessage.status.in_(("received", "preparing")),
    )
    if answered_through is not None:
        waiting = (*waiting, ReachAiMessage.created_at <= answered_through)
    db.execute(update(ReachAiMessage).where(*waiting).values(status="stored"))
    queued = db.scalars(
        select(ReachAiMessage).where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.author == "ai",
            ReachAiMessage.status == "queued",
        )
    ).all()
    for message in queued:
        if message.outbound_message_id is None:
            message.status = "cancelled"
            message.reply_to_id = None
            continue
        outbound = db.get(OutboundMessage, message.outbound_message_id)
        if outbound is not None and outbound.status == "QUEUED":
            outbound.status = "SKIPPED"
            outbound.last_error = "A staff member replied first."
            message.status = "cancelled"
            message.reply_to_id = None
            trace(
                "ai_reply_suppressed",
                conversation_id=conversation.id,
                message_id=message.id,
                outbound_message_id=outbound.id,
                suppression_reason=reason,
                retry_count=outbound.attempts,
            )
        elif outbound is not None and outbound.status == "SENT":
            continue
    trace(
        "human_response_detected",
        conversation_id=conversation.id,
        suppression_reason=reason,
        elapsed_seconds=_elapsed(answered_through),
    )
    _close_wait(db, conversation.id)


def release_mirrored_takeover(db: Session, conversation: ReachAiConversation) -> bool:
    """A phone echo of the customer's own text is not a staff reply. Hand the chat back to the agent."""
    if conversation.handler != "human":
        return False
    staff = db.scalar(
        select(ReachAiMessage)
        .where(ReachAiMessage.conversation_id == conversation.id, ReachAiMessage.author == "staff")
        .order_by(ReachAiMessage.created_at.desc())
        .limit(1)
    )
    if staff is None or not isinstance(staff.evidence, dict) or staff.evidence.get("origin") != "human_device":
        return False
    if not _copied_existing_text(db, conversation.id, staff.body):
        return False
    conversation.handler = "ai"
    if conversation.status != "resolved":
        conversation.status = "waiting_staff"
    replied = set(
        db.scalars(
            select(ReachAiMessage.reply_to_id).where(
                ReachAiMessage.conversation_id == conversation.id,
                ReachAiMessage.reply_to_id.is_not(None),
                ReachAiMessage.status.notin_(("cancelled", "failed")),
            )
        ).all()
    )
    window_start = aware(staff.created_at) - timedelta(minutes=10)
    waiting = db.scalars(
        select(ReachAiMessage).where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.author == "customer",
            ReachAiMessage.status == "stored",
            ReachAiMessage.created_at >= window_start,
        )
    ).all()
    for item in waiting:
        if item.id not in replied:
            item.status = "received"
    return True


def claim(db: Session, messages: list[ReachAiMessage]) -> bool:
    ids = [message.id for message in messages]
    if not ids:
        return False
    result = db.execute(
        update(ReachAiMessage)
        .where(ReachAiMessage.id.in_(ids), ReachAiMessage.status == "received")
        .values(status="preparing")
    )
    db.flush()
    if result.rowcount != len(ids):
        db.execute(
            update(ReachAiMessage)
            .where(ReachAiMessage.id.in_(ids), ReachAiMessage.status == "preparing")
            .values(status="received")
        )
        db.flush()
        return False
    claimed_at = datetime.now(UTC).isoformat()
    for message in messages:
        db.refresh(message)
        evidence = dict(message.evidence or {})
        evidence["claimed_at"] = claimed_at
        message.evidence = evidence
    db.flush()
    return True


def recover_stuck(db: Session, *, stale_after: timedelta = timedelta(minutes=2)) -> None:
    """A claim left behind by a dead worker becomes eligible again. The customer text stays."""
    cutoff = datetime.now(UTC) - stale_after
    rows = db.scalars(select(ReachAiMessage).where(ReachAiMessage.status == "preparing")).all()
    for row in rows:
        raw = row.evidence.get("claimed_at") if isinstance(row.evidence, dict) else None
        anchor = _parsed_time(raw) or aware(row.created_at)
        if anchor >= cutoff:
            continue
        row.status = "received"
        if isinstance(row.evidence, dict) and "claimed_at" in row.evidence:
            evidence = dict(row.evidence)
            evidence.pop("claimed_at", None)
            row.evidence = evidence


def release_if_stale(db: Session, outbound: OutboundMessage) -> bool:
    """Drop an AI reply that must not leave the server. A message Evolution already accepted stays sent."""
    if outbound.template_key != "ai_agent" or outbound.status != "QUEUED":
        return False
    ai_message = db.scalar(select(ReachAiMessage).where(ReachAiMessage.outbound_message_id == outbound.id))
    if ai_message is None or ai_message.author != "ai":
        return False
    reason = _stale_reason(db, ai_message)
    if reason is None:
        return False
    outbound.status = "SKIPPED"
    outbound.last_error = reason[:500]
    parent_id = ai_message.reply_to_id
    parent = db.get(ReachAiMessage, parent_id) if parent_id is not None else None
    ai_message.status = "cancelled"
    ai_message.reply_to_id = None
    db.flush()
    if reason == "newer_customer_message" and parent is not None:
        _release_customer_lines(db, ai_message.conversation_id, parent.created_at)
    trace(
        "ai_reply_suppressed",
        conversation_id=ai_message.conversation_id,
        message_id=ai_message.id,
        outbound_message_id=outbound.id,
        suppression_reason=reason,
        retry_count=outbound.attempts,
    )
    return True


def _stale_reason(db: Session, ai_message: ReachAiMessage) -> str | None:
    conversation = db.get(ReachAiConversation, ai_message.conversation_id)
    if conversation is None:
        return None
    if conversation.status == "resolved":
        return "conversation_resolved"
    parent = db.get(ReachAiMessage, ai_message.reply_to_id) if ai_message.reply_to_id else None
    if conversation.handler != "ai":
        return "human_takeover"
    if parent is not None and staff_has_answered(latest_staff_at(db, conversation.id), parent.created_at):
        return "staff_replied"
    if parent is None:
        return None
    newer = db.scalar(
        select(ReachAiMessage.id).where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.author == "customer",
            ReachAiMessage.id != parent.id,
            ReachAiMessage.created_at > parent.created_at,
        )
    )
    if newer is not None:
        return "newer_customer_message"
    return None


def _release_customer_lines(db: Session, conversation_id, parent_created_at: datetime) -> None:
    """Put the lines from a cancelled draft back in the waiting set. Already-sent answers stay stored."""
    active = db.scalars(
        select(ReachAiMessage).where(
            ReachAiMessage.conversation_id == conversation_id,
            ReachAiMessage.author == "ai",
            ReachAiMessage.direction == "out",
            ReachAiMessage.status.notin_(("cancelled", "failed")),
        )
    ).all()
    customers = db.scalars(
        select(ReachAiMessage).where(
            ReachAiMessage.conversation_id == conversation_id,
            ReachAiMessage.author == "customer",
            ReachAiMessage.status == "stored",
            ReachAiMessage.created_at <= parent_created_at,
        )
    ).all()
    staff_at = latest_staff_at(db, conversation_id)
    for message in customers:
        if message.body.startswith("A media message arrived."):
            continue
        if staff_has_answered(staff_at, message.created_at):
            continue
        if any(aware(item.created_at) >= aware(message.created_at) for item in active):
            continue
        message.status = "received"


def _elapsed(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    return max(int((datetime.now(UTC) - aware(moment)).total_seconds()), 0)


def _parsed_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _stored_wait(value: object) -> int:
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 60
    if seconds < 5 or seconds > 600:
        return 60
    return seconds


def _wait(value: object) -> int:
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "invalid_wait", "Enter a wait from 5 seconds to 10 minutes.") from exc
    if seconds < 5 or seconds > 600:
        raise ApiError(422, "invalid_wait", "Enter a wait from 5 seconds to 10 minutes.")
    return seconds


def _close_wait(db: Session, conversation_id) -> None:
    rows = db.scalars(
        select(ReachAiAction).where(
            ReachAiAction.conversation_id == conversation_id,
            ReachAiAction.category == "human_wait",
            ReachAiAction.status == "needs_review",
        )
    ).all()
    for row in rows:
        row.status = "cancelled"
        row.result = "The response window closed."
