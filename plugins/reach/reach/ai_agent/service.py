"""Agent settings, grounded replies, and staff actions. Consequential work is never posted here."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.business_settings import BusinessSettings
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.messaging import OutboundMessage
from app.models.product import Product
from app.models.sale import Sale
from app.models.store import Store
from app.services.llm_context import ContextDocument, prepare_llm_context
from app.services.pricing import resolve_price
from reach.ai_agent.catalogue import pieces_requested, query_tokens, search_catalogue
from reach.ai_agent.hold import (
    aware,
    claim,
    close_wait,
    due,
    latest_staff_at,
    release_mirrored_takeover,
    reopen_unanswered,
    response_policy,
    staff_has_answered,
    suppress_pending,
    wait_seconds,
    write_policy,
)
from reach.ai_agent.models import (
    ReachAiAction,
    ReachAiAgent,
    ReachAiConversation,
    ReachAiEvent,
    ReachAiKnowledge,
    ReachAiMessage,
    ReachAiUsage,
)
from reach.ai_agent.reply import (
    CONSEQUENTIAL,
    accept_care_reply,
    action_for,
    care_turns,
    clock_tokens,
    compose,
    day_tokens,
    intent_of,
    is_hours_title,
    language_of,
    named_product,
    priority_for,
)

logger = logging.getLogger("axizreach.ai")
_CATALOGUE = frozenset({"product", "price", "stock", "list"})


def agent_row(db: Session) -> ReachAiAgent:
    found = db.scalar(select(ReachAiAgent).where(ReachAiAgent.slot == "default"))
    if found is not None:
        return found
    created = ReachAiAgent(slot="default")
    db.add(created)
    db.flush()
    return created


def present_agent(db: Session, row: ReachAiAgent) -> dict:
    policy = response_policy(db)
    return {
        "id": str(row.id),
        "enabled": row.enabled,
        "mode": row.mode,
        "name": row.name,
        "greeting": row.greeting,
        "language": row.language,
        "tone": row.tone,
        "instructions": row.instructions,
        "product_help": row.product_help,
        "order_help": row.order_help,
        "action_detection": row.action_detection,
        "handoff": row.handoff,
        "response_priority": policy["response_priority"],
        "human_wait_seconds": policy["human_wait_seconds"],
        "notify_staff": policy["notify_staff"],
    }


def save_agent(db: Session, payload: dict) -> dict:
    row = agent_row(db)
    for key in ("name", "greeting", "language", "tone", "instructions", "mode"):
        if key in payload and payload[key] is not None:
            setattr(row, key, payload[key])
    for key in ("product_help", "order_help", "action_detection", "handoff"):
        if key in payload and payload[key] is not None:
            setattr(row, key, bool(payload[key]))
    if row.mode not in {"assist", "hybrid", "autonomous"}:
        raise ApiError(422, "invalid_mode", "Choose assist, hybrid, or autonomous.")
    if row.language not in {"auto", "en", "ar"}:
        raise ApiError(422, "invalid_language", "Choose auto, en, or ar.")
    write_policy(db, payload)
    db.commit()
    return present_agent(db, row)


def set_enabled(db: Session, enabled: bool) -> dict:
    row = agent_row(db)
    row.enabled = enabled
    db.add(ReachAiEvent(kind="agent_enabled" if enabled else "agent_disabled", detail=""))
    db.commit()
    return present_agent(db, row)


def add_knowledge(db: Session, kind: str, title: str, body: str) -> dict:
    if kind not in {"faq", "instruction"}:
        raise ApiError(422, "invalid_knowledge", "Knowledge must be an FAQ or an instruction.")
    row = ReachAiKnowledge(kind=kind, title=title.strip()[:160], body=body.strip()[:8000], status="ready")
    if not row.title or not row.body:
        raise ApiError(422, "invalid_knowledge", "A title and text are required.")
    db.add(row)
    db.commit()
    return _knowledge(row)


def list_knowledge(db: Session) -> list[dict]:
    rows = db.scalars(
        select(ReachAiKnowledge)
        .where(ReachAiKnowledge.kind != "policy")
        .order_by(ReachAiKnowledge.created_at.desc())
    ).all()
    conflicting = _conflicting_hours(rows)
    return [_knowledge(row, row.id in conflicting) for row in rows]


def delete_knowledge(db: Session, knowledge_id) -> None:
    row = db.get(ReachAiKnowledge, knowledge_id)
    if row is None:
        raise ApiError(404, "not_found", "Knowledge item not found.")
    db.delete(row)
    db.commit()


def _knowledge(row: ReachAiKnowledge, conflict: bool = False) -> dict:
    updated = row.updated_at.isoformat() if row.updated_at is not None else None
    return {
        "id": str(row.id),
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "status": row.status,
        "source": "approved_answer",
        "conflict": conflict,
        "updated_at": updated,
    }


def _hour_signature(body: str) -> tuple:
    clocks = frozenset(clock_tokens(body))
    days = frozenset(day_tokens(body))
    if clocks or days:
        return (clocks, days)
    return (body.strip().casefold(),)


def _conflicting_hours(rows: list[ReachAiKnowledge]) -> set:
    """Approved hour answers that do not state the same days and times."""
    hours = [row for row in rows if row.kind == "faq" and row.status == "ready" and is_hours_title(row.title)]
    signatures = {_hour_signature(row.body) for row in hours}
    if len(hours) < 2 or len(signatures) < 2:
        return set()
    return {row.id for row in hours}


def list_conversations(db: Session, status: str | None, handler: str | None) -> list[dict]:
    policy = response_policy(db)
    query = select(ReachAiConversation).order_by(ReachAiConversation.last_message_at.desc())
    if status:
        query = query.where(ReachAiConversation.status == status)
    if handler:
        query = query.where(ReachAiConversation.handler == handler)
    return [_conversation(row, policy) for row in db.scalars(query.limit(100)).all()]


def conversation_detail(db: Session, conversation_id) -> dict:
    row = _owned(db, conversation_id)
    _sync_delivery(db)
    messages = db.scalars(
        select(ReachAiMessage).where(ReachAiMessage.conversation_id == row.id).order_by(ReachAiMessage.created_at)
    ).all()
    actions = db.scalars(select(ReachAiAction).where(ReachAiAction.conversation_id == row.id)).all()
    return {
        "conversation": _conversation(row, response_policy(db)),
        "customer": _customer_card(db, row),
        "messages": [_message(item) for item in messages],
        "actions": [_action(item) for item in actions],
        "events": [_event(item) for item in _events(db, row.id)],
    }


def staff_reply(db: Session, conversation_id, body: str, user_id) -> dict:
    row = _owned(db, conversation_id)
    text = body.strip()
    if not text:
        raise ApiError(422, "empty_reply", "Write a message before sending.")
    row.handler = "human"
    row.status = "waiting_customer"
    if user_id:
        row.assigned_user_id = user_id
    answered_at = datetime.now(UTC)
    suppress_pending(db, row, answered_at)
    message = _queue_reply(db, row, text, author="staff", reply_to=None)
    db.add(ReachAiEvent(conversation_id=row.id, kind="staff_reply", detail=str(user_id or "")))
    db.commit()
    return _message(message)


def takeover(db: Session, conversation_id, user_id) -> dict:
    return _handler(db, conversation_id, "human", "waiting_staff", "takeover", user_id)


def resume(db: Session, conversation_id, user_id) -> dict:
    return _handler(db, conversation_id, "ai", "open", "resume", user_id)


def assign(db: Session, conversation_id, user_id) -> dict:
    row = _owned(db, conversation_id)
    row.assigned_user_id = user_id
    db.add(ReachAiEvent(conversation_id=row.id, kind="assigned", detail=str(user_id)))
    db.commit()
    return _conversation(row)


def resolve(db: Session, conversation_id, user_id) -> dict:
    row = _owned(db, conversation_id)
    row.status = "resolved"
    row.handler = "human"
    db.add(ReachAiEvent(conversation_id=row.id, kind="resolved", detail=str(user_id or "")))
    db.commit()
    return _conversation(row)


def add_note(db: Session, conversation_id, body: str, user_id) -> dict:
    row = _owned(db, conversation_id)
    text = body.strip()
    if not text:
        raise ApiError(422, "empty_note", "Write a note first.")
    message = ReachAiMessage(
        conversation_id=row.id, direction="note", author="staff", body=text[:4000], status="stored"
    )
    db.add(message)
    db.add(ReachAiEvent(conversation_id=row.id, kind="note", detail=str(user_id or "")))
    db.commit()
    return _message(message)


def list_actions(db: Session, status: str | None) -> list[dict]:
    query = select(ReachAiAction).order_by(ReachAiAction.created_at.desc())
    if status:
        query = query.where(ReachAiAction.status == status)
    return [_action(row) for row in db.scalars(query.limit(100)).all()]


def set_action_status(db: Session, action_id, status: str, user_id) -> dict:
    row = db.get(ReachAiAction, action_id)
    if row is None:
        raise ApiError(404, "not_found", "Action not found.")
    if status not in {"approved", "rejected"}:
        raise ApiError(422, "invalid_status", "Choose approved or rejected.")
    row.status = status
    db.add(ReachAiEvent(conversation_id=row.conversation_id, action_id=row.id, kind=status, detail=str(user_id or "")))
    db.commit()
    return _action(row)


def execute_action(db: Session, action_id, user_id) -> dict:
    """Marks a reviewed follow-up complete. Refunds, cancellations, and reservations stay unposted."""
    row = db.get(ReachAiAction, action_id)
    if row is None:
        raise ApiError(404, "not_found", "Action not found.")
    if row.status != "approved":
        raise ApiError(409, "not_approved", "Approve the action before completing it.")
    if row.consequential or row.category in CONSEQUENTIAL:
        raise ApiError(
            422,
            "approval_only",
            "This request stays with staff. The agent does not post refunds, cancellations, or reservations.",
        )
    row.status = "completed"
    row.result = "Marked complete by staff. No sale, refund, or stock document was created."
    db.add(
        ReachAiEvent(
            conversation_id=row.conversation_id,
            action_id=row.id,
            kind="completed",
            detail=str(user_id or ""),
        )
    )
    db.commit()
    return _action(row)


def preview(db: Session, settings: Settings, text: str) -> dict:
    """Answers from current records without sending a WhatsApp message or opening a conversation."""
    agent = agent_row(db)
    intent, score = intent_of(text)
    language = language_of(text, agent.language)
    facts = gather_facts(db, text, intent)
    try:
        document = _prompt_document(text, intent, language, facts, response_policy(db), human_handling=False)
    except Exception:
        logger.exception("[AXIZREACH_AI] context_failed")
        document = None
    reply, provider = _draft(settings, agent, intent, language, facts, document, customer_text=text)
    return {
        "intent": intent,
        "confidence": score,
        "language": language,
        "reply": reply,
        "provider": provider,
        "sent": False,
        "matches": [{"name": row["name"]} for row in facts.get("products") or []],
        "spelling": facts.get("spelling") or [],
        "context": document.public(),
    }


def health(db: Session, settings: Settings) -> dict:
    """Counts and timestamps only. Message text, phone numbers, and credentials stay out."""
    from app.models.scheduled_job import ScheduledJob
    from reach.models import ReachConnection

    agent = agent_row(db)
    job = db.scalar(select(ScheduledJob).where(ScheduledJob.name == "reach_ai_replies"))
    connection_rows = db.scalars(select(ReachConnection.status)).all()
    connections: dict[str, int] = {}
    for status in connection_rows:
        connections[status] = connections.get(status, 0) + 1

    def messages(status: str | None = None, author: str | None = None) -> int:
        query = select(func.count()).select_from(ReachAiMessage)
        if status is not None:
            query = query.where(ReachAiMessage.status == status)
        if author is not None:
            query = query.where(ReachAiMessage.author == author)
        return int(db.scalar(query) or 0)

    oldest = db.scalar(
        select(func.min(ReachAiMessage.created_at)).where(
            ReachAiMessage.author == "customer",
            ReachAiMessage.status == "received",
        )
    )
    oldest_seconds = None
    if oldest is not None:
        oldest_seconds = max(int((datetime.now(UTC) - aware(oldest)).total_seconds()), 0)
    outbound_queued = int(
        db.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(OutboundMessage.template_key == "ai_agent", OutboundMessage.status == "QUEUED")
        )
        or 0
    )
    outbound_failed = int(
        db.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(OutboundMessage.template_key == "ai_agent", OutboundMessage.status == "FAILED")
        )
        or 0
    )
    finished = None if job is None or job.last_finished_at is None else job.last_finished_at.isoformat()
    return {
        "enabled": agent.enabled,
        "mode": agent.mode,
        "whatsapp": connections,
        "llm_provider": settings.assistant_provider,
        "worker": {
            "last_status": None if job is None else job.last_status,
            "last_finished_at": finished,
            "run_count": 0 if job is None else job.run_count,
        },
        "incoming": messages(author="customer"),
        "pending": messages("received", "customer"),
        "processing": messages("preparing"),
        "ai_replies": messages(author="ai"),
        "queued": messages("queued"),
        "sent": messages("sent"),
        "failed": messages("failed"),
        "outbound_queued": outbound_queued,
        "outbound_failed": outbound_failed,
        "human_takeover": int(
            db.scalar(
                select(func.count())
                .select_from(ReachAiConversation)
                .where(ReachAiConversation.handler == "human", ReachAiConversation.status != "resolved")
            )
            or 0
        ),
        "oldest_unanswered_seconds": oldest_seconds,
    }


def analytics(db: Session) -> dict:
    conversations = db.scalar(select(func.count()).select_from(ReachAiConversation)) or 0
    waiting = db.scalar(
        select(func.count())
        .select_from(ReachAiConversation)
        .where(ReachAiConversation.handler == "human", ReachAiConversation.status != "resolved")
    ) or 0
    actions = db.scalar(
        select(func.count()).select_from(ReachAiAction).where(ReachAiAction.status == "needs_review")
    ) or 0
    replies = db.scalar(select(func.count()).select_from(ReachAiUsage)) or 0
    return {"conversations": conversations, "human_handling": waiting, "actions_waiting": actions, "replies": replies}


def _recover_stuck(db: Session) -> None:
    """A reply that was claimed and never finished is waited on again. The customer message stays."""
    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    db.execute(
        update(ReachAiMessage)
        .where(ReachAiMessage.status == "preparing", ReachAiMessage.created_at < cutoff)
        .values(status="received")
    )


def process_pending(db: Session, settings: Settings, limit: int = 20) -> str:
    _recover_stuck(db)
    _sync_delivery(db)
    agent = agent_row(db)
    if not agent.enabled:
        return "agent is off"
    policy = response_policy(db)
    if policy["response_priority"] == "human_only":
        return "human only"
    held = db.scalars(
        select(ReachAiConversation).where(
            ReachAiConversation.handler == "human",
            ReachAiConversation.status != "resolved",
        )
    ).all()
    for conversation in held:
        if release_mirrored_takeover(db, conversation):
            logger.info("[AXIZREACH_AI] mirrored_takeover_released")
    reopen_unanswered(db)
    db.flush()
    pending = db.scalars(
        select(ReachAiMessage)
        .where(ReachAiMessage.status == "received", ReachAiMessage.author == "customer")
        .order_by(ReachAiMessage.created_at)
        .limit(max(limit, 100))
    ).all()
    batches: dict = {}
    for incoming in pending:
        batches.setdefault(incoming.conversation_id, []).append(incoming)
    sent = 0
    failed = 0
    for batch in batches.values():
        try:
            with db.begin_nested():
                if _reply_to_batch(db, settings, agent, policy, batch):
                    sent += 1
        except Exception:
            failed += 1
            logger.exception("[AXIZREACH_AI] reply_failed")
    if failed:
        return f"{sent} replies prepared; {failed} conversations failed"
    return f"{sent} replies prepared"


def gather_facts(db: Session, text: str, intent: str, conversation: ReachAiConversation | None = None) -> dict:
    settings_row = db.scalar(select(BusinessSettings).limit(1))
    currency = settings_row.currency if settings_row is not None else ""
    facts: dict = {
        "currency": currency,
        "products": [],
        "branches": [],
        "hours": None,
        "spelling": [],
        "truncated": False,
        "all_ids": [],
        "offset": 0,
        "named_query": named_product(text),
    }
    if intent == "hours":
        rows = db.scalars(
            select(ReachAiKnowledge).where(ReachAiKnowledge.kind == "faq", ReachAiKnowledge.status == "ready")
        ).all()
        hours = [row for row in rows if is_hours_title(row.title)]
        if len(_conflicting_hours(hours)) > 1:
            facts["hours_conflict"] = True
        elif hours:
            preferred = next((row for row in hours if row.title.casefold().strip() == "opening hours"), hours[0])
            facts["hours"] = preferred.body.strip()[:500]
    if intent == "branch":
        stores = db.scalars(
            select(Store).where(Store.is_active.is_(True), Store.is_warehouse.is_(False)).limit(8)
        ).all()
        facts["branches"] = [{"name": store.name, "address": store.address} for store in stores]
    if intent in _CATALOGUE:
        prior_ids, prior_offset = _prior_products(db, conversation)
        started = time.perf_counter()
        found = search_catalogue(db, _catalogue_text(db, conversation, text), prior_ids, prior_offset)
        catalogue_ms = int((time.perf_counter() - started) * 1000)
        pieces = pieces_requested(text)
        include_stock = intent == "stock"
        priced = time.perf_counter()
        for product in found["products"]:
            facts["products"].append(
                _product_fact(db, product, currency, include_stock=include_stock, pieces=pieces)
            )
        lookup_ms = int((time.perf_counter() - priced) * 1000)
        facts["spelling"] = found["spelling"]
        facts["truncated"] = found["truncated"]
        facts["all_ids"] = [str(item) for item in found["all_ids"]]
        facts["offset"] = found["offset"]
        logger.info(
            "[AXIZREACH_AI] intent=%s catalogue_search_ms=%s product_match_count=%s "
            "price_lookup_ms=%s stock_lookup_ms=%s",
            intent,
            catalogue_ms,
            len(facts["products"]),
            0 if include_stock else lookup_ms,
            lookup_ms if include_stock else 0,
        )
    return facts


def _prompt_document(
    text: str, intent: str, language: str, facts: dict, policy: dict, *, human_handling: bool
) -> ContextDocument:
    messages = [part.strip() for part in text.splitlines() if part.strip()]
    rows = []
    for row in facts.get("products") or []:
        item = {"product_id": str(row.get("id") or ""), "name": row["name"], "price": row["price"]}
        if intent == "stock":
            stock = row.get("stock")
            item["availability"] = "unconfirmed" if stock is None else "confirmed"
            item["available_quantity"] = stock
        rows.append(item)
    return prepare_llm_context(
        {
            "conversation": {
                "tenant_context": "authorized_current_tenant",
                "response_mode": policy["response_priority"],
                "human_handling": human_handling,
                "pending_customer_messages": messages,
                "language": language,
            },
            "response_context": {
                "priority": policy["response_priority"],
                "response_window_seconds": policy["human_wait_seconds"],
                "human_replied": human_handling,
                "human_takeover_active": human_handling,
                "ai_fallback_enabled": policy["response_priority"] != "human_only",
            },
            "matched_products": rows,
            "approved_faq": facts.get("hours"),
        }
    )


def _evidence(intent: str, provider: str, facts: dict) -> dict:
    return {
        "intent": intent,
        "provider": provider,
        "product_ids": facts.get("all_ids") or [],
        "offset": facts.get("offset") or 0,
    }


def _catalogue_text(db: Session, conversation: ReachAiConversation | None, text: str) -> str:
    """A short follow-up such as "256 GB" is searched with the earlier product the customer named."""
    if conversation is None or len(query_tokens(text)) >= 3:
        return text
    earlier = db.scalars(
        select(ReachAiMessage)
        .where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.author == "customer",
        )
        .order_by(ReachAiMessage.created_at.desc())
        .limit(6)
    ).all()
    for row in earlier:
        if row.body.strip() == text.strip():
            continue
        if len(query_tokens(row.body)) >= 2:
            return f"{row.body}\n{text}"
    return text


def _prior_products(db: Session, conversation: ReachAiConversation | None) -> tuple[list[str], int]:
    if conversation is None:
        return [], 0
    message = db.scalar(
        select(ReachAiMessage)
        .where(ReachAiMessage.conversation_id == conversation.id, ReachAiMessage.direction == "out")
        .order_by(ReachAiMessage.created_at.desc())
        .limit(1)
    )
    if message is None or not isinstance(message.evidence, dict):
        return [], 0
    ids = [str(item) for item in message.evidence.get("product_ids") or []]
    offset = int(message.evidence.get("offset") or 0)
    return ids, offset


def _product_fact(db: Session, product: Product, currency: str, *, include_stock: bool, pieces: int) -> dict:
    checked = None
    available = None
    if include_stock:
        levels = db.scalars(select(InventoryLevel).where(InventoryLevel.product_id == product.id)).all()
        if levels:
            available = sum(max(level.quantity_on_hand - level.quantity_reserved, 0) for level in levels)
            latest = max((level.updated_at for level in levels if level.updated_at is not None), default=None)
            checked = latest.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if latest is not None else None
    cents = resolve_price(product.price_cents, product.prices or [], "RETAIL", pieces).price_cents
    return {
        "id": str(product.id),
        "name": product.name,
        "price": f"{cents // 100}.{cents % 100:02d} {currency}".strip(),
        "stock": available,
        "checked_at": checked,
    }


def _reply_to_batch(db: Session, settings: Settings, agent: ReachAiAgent, policy: dict, batch: list) -> bool:
    newest = max(batch, key=lambda item: aware(item.created_at))
    conversation = db.scalar(
        select(ReachAiConversation).where(ReachAiConversation.id == newest.conversation_id).with_for_update()
    )
    if conversation is not None and release_mirrored_takeover(db, conversation):
        logger.info("[AXIZREACH_AI] mirrored_takeover_released")
    if conversation is None or conversation.status == "resolved":
        for item in batch:
            item.status = "stored"
        return False
    staff_at = latest_staff_at(db, conversation.id)
    if staff_has_answered(staff_at, newest.created_at):
        for item in batch:
            if staff_has_answered(staff_at, item.created_at):
                item.status = "stored"
        return False
    if conversation.handler != "ai":
        # A person at the phone still has the chat. Leave the customer line received so the
        # idle wait can answer it. Marking it stored here made the fallback skip it forever.
        if policy["response_priority"] != "human_first" or not due(newest.created_at, policy):
            return False
        conversation.handler = "ai"
        conversation.status = "waiting_staff"
        db.add(
            ReachAiEvent(
                conversation_id=conversation.id,
                kind="idle_fallback",
                detail="Staff were idle, so the assistant answered.",
            )
        )
        logger.info("[AXIZREACH_AI] idle_fallback")
    if not due(newest.created_at, policy):
        return False
    if not claim(db, batch):
        return False
    for item in batch:
        db.refresh(item)
    db.refresh(conversation)
    held = conversation.handler != "ai" or conversation.status == "resolved"
    if any(item.status != "preparing" for item in batch) or held:
        for item in batch:
            if item.status == "preparing":
                item.status = "received"
        return False
    text = "\n".join(item.body for item in batch)
    sent = _reply_to_incoming(db, settings, agent, newest, text)
    for item in batch:
        db.refresh(item)
        if item.status == "preparing":
            item.status = "stored" if sent else "received"
    return sent


def _reply_to_incoming(
    db: Session, settings: Settings, agent: ReachAiAgent, incoming: ReachAiMessage, text: str | None = None
) -> bool:
    body = text or incoming.body
    if db.scalar(select(ReachAiMessage.id).where(ReachAiMessage.reply_to_id == incoming.id)):
        incoming.status = "stored"
        return False
    conversation = db.get(ReachAiConversation, incoming.conversation_id)
    if conversation is None:
        incoming.status = "stored"
        return False
    db.refresh(conversation)
    if conversation.handler != "ai" or conversation.status == "resolved":
        incoming.status = "stored"
        suppress_pending(db, conversation)
        return False
    started = time.monotonic()
    prior_intent = conversation.intent
    intent, score = intent_of(body)
    if intent == "unknown" and prior_intent == "hours":
        intent = "hours"
    language = language_of(body, agent.language)
    conversation.language = language
    conversation.intent = intent
    lookup = "unknown" if intent in _CATALOGUE and not agent.product_help else intent
    facts = gather_facts(db, body, lookup, conversation)
    if intent == "hours" and (prior_intent == "hours" or "visit" in body.casefold()):
        facts["hours_followup"] = True
    if facts.get("hours_conflict"):
        _open_action(
            db,
            conversation,
            incoming,
            "hours_conflict",
            "hours",
            "Approved opening hours disagree.",
            90,
        )
    if intent in _CATALOGUE and not agent.product_help:
        facts = {**facts, "products": []}
    try:
        document = _prompt_document(body, intent, language, facts, response_policy(db), human_handling=False)
    except Exception:
        logger.exception("[AXIZREACH_AI] context_failed")
        document = None
    reply, provider = _draft(
        settings,
        agent,
        intent,
        language,
        facts,
        document,
        customer_text=body,
        history=_recent_history(db, conversation.id, incoming.id),
    )
    category = action_for(intent) if agent.action_detection else None
    if category and not (intent in {"order", "warranty", "repair"} and not agent.order_help):
        _open_action(db, conversation, incoming, category, intent, body, score)
    handoff = agent.handoff and intent in {"human", "refund", "complaint", "cancellation"}
    db.refresh(conversation)
    db.refresh(incoming)
    if conversation.handler != "ai" or incoming.status not in {"preparing", "received"}:
        incoming.status = "stored"
        return False
    newer = db.scalar(
        select(ReachAiMessage.id).where(
            ReachAiMessage.conversation_id == conversation.id,
            ReachAiMessage.author == "customer",
            ReachAiMessage.id != incoming.id,
            ReachAiMessage.created_at > incoming.created_at,
            ReachAiMessage.status.in_(("received", "preparing")),
        )
    )
    if newer is not None:
        logger.info("[AXIZREACH_AI] stale_context_discarded")
        incoming.status = "received"
        return False
    if agent.mode == "assist":
        db.add(
            ReachAiMessage(
                conversation_id=conversation.id,
                reply_to_id=incoming.id,
                direction="out",
                author="ai",
                body=reply,
                status="suggested",
                evidence={**_evidence(intent, provider, facts), "origin": "ai_agent"},
            )
        )
        incoming.status = "stored"
        _usage(db, conversation.id, "suggestion", provider, started)
        return False
    queued = _queue_reply(
        db,
        conversation,
        reply,
        author="ai",
        reply_to=incoming.id,
        evidence={**_evidence(intent, provider, facts), "origin": "ai_agent"},
    )
    if queued is None:
        incoming.status = "stored"
        return False
    incoming.status = "stored"
    if handoff and agent.handoff:
        conversation.handler = "human"
        conversation.status = "escalated"
        conversation.priority = priority_for(intent, body)
        db.add(ReachAiEvent(conversation_id=conversation.id, kind="handoff", detail=intent))
    else:
        conversation.status = "waiting_customer"
        db.add(ReachAiEvent(conversation_id=conversation.id, kind="ai_reply", detail=""))
    close_wait(db, conversation.id)
    incoming.status = "stored"
    _usage(db, conversation.id, "reply", provider, started)
    return True


def _recent_history(db: Session, conversation_id, current_id) -> list[dict]:
    rows = db.scalars(
        select(ReachAiMessage)
        .where(ReachAiMessage.conversation_id == conversation_id, ReachAiMessage.id != current_id)
        .order_by(ReachAiMessage.created_at.desc())
        .limit(6)
    ).all()
    prior = []
    for row in reversed(rows):
        if row.author not in {"customer", "ai", "staff"} or not row.body:
            continue
        prior.append({"author": row.author, "body": row.body})
    return prior


def _draft(
    settings: Settings,
    agent: ReachAiAgent,
    intent: str,
    language: str,
    facts: dict,
    document: ContextDocument | None = None,
    *,
    customer_text: str = "",
    history: list[dict] | None = None,
) -> tuple[str, str]:
    template = compose(intent, language, agent.greeting, facts)
    # Built-in mode has no model. Ollama is the configured customer-care model.
    if settings.assistant_provider != "ollama":
        return template, "template"
    turns = care_turns(customer_text or template, language, template, history or [], agent.instructions)
    try:
        from app.services.assistant_llm import complete

        result = complete(settings, turns, [], mode="chat")
    except Exception:
        logger.info("[AXIZREACH_AI] model_unavailable")
        return template, "fallback"
    accepted = accept_care_reply(str(result.get("content") or ""), template, intent)
    if accepted is None:
        logger.info("[AXIZREACH_AI] model_reply_rejected")
        return template, "fallback"
    return accepted, f"ollama:{settings.ollama_model}"


def _open_action(
    db: Session,
    conversation: ReachAiConversation,
    incoming: ReachAiMessage,
    category: str,
    intent: str,
    text: str,
    score: int,
) -> None:
    key = f"{conversation.id}:{category}"[:80]
    existing = select(ReachAiAction.id).where(
        ReachAiAction.dedupe_key == key,
        ReachAiAction.status.notin_(("completed", "rejected", "cancelled")),
    )
    if db.scalar(existing):
        return
    try:
        with db.begin_nested():
            db.add(
                ReachAiAction(
                    conversation_id=conversation.id,
                    message_id=incoming.id,
                    dedupe_key=key,
                    category=category,
                    title=category.replace("_", " "),
                    details=text[:1000],
                    priority=priority_for(intent, text),
                    confidence=score,
                    consequential=category in CONSEQUENTIAL,
                )
            )
            db.flush()
    except IntegrityError:
        return


def _queue_reply(
    db: Session,
    conversation: ReachAiConversation,
    text: str,
    *,
    author: str,
    reply_to,
    evidence: dict | None = None,
) -> ReachAiMessage | None:
    if author == "ai":
        db.refresh(conversation)
        if conversation.handler != "ai" or conversation.status == "resolved":
            return None
    origin = "ai_agent" if author == "ai" else "human_staff"
    outbound = OutboundMessage(
        channel="whatsapp",
        to_address=conversation.phone,
        customer_id=conversation.customer_id,
        template_key="ai_agent",
        body=text,
        status="QUEUED",
        dedupe_key=None if reply_to is None else f"ai-reply:{reply_to}",
        context={"purpose": "customer_care", "origin": origin},
    )
    db.add(outbound)
    db.flush()
    message = ReachAiMessage(
        conversation_id=conversation.id,
        reply_to_id=reply_to,
        direction="out",
        author=author,
        body=text,
        outbound_message_id=outbound.id,
        status="queued",
        evidence={**(evidence or {}), "origin": origin},
    )
    db.add(message)
    conversation.last_preview = text[:180]
    conversation.last_message_at = datetime.now(UTC)
    return message


def _handler(db: Session, conversation_id, handler: str, status: str, kind: str, user_id) -> dict:
    row = _owned(db, conversation_id)
    row.handler = handler
    row.status = status
    if user_id and handler == "human":
        row.assigned_user_id = user_id
    if handler == "human":
        suppress_pending(db, row)
    db.add(ReachAiEvent(conversation_id=row.id, kind=kind, detail=str(user_id or "")))
    db.commit()
    return _conversation(row)


def _owned(db: Session, conversation_id) -> ReachAiConversation:
    row = db.get(ReachAiConversation, conversation_id)
    if row is None:
        raise ApiError(404, "not_found", "Conversation not found.")
    return row


def _sync_delivery(db: Session) -> None:
    rows = db.scalars(select(ReachAiMessage).where(ReachAiMessage.status == "queued")).all()
    for message in rows:
        if message.outbound_message_id is None:
            continue
        outbound = db.get(OutboundMessage, message.outbound_message_id)
        if outbound is None:
            continue
        if outbound.status == "SENT":
            message.status = "sent"
        elif outbound.status in {"FAILED", "SKIPPED"}:
            message.status = "failed"


def _usage(db: Session, conversation_id, kind: str, provider: str, started: float) -> None:
    db.add(
        ReachAiUsage(
            conversation_id=conversation_id,
            kind=kind,
            provider=provider[:40],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    )


def _conversation(row: ReachAiConversation, policy: dict | None = None) -> dict:
    fallback_at = None
    if policy and row.handler == "ai" and row.status == "waiting_staff" and row.last_message_at is not None:
        fallback_at = (aware(row.last_message_at) + timedelta(seconds=wait_seconds(policy))).isoformat()
    return {
        "id": str(row.id),
        "phone": row.phone,
        "customer_name": row.customer_name,
        "customer_id": None if row.customer_id is None else str(row.customer_id),
        "status": row.status,
        "handler": row.handler,
        "priority": row.priority,
        "language": row.language,
        "intent": row.intent,
        "unread_count": row.unread_count,
        "last_preview": row.last_preview,
        "last_message_at": None if row.last_message_at is None else row.last_message_at.isoformat(),
        "assigned_user_id": None if row.assigned_user_id is None else str(row.assigned_user_id),
        "fallback_at": fallback_at,
    }


def _events(db: Session, conversation_id) -> list[ReachAiEvent]:
    return list(
        db.scalars(
            select(ReachAiEvent)
            .where(ReachAiEvent.conversation_id == conversation_id)
            .order_by(ReachAiEvent.created_at)
        ).all()
    )


def _event(row: ReachAiEvent) -> dict:
    return {"kind": row.kind, "detail": row.detail, "created_at": row.created_at.isoformat()}


def _message(row: ReachAiMessage) -> dict:
    return {
        "id": str(row.id),
        "direction": row.direction,
        "author": row.author,
        "body": row.body,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "evidence": row.evidence or {},
    }


def _action(row: ReachAiAction) -> dict:
    return {
        "id": str(row.id),
        "conversation_id": str(row.conversation_id),
        "category": row.category,
        "title": row.title,
        "details": row.details,
        "priority": row.priority,
        "confidence": row.confidence,
        "status": row.status,
        "consequential": row.consequential,
        "result": row.result,
    }


def _customer_card(db: Session, row: ReachAiConversation) -> dict:
    if row.customer_id is None:
        return {"matched": False, "name": row.customer_name, "phone": row.phone}
    customer = db.get(Customer, row.customer_id)
    if customer is None:
        return {"matched": False, "name": row.customer_name, "phone": row.phone}
    purchases = db.scalar(
        select(func.coalesce(func.sum(Sale.total_cents), 0)).where(Sale.customer_id == customer.id)
    ) or 0
    last = db.scalar(select(func.max(Sale.created_at)).where(Sale.customer_id == customer.id))
    return {
        "matched": True,
        "name": customer.company_name or customer.name,
        "phone": customer.phone or row.phone,
        "customer_since": customer.created_at.isoformat(),
        "purchase_total_cents": int(purchases),
        "last_purchase_at": None if last is None else last.isoformat(),
        "balance_cents": customer.current_balance_cents,
    }
