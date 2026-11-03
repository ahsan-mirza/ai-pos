"""Evolution sends, prepaid credits, and tenant isolation on the existing outbox."""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.models.reach import ReachCampaign, ReachCreditAccount, ReachRecipient
from app.services.messaging_providers import ProviderError
from app.tenancy.scoping import DEFAULT_TENANT_ID
from reach import credits as credit_book
from reach.providers.evolution.client import set_handler
from tests.governance_support import platform  # noqa: F401
from wholesale_support import admin, seed


@pytest.fixture(autouse=True)
def _fake_evolution():
    calls: list[tuple[str, str]] = []

    def handler(method: str, path: str, body: dict | None) -> dict:
        calls.append((method, path))
        if path.startswith("/message/sendText/") and body and body.get("text") == "fail":
            raise ProviderError("Evolution rejected the message.", permanent=True)
        if path.startswith("/message/sendText/") or path.startswith("/message/sendMedia/"):
            return {"key": {"id": "MSG-1"}}
        if "/connectionState/" in path:
            return {"instance": {"state": "open", "wuid": "971500000111"}}
        if path.startswith("/instance/connect/"):
            return {"base64": "qr-bytes"}
        return {"ok": True}

    set_handler(handler)
    settings = get_settings()
    settings.evolution_api_url = "http://evolution.test"
    settings.evolution_api_key = "test-key"
    settings.evolution_webhook_secret = "hook-secret"
    settings.public_base_url = "https://axizpos.test"
    settings.reach_send_interval_seconds = 0
    yield calls
    set_handler(None)


def _enable(client, headers: dict[str, str]) -> None:
    current = client.get("/api/v1/settings", headers=headers).json()
    client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={
            "business_profile": current["business_profile"],
            "capabilities": list(dict.fromkeys([*current["capabilities"], "axiz_reach"])),
        },
    )


def _ready(client, headers: dict[str, str]) -> str:
    created = client.post("/api/v1/reach/connections", headers=headers, json={"name": "Counter"})
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]
    status = client.post(f"/api/v1/reach/connections/{connection_id}/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "open"
    saved = client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": "whatsapp", "enabled": True, "provider": "evolution", "public_config": {}},
    )
    assert saved.status_code == 200, saved.text
    return created.json()["id"]


def test_cross_tenant_campaign_and_credits_stay_hidden(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": "whatsapp", "enabled": True, "provider": "log", "public_config": {}},
    )
    other = uuid.UUID("00000000-0000-4000-8000-000000000099")
    hidden = ReachCampaign(
        name="Other store",
        idempotency_key=str(uuid.uuid4()),
        channels=["whatsapp"],
        audience={},
        content={},
    )
    hidden.tenant_id = other
    session.add(hidden)
    session.add(ReachCreditAccount(purpose="marketing", balance=50, reserved=0, tenant_id=other))
    session.commit()
    missing = client.get(f"/api/v1/reach/campaigns/{hidden.id}", headers=headers)
    assert missing.status_code == 404
    credits = client.get("/api/v1/reach/credits", headers=headers).json()
    assert credits["balance"] == 0
    assert session.get(ReachCampaign, hidden.id) is None
    assert hidden.tenant_id != DEFAULT_TENANT_ID


def test_double_consume_debits_once(session) -> None:
    campaign_id = uuid.uuid4()
    message_id = uuid.uuid4()
    credit_book.allocate(session, units=3, note="seed", idempotency_key="alloc-once")
    credit_book.reserve(session, campaign_id, 1)
    credit_book.consume(session, message_id, campaign_id)
    credit_book.consume(session, message_id, campaign_id)
    found = credit_book.snapshot(session)
    assert found is not None
    assert found["balance"] == 2
    assert found["reserved"] == 0


def test_evolution_failure_releases_the_reservation(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-release")
    session.commit()
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "phone": "+971501110010", "marketing_whatsapp_opt_in": True},
    )
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Fail",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": "fail", "subject": "Fail"}},
        },
    )
    assert launched.status_code == 201, launched.text
    held = credit_book.snapshot(session)
    assert held is not None and held["reserved"] == 1
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    released = credit_book.snapshot(session)
    assert released is not None
    assert released["balance"] == 2
    assert released["reserved"] == 0
    recipient = session.scalar(select(ReachRecipient))
    assert recipient is not None and recipient.status == "failed"


def test_evolution_send_webhook_and_duplicate(client, session, _fake_evolution) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-send")
    session.commit()
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110011", "marketing_whatsapp_opt_in": True},
    )
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Hello",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Hello"}},
        },
    )
    assert launched.status_code == 201, launched.text
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    assert any(path.startswith("/message/sendText/") for _, path in _fake_evolution)
    sent = credit_book.snapshot(session)
    assert sent is not None and sent["balance"] == 1 and sent["reserved"] == 0
    key = session.scalar(select(ReachRecipient.provider_message_id))
    assert key == "MSG-1"
    payload = {"eventId": "evt-1", "event": "messages.update", "data": {"keyId": "MSG-1", "status": "DELIVERY_ACK"}}
    first = client.post(
        f"/api/v1/reach/webhooks/evolution/{_webhook_key(session)}",
        headers={"apikey": "hook-secret"},
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    again = client.post(
        f"/api/v1/reach/webhooks/evolution/{_webhook_key(session)}",
        headers={"apikey": "hook-secret"},
        json=payload,
    )
    assert again.status_code == 200, again.text
    assert again.json()["duplicate"] is True
    session.expire_all()
    recipient = session.scalar(select(ReachRecipient))
    assert recipient is not None and recipient.status == "delivered"


def test_stop_opts_the_customer_out(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-stop")
    session.commit()
    created = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Lina", "phone": "+971501110012", "marketing_whatsapp_opt_in": True},
    ).json()
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Later",
            "channels": ["whatsapp"],
            "audience": {},
            "scheduled_at": "2099-01-01T00:00:00Z",
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Later"}},
        },
    )
    assert launched.status_code == 201, launched.text
    payload = {
        "eventId": "evt-stop",
        "event": "messages.upsert",
        "data": {"key": {"remoteJid": "971501110012@s.whatsapp.net"}, "message": {"conversation": "STOP"}},
    }
    stopped = client.post(
        f"/api/v1/reach/webhooks/evolution/{_webhook_key(session)}",
        headers={"apikey": "hook-secret"},
        json=payload,
    )
    assert stopped.status_code == 200, stopped.text
    session.expire_all()
    customer = session.get(Customer, uuid.UUID(created["id"]))
    assert customer is not None and customer.marketing_whatsapp_opt_in is False
    queued = session.scalars(select(OutboundMessage).where(OutboundMessage.template_key == "campaign")).all()
    assert queued and all(row.status == "SKIPPED" for row in queued)
    released = credit_book.snapshot(session)
    assert released is not None and released["reserved"] == 0 and released["balance"] == 2


def test_opted_out_customer_is_not_queued(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": "whatsapp", "enabled": True, "provider": "log", "public_config": {}},
    )
    client.post("/api/v1/customers", headers=headers, json={"name": "No consent", "phone": "+971501110013"})
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Quiet",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Quiet"}},
        },
    )
    assert launched.status_code == 201, launched.text
    assert launched.json()["queued_count"] == 0


def test_console_allocation_is_idempotent(platform) -> None:
    admin_headers = platform.operator()
    tenant_id = platform.tenant_id("alpha")
    body = {"units": 4, "note": "opening", "idempotency_key": "console-alloc-1"}
    first = platform.client.post(f"/api/v1/super-admin/tenants/{tenant_id}/reach/credits", headers=admin_headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["balance"] == 4
    second = platform.client.post(f"/api/v1/super-admin/tenants/{tenant_id}/reach/credits", headers=admin_headers, json=body)
    assert second.status_code == 200, second.text
    assert second.json()["balance"] == 4


def test_open_session_selects_evolution_and_registers_the_webhook(client, session, _fake_evolution) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    created = client.post("/api/v1/reach/connections", headers=headers, json={"name": "Counter"})
    assert created.status_code == 201, created.text
    assert created.json()["webhook_status"] == "registered"
    status = client.post(f"/api/v1/reach/connections/{created.json()['id']}/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "open"
    channels = client.get("/api/v1/reach/channels", headers=headers).json()
    whatsapp = next(row for row in channels if row["channel"] == "whatsapp")
    assert whatsapp["provider"] == "evolution"
    assert whatsapp["enabled"] is True
    assert any(path.startswith("/webhook/set/") for _, path in _fake_evolution)


def test_selected_customers_and_duplicate_phones(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=5, note="seed", idempotency_key="alloc-select")
    session.commit()
    first = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110021", "marketing_whatsapp_opt_in": True},
    ).json()
    duplicate = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Same phone", "phone": "+971501110021", "marketing_whatsapp_opt_in": True},
    ).json()
    second = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Other", "phone": "+971501110022", "marketing_whatsapp_opt_in": True},
    ).json()
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Picked",
            "channels": ["whatsapp"],
            "audience": {"customer_ids": [first["id"], duplicate["id"], second["id"]]},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Picked"}},
        },
    )
    assert launched.status_code == 201, launched.text
    assert launched.json()["queued_count"] == 2
    assert launched.json()["suppressed_count"] == 1
    empty = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Nobody",
            "channels": ["whatsapp"],
            "audience": {"customer_ids": []},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Nobody"}},
        },
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "audience_required"


def test_evolution_campaign_without_credits_is_refused(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110031", "marketing_whatsapp_opt_in": True},
    )
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Unpaid",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Unpaid"}},
        },
    )
    assert launched.status_code == 422, launched.text
    assert launched.json()["error"]["code"] == "credits_required"


def test_withdrawn_consent_is_rechecked_before_send(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-withdraw")
    session.commit()
    created = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110041", "marketing_whatsapp_opt_in": True},
    ).json()
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Later",
            "channels": ["whatsapp"],
            "audience": {},
            "scheduled_at": "2099-01-01T00:00:00Z",
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Later"}},
        },
    )
    assert launched.status_code == 201, launched.text
    customer = session.get(Customer, uuid.UUID(created["id"]))
    assert customer is not None
    customer.marketing_whatsapp_opt_in = False
    queued = session.scalars(select(OutboundMessage).where(OutboundMessage.template_key == "campaign")).all()
    for message in queued:
        message.next_attempt_at = message.created_at
    session.commit()
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    session.expire_all()
    skipped = session.scalars(select(OutboundMessage).where(OutboundMessage.template_key == "campaign")).all()
    assert skipped and all(row.status == "SKIPPED" for row in skipped)
    released = credit_book.snapshot(session)
    assert released is not None and released["reserved"] == 0 and released["balance"] == 2


def test_disconnected_session_pauses_the_campaign(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-pause")
    session.commit()
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110051", "marketing_whatsapp_opt_in": True},
    )
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Live",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": "Hello {{customer_name}}", "subject": "Live"}},
        },
    )
    assert launched.status_code == 201, launched.text
    from app.models.reach import ReachConnection

    connection = session.scalar(select(ReachConnection))
    assert connection is not None
    connection.status = "close"
    session.commit()
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    session.expire_all()
    campaign = session.scalar(select(ReachCampaign))
    assert campaign is not None and campaign.status == "paused"
    queued = session.scalar(select(OutboundMessage).where(OutboundMessage.template_key == "campaign"))
    assert queued is not None and queued.status == "QUEUED"
    held = credit_book.snapshot(session)
    assert held is not None and held["reserved"] == 1 and held["balance"] == 2


def test_media_upload_and_image_send(client, session, _fake_evolution) -> None:
    import base64

    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-media")
    session.commit()
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110061", "marketing_whatsapp_opt_in": True},
    )
    rejected = client.post(
        "/api/v1/reach/media",
        headers=headers,
        json={"file_name": "note.png", "mime_type": "image/png", "content_base64": base64.b64encode(b"hello").decode()},
    )
    assert rejected.status_code == 422
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    uploaded = client.post(
        "/api/v1/reach/media",
        headers=headers,
        json={"file_name": "banner.png", "mime_type": "image/png", "content_base64": base64.b64encode(png).decode()},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["kind"] == "image"
    launched = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": "Banner",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {
                "whatsapp": {
                    "body": "See this",
                    "subject": "Banner",
                    "media_id": uploaded.json()["id"],
                    "media_kind": "image",
                }
            },
        },
    )
    assert launched.status_code == 201, launched.text
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    assert any(path.startswith("/message/sendMedia/") for _, path in _fake_evolution)


def test_ai_campaign_requires_approval_before_send(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _ready(client, headers)
    credit_book.allocate(session, units=2, note="seed", idempotency_key="alloc-ai")
    session.commit()
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110071", "marketing_whatsapp_opt_in": True},
    )
    generated = client.post("/api/v1/reach/ai/generate", headers=headers, json={"objective": "announcement"})
    assert generated.status_code == 200, generated.text
    assert generated.json()["origin"] == "ai"
    blocked = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": generated.json()["title"],
            "origin": "ai",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": generated.json()["body"], "subject": "AI"}},
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "approval_required"
    draft = client.post(
        "/api/v1/reach/campaigns",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "name": generated.json()["title"],
            "origin": "ai",
            "mode": "draft",
            "channels": ["whatsapp"],
            "audience": {},
            "content": {"whatsapp": {"body": generated.json()["body"], "subject": "AI"}},
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["status"] == "draft"
    campaign_id = draft.json()["id"]
    changed = client.post(
        f"/api/v1/reach/campaigns/{campaign_id}/revise",
        headers=headers,
        json={"content": {"whatsapp": {"body": "A reviewed message for you", "subject": "AI"}}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["content_version"] == 2
    sent = client.post(f"/api/v1/reach/campaigns/{campaign_id}/approve-and-send", headers=headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()["queued_count"] == 1
    again = client.post(f"/api/v1/reach/campaigns/{campaign_id}/approve-and-send", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == campaign_id
    queued = client.get("/api/v1/messaging/outbox", headers=headers, params={"status": "QUEUED"}).json()
    assert len([row for row in queued if row["template_key"] == "campaign"]) == 1


def _webhook_key(session) -> str:
    from app.models.reach import ReachConnection

    row = session.scalar(select(ReachConnection))
    assert row is not None
    return row.webhook_key
