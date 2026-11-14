"""Promotional rows wait. A receipt is chosen before the next campaign send."""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.models.messaging import OutboundMessage
from app.services.messaging_service import choose_next, dispatch_due, priority_for
from wholesale_support import seed


def test_priority_comes_from_the_message_type() -> None:
    assert priority_for("receipt") == 1
    assert priority_for("statement") == 1
    assert priority_for("ai_agent") == 2
    assert priority_for("overdue_reminder") == 2
    assert priority_for("campaign") == 3
    assert priority_for("coupon_issued") == 3
    # An unknown name stays transactional. A caller cannot invent a low priority.
    assert priority_for("frontend-priority") == 1


def test_a_receipt_beats_an_older_campaign() -> None:
    older = datetime(2020, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 11, 13, tzinfo=UTC)
    candidates = [("tenant-a", 3, older), ("tenant-d", 1, newer)]
    assert choose_next(candidates, allow_marketing=True) == 1


def test_same_priority_sends_the_message_that_has_waited_longest() -> None:
    candidates = [
        ("tenant-a", 3, datetime(2026, 2, 1, tzinfo=UTC)),
        ("tenant-b", 3, datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    assert choose_next(candidates, allow_marketing=True) == 1


def test_reserved_capacity_does_not_pick_marketing() -> None:
    candidates = [("tenant-a", 3, datetime(2020, 1, 1, tzinfo=UTC))]
    assert choose_next(candidates, allow_marketing=False) is None


def test_receipt_is_sent_before_an_older_campaign(client, session) -> None:
    seed(client)
    past = datetime(2020, 1, 1, tzinfo=UTC)
    campaign = OutboundMessage(
        channel="email",
        to_address="shopper@example.com",
        template_key="campaign",
        priority=3,
        subject="Weekend",
        body="Sale",
        status="QUEUED",
        created_at=past,
        next_attempt_at=past,
    )
    receipt = OutboundMessage(
        channel="email",
        to_address="shopper@example.com",
        template_key="receipt",
        priority=1,
        subject="Receipt",
        body="Thank you",
        status="QUEUED",
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
        next_attempt_at=past,
    )
    session.add(campaign)
    session.add(receipt)
    session.commit()

    dispatch_due(session, get_settings(), limit=1)

    session.refresh(campaign)
    session.refresh(receipt)
    assert receipt.status == "SENT"
    assert campaign.status == "QUEUED"
