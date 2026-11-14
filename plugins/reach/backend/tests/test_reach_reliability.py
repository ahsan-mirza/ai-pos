"""Webhook idempotency, ambiguous timeout, and report completeness."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.models.messaging import OutboundMessage
from app.services.messaging_providers import ProviderError
from app.services.messaging_service import dispatch_due
from reach.models import ReachCampaignRun, ReachConnection, ReachRecipient
from reach.prepare import lease_recipient, prepare_due, recover_leases
from reach.report_pdf import render_run
from reach.runs import _csv_cell, present, refresh_run
from reach.webhooks import accept

from test_campaign_runs import _campaign, _ready


def test_pdf_says_when_the_recipient_list_is_incomplete() -> None:
    body = {
        "campaign_name": "November",
        "run_number": 1,
        "channel": "email",
        "status": "completed",
        "started_at": None,
        "completed_at": None,
        "report_built_at": None,
        "delivery_updated_at": None,
        "total_recipients": 5,
        "eligible_recipients": 5,
        "excluded_recipients": 0,
        "accepted_count": 1,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "cancelled_count": 0,
        "recipient_rows": 5,
    }
    people = [{"customer": f"C{i}", "contact": "a***@example.test", "status": "queued"} for i in range(2)]
    pdf = render_run(body, people)
    assert pdf.startswith(b"%PDF")
    assert b"not the full audience" in pdf
    assert b"2 of 5" in pdf


def test_report_keys_cannot_leave_the_tenant_folder() -> None:
    import pytest

    from reach.report_store import ReportStoreError, _safe_key

    with pytest.raises(ReportStoreError):
        _safe_key("../secrets.txt")


def test_csv_cells_cannot_start_a_formula() -> None:
    assert _csv_cell("=HYPERLINK(\"x\")").startswith("'")
    assert _csv_cell("+971500000000").startswith("'")
    assert _csv_cell("Sara") == "Sara"


def test_ambiguous_timeout_is_not_sent_again(client, session, monkeypatch) -> None:
    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Timeout", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, get_settings())

    def timed_out(*_args, **_kwargs):
        raise ProviderError("timed out", ambiguous=True)

    monkeypatch.setattr("app.services.reach_bridge.submit_message", timed_out)
    settings = get_settings()
    settings.reach_send_interval_seconds = 0
    settings.reach_transactional_reserve = 0
    dispatch_due(session, settings, limit=1)
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    assert message.status == "FAILED"
    assert message.context["ambiguous_timeout"] == "1"
    dispatch_due(session, settings, limit=1)
    session.refresh(message)
    assert message.status == "FAILED"
    assert message.attempts == 1


def test_a_slow_provider_sees_the_lease_before_the_call(client, session, monkeypatch) -> None:
    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Slow", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, get_settings())
    seen: dict[str, object] = {}

    def slow(db, _settings, _provider, _outgoing, _creds, message):
        recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
        seen["status"] = recipient.status
        seen["started"] = recipient.processing_started_at
        seen["lease"] = recipient.lease_until
        seen["next"] = message.next_attempt_at
        return "log-slow-1"

    monkeypatch.setattr("app.services.reach_bridge.submit_message", slow)
    settings = get_settings()
    settings.reach_send_interval_seconds = 0
    settings.reach_transactional_reserve = 0
    dispatch_due(session, settings, limit=1)
    def _aware(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    assert seen["status"] == "sending"
    assert seen["started"] is not None
    assert seen["lease"] is not None
    assert _aware(seen["next"]) >= _aware(seen["lease"])
    run = session.scalar(select(ReachCampaignRun))
    body = present(session, run)
    assert body["accepted_count"] == 1
    assert body["delivered_count"] == 0


def test_webhook_delivery_does_not_double_count(client, session) -> None:
    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Hooks", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, get_settings())
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    recipient = session.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    message.status = "SENT"
    message.provider_message_id = "prov-1"
    recipient.status = "sent"
    recipient.provider_message_id = "prov-1"
    connection = ReachConnection(name="Test", instance_name="test-instance", webhook_key="hook-key", status="open")
    session.add(connection)
    session.commit()
    run = session.scalar(select(ReachCampaignRun))
    refresh_run(session, run.id)
    settings = get_settings()
    settings.evolution_webhook_secret = "hook-secret"
    delivered = {"event": "messages.update", "data": {"key": {"id": "prov-1"}, "status": "DELIVERY_ACK"}}
    first = accept(session, settings, "hook-key", delivered, "hook-secret")
    second = accept(session, settings, "hook-key", delivered, "hook-secret")
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    session.refresh(recipient)
    assert recipient.status == "delivered"
    read = {"eventId": "read-1", "data": {"key": {"id": "prov-1"}, "status": "READ"}}
    accept(session, settings, "hook-key", read, "hook-secret")
    late = {"eventId": "late-1", "data": {"key": {"id": "prov-1"}, "status": "DELIVERY_ACK"}}
    accept(session, settings, "hook-key", late, "hook-secret")
    session.refresh(recipient)
    assert recipient.status == "read"
    refresh_run(session, run.id, delivery=True)
    body = present(session, run)
    assert body["accepted_count"] == 1
    assert body["delivered_count"] == 1
    assert body["read_count"] == 1
    unknown = {"eventId": "other", "data": {"key": {"id": "missing"}, "status": "DELIVERY_ACK"}}
    accept(session, settings, "hook-key", unknown, "hook-secret")
    session.refresh(recipient)
    assert recipient.status == "read"


def test_a_live_lease_is_not_reclaimed(client, session) -> None:
    headers, customer_id = _ready(client)
    client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Hold", customer_id))
    prepare_due(session, get_settings())
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    lease_recipient(session, message, seconds=120)
    session.commit()
    assert recover_leases(session) == 0
    recipient = session.scalar(select(ReachRecipient))
    assert recipient.status == "sending"
    recipient.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert recover_leases(session) == 1
    session.refresh(recipient)
    assert recipient.status == "queued"


def test_a_two_second_provider_delay_keeps_the_lease(client, session, monkeypatch) -> None:
    import time

    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Delay", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, get_settings())
    seen: dict[str, object] = {}

    def slow(db, _settings, _provider, _outgoing, _creds, message):
        recipient = db.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
        seen["status"] = recipient.status
        time.sleep(2)
        return "log-delay-1"

    monkeypatch.setattr("app.services.reach_bridge.submit_message", slow)
    settings = get_settings()
    settings.reach_send_interval_seconds = 0
    settings.reach_transactional_reserve = 0
    started = time.perf_counter()
    dispatch_due(session, settings, limit=1)
    elapsed = time.perf_counter() - started
    assert seen["status"] == "sending"
    assert elapsed >= 1.8
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    assert message.status == "SENT"
    assert message.provider_message_id == "log-delay-1"


def test_webhook_burst_stays_idempotent(client, session) -> None:
    from app.core.errors import ApiError

    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Burst", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, get_settings())
    recipient = session.scalar(select(ReachRecipient))
    message = session.get(OutboundMessage, recipient.outbound_message_id)
    message.status = "SENT"
    message.provider_message_id = "burst-1"
    recipient.status = "sent"
    recipient.provider_message_id = "burst-1"
    session.add(ReachConnection(name="Burst", instance_name="burst-instance", webhook_key="burst-key", status="open"))
    session.commit()
    settings = get_settings()
    settings.evolution_webhook_secret = "burst-secret"
    try:
        accept(session, settings, "burst-key", {"eventId": "bad", "data": {"key": {"id": "burst-1"}, "status": "READ"}}, "wrong")
        raise AssertionError("invalid signature was accepted")
    except ApiError as exc:
        assert exc.status_code == 401
    applied = 0
    for index in range(1000):
        status = "READ" if index % 2 == 0 else "DELIVERY_ACK"
        event_id = "same" if index % 5 == 0 else f"evt-{index}"
        result = accept(
            session,
            settings,
            "burst-key",
            {"eventId": event_id, "data": {"key": {"id": "burst-1"}, "status": status}},
            "burst-secret",
        )
        if not result["duplicate"]:
            applied += 1
    accept(
        session,
        settings,
        "burst-key",
        {"eventId": "unknown-burst", "data": {"key": {"id": "missing-id"}, "status": "DELIVERY_ACK"}},
        "burst-secret",
    )
    session.refresh(recipient)
    assert recipient.status == "read"
    assert applied < 1000
    run = session.scalar(select(ReachCampaignRun))
    refresh_run(session, run.id, delivery=True)
    body = present(session, run)
    assert body["read_count"] == 1
    assert body["accepted_count"] == 1
    assert body["delivered_count"] == 1
