"""A second send of a campaign is a new run. Receipts stay ahead of it."""

import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.models.messaging import OutboundMessage
from app.services.messaging_service import dispatch_due, priority_for, queue_metrics
from reach.models import ReachCampaignRun, ReachRecipient
from reach.report_pdf import render_run
from reach.runs import present


def _enable(client, headers: dict[str, str]) -> None:
    current = client.get("/api/v1/settings", headers=headers)
    body = current.json()
    updated = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": body["business_profile"], "capabilities": [*body["capabilities"], "axiz_reach"]},
    )
    assert updated.status_code == 200, updated.text


def _campaign(name: str, customer_id: str | None = None) -> dict:
    audience: dict = {}
    if customer_id is not None:
        audience["customer_ids"] = [customer_id]
    return {
        "idempotency_key": str(uuid.uuid4()),
        "name": name,
        "channels": ["email"],
        "audience": audience,
        "content": {"email": {"body": "Hello {{customer_name}}", "subject": name}},
    }


def _ready(client):
    from wholesale_support import admin, seed

    seed(client)
    headers, _user = admin(client)
    _enable(client, headers)
    saved = client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": "email", "enabled": True, "provider": "log", "public_config": {}},
    )
    assert saved.status_code == 200, saved.text
    person = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "email": "sara@example.com", "marketing_email_opt_in": True},
    )
    assert person.status_code == 201, person.text
    return headers, person.json()["id"]


def test_two_runs_keep_separate_recipients(client, session) -> None:
    from wholesale_support import admin, seed

    seed(client)
    headers, _user = admin(client)
    _enable(client, headers)
    client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": "email", "enabled": True, "provider": "log", "public_config": {}},
    )
    person = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "email": "sara@example.com", "marketing_email_opt_in": True},
    )
    assert person.status_code == 201, person.text
    customer_id = person.json()["id"]
    first = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Weekend", customer_id))
    assert first.status_code == 201, first.text
    campaign_id = first.json()["id"]
    second = client.post(f"/api/v1/reach/campaigns/{campaign_id}/runs", headers=headers)
    assert second.status_code == 201, second.text
    from reach.prepare import prepare_due

    prepare_due(session, get_settings())

    runs = list(session.scalars(select(ReachCampaignRun).order_by(ReachCampaignRun.run_number)))
    assert [run.run_number for run in runs] == [1, 2]
    assert runs[0].id != runs[1].id
    first_people = list(session.scalars(select(ReachRecipient).where(ReachRecipient.campaign_run_id == runs[0].id)))
    second_people = list(session.scalars(select(ReachRecipient).where(ReachRecipient.campaign_run_id == runs[1].id)))
    assert len(first_people) == 1
    assert len(second_people) == 1
    assert first_people[0].id != second_people[0].id
    assert first_people[0].outbound_message_id != second_people[0].outbound_message_id


def test_cancel_leaves_a_receipt_queued(client, session) -> None:
    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Promo", customer_id))
    assert launched.status_code == 201, launched.text
    run = session.scalar(select(ReachCampaignRun))
    assert run is not None
    receipt = OutboundMessage(
        channel="email",
        to_address="sara@example.com",
        template_key="receipt",
        priority=priority_for("receipt"),
        subject="Receipt",
        body="Thank you",
        status="QUEUED",
    )
    session.add(receipt)
    session.commit()
    from reach.prepare import prepare_due

    prepare_due(session, get_settings())

    cancelled = client.post(f"/api/v1/reach/campaign-runs/{run.id}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    session.refresh(receipt)
    assert receipt.status == "QUEUED"
    promo = session.scalar(
        select(OutboundMessage).where(OutboundMessage.template_key == "campaign", OutboundMessage.priority == 3)
    )
    assert promo is not None
    assert promo.status == "SKIPPED"

    dispatch_due(session, get_settings(), limit=1)
    session.refresh(receipt)
    assert receipt.status == "SENT"


def test_report_separates_acceptance_from_delivery(client, session) -> None:
    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Figures", customer_id))
    assert launched.status_code == 201, launched.text
    run = session.scalar(select(ReachCampaignRun))
    assert run is not None
    listed = client.get("/api/v1/reach/campaign-runs", headers=headers)
    assert listed.status_code == 200
    body = present(session, run)
    assert body["accepted_count"] == 0
    assert body["delivered_count"] == 0
    pdf = render_run(body, [])
    assert pdf.startswith(b"%PDF")
    csv_body = client.get(f"/api/v1/reach/campaign-runs/{run.id}/recipients.csv", headers=headers)
    assert csv_body.status_code == 200
    assert "Contact" in csv_body.text
    assert "sara@example.com" not in csv_body.text


def test_queue_metrics_count_this_store(client, session) -> None:
    headers, customer_id = _ready(client)
    client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Depth", customer_id))
    from reach.prepare import prepare_due

    prepare_due(session, get_settings())
    metrics = client.get("/api/v1/reach/queue", headers=headers)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["campaign_queued"] >= 1
    assert body["by_priority"]["3"] >= 1
    direct = queue_metrics(session)
    assert direct["campaign_queued"] == body["campaign_queued"]


def test_a_campaign_cannot_choose_its_own_priority() -> None:
    assert priority_for("campaign") == 3
    assert priority_for("receipt") == 1


def test_audience_is_prepared_in_batches_without_duplicates(client, session) -> None:
    headers, first_id = _ready(client)
    extra = []
    for name in ("Nora", "Lina"):
        person = client.post(
            "/api/v1/customers",
            headers=headers,
            json={"name": name, "email": f"{name.lower()}@example.com", "marketing_email_opt_in": True},
        )
        assert person.status_code == 201, person.text
        extra.append(person.json()["id"])
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json=_campaign("Batch", None) | {"audience": {"customer_ids": [first_id, *extra]}},
    )
    assert launched.status_code == 201, launched.text
    assert launched.json()["status"] == "preparing"
    assert launched.json()["queued_count"] == 0
    from types import SimpleNamespace

    from reach.prepare import _prepare_page

    run = session.scalar(select(ReachCampaignRun))
    assert run is not None
    assert _prepare_page(session, SimpleNamespace(reach_prepare_batch=1), run) == 1
    session.commit()
    assert run.total_candidates == 1
    assert session.scalar(select(ReachRecipient).where(ReachRecipient.campaign_run_id == run.id)) is not None
    assert _prepare_page(session, SimpleNamespace(reach_prepare_batch=1), run) == 1
    session.commit()
    people = list(session.scalars(select(ReachRecipient).where(ReachRecipient.campaign_run_id == run.id)))
    assert len(people) == 2
    assert len({row.customer_id for row in people}) == 2


def test_an_expired_lease_is_not_sent_twice(client, session) -> None:
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from reach.prepare import lease_recipient, prepare_due, recover_leases

    headers, customer_id = _ready(client)
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Lease", customer_id))
    assert launched.status_code == 201, launched.text
    prepare_due(session, SimpleNamespace(reach_prepare_batch=50))
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    recipient = session.scalar(select(ReachRecipient).where(ReachRecipient.outbound_message_id == message.id))
    lease_recipient(session, message, seconds=30)
    session.commit()
    assert recipient.status == "sending"
    recipient.lease_until = datetime.now(UTC) - timedelta(seconds=5)
    session.commit()
    assert recover_leases(session) == 1
    session.refresh(message)
    session.refresh(recipient)
    assert message.status == "QUEUED"
    assert message.provider_message_id is None
    assert recipient.status == "queued"
    message.provider_message_id = "provider-1"
    recipient.status = "sending"
    recipient.lease_until = datetime.now(UTC) - timedelta(seconds=5)
    session.commit()
    recover_leases(session)
    session.flush()
    session.refresh(message)
    assert message.status == "SENT"
    assert message.provider_message_id == "provider-1"
