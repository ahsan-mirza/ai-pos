"""Review queues for a lost terminal and a sync conflict. Decisions do not post."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.payloads import ApiModel
from app.services import offline_review_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanAdjust = Annotated[Principal, Depends(authorize(Permission.INVENTORY_ADJUST_STOCK))]
CanAccount = Annotated[Principal, Depends(authorize(Permission.ACCOUNTING_MANAGE))]


class LostTerminalIn(ApiModel):
    store_id: uuid.UUID
    device_id: uuid.UUID
    allocation_id: uuid.UUID | None = None
    last_sequence: int
    quantity: int
    reason: str
    evidence: str = ""
    idempotency_key: str


class DecisionIn(ApiModel):
    decision: str
    reason: str
    store_id: uuid.UUID | None = None


class ConflictIn(ApiModel):
    store_id: uuid.UUID
    idempotency_key: str
    original_hash: str
    proposed_hash: str
    currency: str
    amount_cents: int
    reason: str
    evidence: str = ""
    request_key: str


def _lost(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "status": row.status,
        "posting_status": row.posting_status,
        "quantity": row.quantity,
        "idempotency_key": row.idempotency_key,
    }


def _conflict(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "status": row.status,
        "posting_status": row.posting_status,
        "idempotency_key": row.idempotency_key,
        "original_hash": row.original_hash,
        "amount_cents": row.amount_cents,
    }


@router.post("/inventory/lost-terminal-requests", status_code=201)
def submit_lost_terminal(payload: LostTerminalIn, db: Db, principal: CanAdjust) -> dict[str, object]:
    row = offline_review_service.submit_lost_terminal(db, principal, **payload.model_dump())
    db.commit()
    return _lost(row)


@router.post("/inventory/lost-terminal-requests/{request_id}/decision")
def decide_lost_terminal(request_id: uuid.UUID, payload: DecisionIn, db: Db, principal: CanAdjust) -> dict[str, object]:
    row = offline_review_service.decide_lost_terminal(
        db, principal, request_id, decision=payload.decision, reason=payload.reason, store_id=payload.store_id
    )
    db.commit()
    return _lost(row)


@router.post("/sync/conflict-adjustments", status_code=201)
def submit_conflict(payload: ConflictIn, db: Db, principal: CanAccount) -> dict[str, object]:
    row = offline_review_service.submit_conflict_adjustment(db, principal, **payload.model_dump())
    db.commit()
    return _conflict(row)


@router.post("/sync/conflict-adjustments/{request_id}/decision")
def decide_conflict(request_id: uuid.UUID, payload: DecisionIn, db: Db, principal: CanAccount) -> dict[str, object]:
    row = offline_review_service.decide_conflict_adjustment(
        db, principal, request_id, decision=payload.decision, reason=payload.reason, store_id=payload.store_id
    )
    db.commit()
    return _conflict(row)
