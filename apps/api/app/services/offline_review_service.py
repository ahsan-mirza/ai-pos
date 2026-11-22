"""Lost-terminal and conflict-adjustment requests.

A decision does not release a reservation, write off stock, or post a journal.
The original sync conflict is not rewritten.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.offline_review import ConflictAdjustmentRequest, LostTerminalRequest
from app.services import audit

POSTING = "awaiting_approval"


def _user(principal: Principal) -> uuid.UUID:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user.id


def _store(principal: Principal, store_id: uuid.UUID) -> uuid.UUID:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_forbidden", "That branch is outside this sign-in.")
    return store_id


def _bind(db: Session, principal: Principal, store_id: uuid.UUID) -> uuid.UUID:
    """Bind the branch this sign-in is allowed to use. An empty store still matches nothing."""
    store = _store(principal, store_id)
    from app.tenancy.scoping import bind_request_scope

    bind_request_scope(db, store, None)
    return store


def submit_lost_terminal(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    device_id: uuid.UUID,
    allocation_id: uuid.UUID | None,
    last_sequence: int,
    quantity: int,
    reason: str,
    evidence: str,
    idempotency_key: str,
) -> LostTerminalRequest:
    if quantity < 1 or last_sequence < 0 or not reason.strip() or not idempotency_key.strip():
        raise ApiError(422, "invalid_review", "A lost-terminal request needs a quantity, a sequence, and a reason.")
    store = _bind(db, principal, store_id)
    existing = db.scalar(
        select(LostTerminalRequest).where(LostTerminalRequest.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    row = LostTerminalRequest(
        store_id=store,
        device_id=device_id,
        allocation_id=allocation_id,
        last_sequence=last_sequence,
        quantity=quantity,
        reason=reason.strip(),
        evidence=evidence.strip(),
        idempotency_key=idempotency_key.strip(),
        status="submitted",
        posting_status=POSTING,
        submitted_by_id=_user(principal),
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="lost_terminal.request",
        target_entity="LostTerminalRequest",
        target_entity_id=row.id,
        store_id=store,
        user=principal.user,
        new_values={"quantity": quantity, "last_sequence": last_sequence, "posting_status": POSTING},
    )
    return row


def decide_lost_terminal(
    db: Session,
    principal: Principal,
    request_id: uuid.UUID,
    *,
    decision: str,
    reason: str,
    store_id: uuid.UUID | None = None,
) -> LostTerminalRequest:
    if decision not in {"approved", "rejected"} or not reason.strip():
        raise ApiError(422, "invalid_review", "Choose approve or reject, and record a reason.")
    if store_id is not None:
        _bind(db, principal, store_id)
    row = db.get(LostTerminalRequest, request_id)
    if row is None:
        raise ApiError(404, "not_found", "That lost-terminal request does not exist.")
    _store(principal, row.store_id)
    actor = _user(principal)
    if actor == row.submitted_by_id:
        raise ApiError(403, "separation_of_duties", "The person who submitted this request cannot decide it.")
    if row.status != "submitted":
        return row
    row.status = decision
    row.decision_reason = reason.strip()
    row.decided_by_id = actor
    row.decided_at = datetime.now(UTC)
    row.posting_status = POSTING
    db.flush()
    audit.record(
        db,
        action_type="UPDATE",
        action="lost_terminal.decide",
        target_entity="LostTerminalRequest",
        target_entity_id=row.id,
        store_id=row.store_id,
        user=principal.user,
        new_values={"status": decision, "posting_status": POSTING},
    )
    return row


def submit_conflict_adjustment(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    idempotency_key: str,
    original_hash: str,
    proposed_hash: str,
    currency: str,
    amount_cents: int,
    reason: str,
    evidence: str,
    request_key: str,
) -> ConflictAdjustmentRequest:
    if (
        not idempotency_key.strip()
        or not original_hash.strip()
        or not proposed_hash.strip()
        or original_hash.strip() == proposed_hash.strip()
        or len(currency.strip()) != 3
        or not reason.strip()
        or not request_key.strip()
    ):
        raise ApiError(422, "invalid_review", "A conflict adjustment needs both payload hashes, a currency, and a reason.")
    store = _bind(db, principal, store_id)
    existing = db.scalar(
        select(ConflictAdjustmentRequest).where(ConflictAdjustmentRequest.request_key == request_key)
    )
    if existing is not None:
        return existing
    row = ConflictAdjustmentRequest(
        store_id=store,
        idempotency_key=idempotency_key.strip(),
        original_hash=original_hash.strip(),
        proposed_hash=proposed_hash.strip(),
        currency=currency.strip().upper(),
        amount_cents=amount_cents,
        reason=reason.strip(),
        evidence=evidence.strip(),
        request_key=request_key.strip(),
        status="submitted",
        posting_status=POSTING,
        submitted_by_id=_user(principal),
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="conflict_adjustment.request",
        target_entity="ConflictAdjustmentRequest",
        target_entity_id=row.id,
        store_id=store,
        user=principal.user,
        new_values={"amount_cents": amount_cents, "posting_status": POSTING},
    )
    return row


def decide_conflict_adjustment(
    db: Session,
    principal: Principal,
    request_id: uuid.UUID,
    *,
    decision: str,
    reason: str,
    store_id: uuid.UUID | None = None,
) -> ConflictAdjustmentRequest:
    if decision not in {"approved", "rejected"} or not reason.strip():
        raise ApiError(422, "invalid_review", "Choose approve or reject, and record a reason.")
    if store_id is not None:
        _bind(db, principal, store_id)
    row = db.get(ConflictAdjustmentRequest, request_id)
    if row is None:
        raise ApiError(404, "not_found", "That conflict adjustment does not exist.")
    _store(principal, row.store_id)
    actor = _user(principal)
    if actor == row.submitted_by_id:
        raise ApiError(403, "separation_of_duties", "The person who submitted this request cannot decide it.")
    if row.status != "submitted":
        return row
    row.status = decision
    row.decision_reason = reason.strip()
    row.decided_by_id = actor
    row.decided_at = datetime.now(UTC)
    row.posting_status = POSTING
    db.flush()
    audit.record(
        db,
        action_type="UPDATE",
        action="conflict_adjustment.decide",
        target_entity="ConflictAdjustmentRequest",
        target_entity_id=row.id,
        store_id=row.store_id,
        user=principal.user,
        new_values={"status": decision, "posting_status": POSTING},
    )
    return row
