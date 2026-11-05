"""Human-first waiting window. Settings live in an existing knowledge row, so no new table is required."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.messaging import OutboundMessage
from reach.ai_agent.models import ReachAiAction, ReachAiConversation, ReachAiEvent, ReachAiKnowledge, ReachAiMessage

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


def note_customer_waiting(db: Session, conversation: ReachAiConversation, preview: str, policy: dict) -> None:
    if conversation.handler != "ai" or policy["response_priority"] not in {"human_first", "human_only"}:
        return
    conversation.status = "waiting_staff"
    latest = db.scalar(
        select(ReachAiEvent)
        .where(ReachAiEvent.conversation_id == conversation.id)
        .order_by(ReachAiEvent.created_at.desc())
        .limit(1)
    )
    if latest is not None and latest.kind == "waiting_human":
        return
    db.add(
        ReachAiEvent(
            conversation_id=conversation.id,
            kind="waiting_human",
            detail=f"Staff have {wait_seconds(policy)} seconds before an AI reply.",
        )
    )
    if not policy.get("notify_staff", True):
        return
    key = f"wait:{conversation.id}"[:80]
    existing = db.scalar(
        select(ReachAiAction.id).where(
            ReachAiAction.dedupe_key == key,
            ReachAiAction.status.notin_(("completed", "rejected", "cancelled")),
        )
    )
    if existing is not None:
        return
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


def close_wait(db: Session, conversation_id) -> None:
    _close_wait(db, conversation_id)


def suppress_pending(db: Session, conversation: ReachAiConversation) -> None:
    """A staff reply wins. Pending customer messages are closed and unsent AI outbox rows are skipped."""
    db.execute(
        update(ReachAiMessage)
        .where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.status.in_(("received", "preparing")),
        )
        .values(status="stored")
    )
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
            continue
        outbound = db.get(OutboundMessage, message.outbound_message_id)
        if outbound is not None and outbound.status == "QUEUED":
            outbound.status = "SKIPPED"
            outbound.last_error = "A staff member replied first."
            message.status = "cancelled"
    _close_wait(db, conversation.id)


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
    return result.rowcount == len(ids)


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
