"""Write-off and conflict requests are recorded and are not posted."""

import uuid

from app.core.errors import ApiError
from app.models.inventory import StockMovement
from app.services.offline_approval_service import (
    POSTING,
    decide_conflict_adjustment,
    decide_writeoff,
    request_conflict_adjustment,
    request_writeoff,
)
from sqlalchemy import func, select


def test_writeoff_and_conflict_decisions_do_not_post(session) -> None:
    assert POSTING == "AWAITING APPROVAL"
    requester = uuid.uuid4()
    reviewer = uuid.uuid4()
    writeoff = request_writeoff(
        session,
        store_id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        allocation_id=uuid.uuid4(),
        quantity=4,
        reason="Terminal did not return",
        evidence="Last sequence 3",
        requested_by_id=requester,
    )
    session.commit()
    try:
        decide_writeoff(session, writeoff.id, actor_id=requester, approve=True, note="same person")
        raise AssertionError("self approval should fail")
    except ApiError as exc:
        assert exc.status_code == 403
    decided = decide_writeoff(session, writeoff.id, actor_id=reviewer, approve=True, note="reviewed")
    assert decided.status == "approved"
    assert decided.posted_at is None
    adjustment = request_conflict_adjustment(
        session,
        store_id=uuid.uuid4(),
        idempotency_key="conflict-key-1",
        original_hash="a" * 64,
        proposed_hash="b" * 64,
        amount_cents=500,
        reason="Payloads differ",
        requested_by_id=requester,
    )
    again = request_conflict_adjustment(
        session,
        store_id=adjustment.store_id,
        idempotency_key="conflict-key-1",
        original_hash="a" * 64,
        proposed_hash="c" * 64,
        amount_cents=900,
        reason="Payloads differ",
        requested_by_id=requester,
    )
    assert again.id == adjustment.id
    assert again.amount_cents == 500
    closed = decide_conflict_adjustment(session, adjustment.id, actor_id=reviewer, approve=False, note="no")
    assert closed.status == "rejected"
    assert closed.posted_at is None
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0
