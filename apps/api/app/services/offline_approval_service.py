"""Record write-off and conflict-adjustment requests. Do not post them.

The business decision note does not approve a stock valuation, a financial
treatment, or a separation-of-duties exception. An approved row stays unposted.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.offline_approval import OfflineConflictAdjustment, OfflineWriteoffRequest

POSTING = "AWAITING APPROVAL"


def request_writeoff(
    db: Session,
    *,
    store_id: uuid.UUID,
    device_id: uuid.UUID,
    allocation_id: uuid.UUID,
    quantity: int,
    reason: str,
    evidence: str,
    requested_by_id: uuid.UUID,
) -> OfflineWriteoffRequest:
    if quantity < 1:
        raise ApiError(422, "invalid_quantity", "A write-off request needs a positive quantity.")
    if not reason.strip():
        raise ApiError(422, "reason_required", "A write-off request needs a reason.")
    row = OfflineWriteoffRequest(
        store_id=store_id,
        device_id=device_id,
        allocation_id=allocation_id,
        requested_quantity=quantity,
        reason=reason.strip()[:500],
        evidence=evidence.strip()[:500],
        requested_by_id=requested_by_id,
        status="pending",
    )
    db.add(row)
    db.flush()
    return row


def decide_writeoff(
    db: Session,
    request_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    approve: bool,
    note: str,
) -> OfflineWriteoffRequest:
    row = db.get(OfflineWriteoffRequest, request_id)
    if row is None:
        raise ApiError(404, "request_not_found", "That write-off request does not exist.")
    if row.status != "pending":
        return row
    if actor_id == row.requested_by_id:
        raise ApiError(403, "separation_of_duties", "The person who requested the write-off cannot decide it.")
    row.status = "approved" if approve else "rejected"
    row.decided_by_id = actor_id
    row.decision_note = note.strip()[:500]
    row.posted_at = None
    db.flush()
    return row


def request_conflict_adjustment(
    db: Session,
    *,
    store_id: uuid.UUID,
    idempotency_key: str,
    original_hash: str,
    proposed_hash: str,
    amount_cents: int,
    reason: str,
    requested_by_id: uuid.UUID,
) -> OfflineConflictAdjustment:
    existing = db.scalar(
        select(OfflineConflictAdjustment).where(OfflineConflictAdjustment.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    if original_hash == proposed_hash:
        raise ApiError(422, "not_a_conflict", "An adjustment needs two different payload hashes.")
    if not reason.strip():
        raise ApiError(422, "reason_required", "An adjustment request needs a reason.")
    row = OfflineConflictAdjustment(
        store_id=store_id,
        idempotency_key=idempotency_key[:128],
        original_hash=original_hash[:64],
        proposed_hash=proposed_hash[:64],
        amount_cents=amount_cents,
        reason=reason.strip()[:500],
        requested_by_id=requested_by_id,
        status="pending",
    )
    db.add(row)
    db.flush()
    return row


def decide_conflict_adjustment(
    db: Session,
    request_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    approve: bool,
    note: str,
) -> OfflineConflictAdjustment:
    row = db.get(OfflineConflictAdjustment, request_id)
    if row is None:
        raise ApiError(404, "request_not_found", "That adjustment request does not exist.")
    if row.status != "pending":
        return row
    if actor_id == row.requested_by_id:
        raise ApiError(403, "separation_of_duties", "The person who requested the adjustment cannot decide it.")
    row.status = "approved" if approve else "rejected"
    row.decided_by_id = actor_id
    row.decision_note = note.strip()[:500]
    row.posted_at = None
    db.flush()
    return row
