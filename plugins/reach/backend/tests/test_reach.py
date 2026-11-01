"""AxizReach is one add-on. Campaigns queue onto the existing outbox and never return secrets."""

import uuid

from sqlalchemy import func, select

from app.core.capabilities import Capability
from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.reach import ReachUsage
from wholesale_support import admin, seed


def _enable(client, headers: dict[str, str]) -> None:
    current = client.get("/api/v1/settings", headers=headers)
    assert current.status_code == 200, current.text
    body = current.json()
    capabilities = list(dict.fromkeys([*body["capabilities"], "axiz_reach"]))
    updated = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": body["business_profile"], "capabilities": capabilities},
    )
    assert updated.status_code == 200, updated.text
    assert "axiz_reach" in updated.json()["capabilities"]


def _channel(client, headers: dict[str, str], channel: str, enabled: bool, secret: str | None = None) -> dict:
    saved = client.put(
        "/api/v1/reach/channels",
        headers=headers,
        json={"channel": channel, "enabled": enabled, "provider": "log", "public_config": {}, "secret": secret},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _campaign(name: str, channels: list[str], key: str | None = None) -> dict:
    return {
        "idempotency_key": key or str(uuid.uuid4()),
        "name": name,
        "channels": channels,
        "audience": {},
        "content": {channel: {"body": "Hello {{customer_name}}", "subject": name} for channel in channels},
    }


def test_reach_is_one_addon_and_does_not_sell_channels_separately() -> None:
    assert Capability.AXIZ_REACH.value == "axiz_reach"
    assert not any(item.value in {"whatsapp", "sms", "email"} for item in Capability)


def test_campaigns_need_the_addon_consent_and_an_enabled_channel(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    blocked = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Early", ["whatsapp"]))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "addon_required"

    _enable(client, headers)
    secret = "tenant-whatsapp-token-91"
    whatsapp = _channel(client, headers, "whatsapp", True, secret)
    assert whatsapp["secret_set"] is True
    assert whatsapp["secret_hint"].endswith("n-91")
    listed = client.get("/api/v1/reach/channels", headers=headers).json()
    raw = str(listed)
    assert secret not in raw
    _channel(client, headers, "sms", False)
    _channel(client, headers, "email", True)

    sms_only = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Texts", ["sms"]))
    assert sms_only.status_code == 422
    assert sms_only.json()["error"]["code"] == "channel_disabled"

    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Noor", "phone": "+971501110000"},
    )
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Rania", "phone": "+971501110002", "whatsapp_opt_in": True},
    )
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "phone": "+971501110001", "marketing_whatsapp_opt_in": True},
    )
    key = str(uuid.uuid4())
    first = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Hello", ["whatsapp"], key))
    assert first.status_code == 201, first.text
    assert first.json()["queued_count"] == 1
    assert first.json()["suppressed_count"] >= 1
    replay = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Hello", ["whatsapp"], key))
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    queued = client.get("/api/v1/messaging/outbox", headers=headers, params={"status": "QUEUED"}).json()
    assert len([row for row in queued if row["template_key"] == "campaign"]) == 1
    assert all(row["status"] == "QUEUED" for row in queued)

    client.put(
        "/api/v1/messaging/settings",
        headers=headers,
        json={"providers": {"whatsapp": "whatsapp_cloud"}},
    )
    client.put("/api/v1/reach/prices", headers=headers, json={"whatsapp": 25, "sms": 10, "email": 5})
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    usage = session.scalar(select(func.count()).select_from(ReachUsage))
    assert usage == 1
    overview = client.get("/api/v1/reach/overview", headers=headers).json()
    assert overview["sent"] == 1
    assert overview["usage_cents"] == 25
    assert overview["by_channel"]["whatsapp"] == 1
    assert overview["by_channel"]["email"] == 0
    assert overview["transactional_cents"] == 0


def test_starter_kit_configures_providers_and_keeps_receipts_without_the_addon(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    secret = "starter-whatsapp-token"
    saved = _channel(client, headers, "whatsapp", True, secret)
    assert saved["status"] == "connected"
    assert secret not in str(saved)
    blocked = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Promo", ["whatsapp"]))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "addon_required"

    keen = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "phone": "+971501110009", "whatsapp_opt_in": True},
    ).json()
    from app.models.customer import Customer
    from app.services import messaging_service

    messaging_service.enqueue(
        session,
        template_key="statement",
        customer=session.get(Customer, uuid.UUID(keen["id"])),
        context={"business": "AI POS", "balance": "AED 1.00", "overdue": "AED 0.00"},
        dedupe_key=f"statement:{keen['id']}",
    )
    session.commit()
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    sent = client.get("/api/v1/messaging/outbox", headers=headers, params={"status": "SENT"}).json()
    assert any(row["template_key"] == "statement" for row in sent)


def test_turning_reach_off_pauses_a_queued_campaign_and_leaves_the_channel(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _channel(client, headers, "whatsapp", True)
    client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "phone": "+971501110003", "marketing_whatsapp_opt_in": True},
    )
    launched = client.post("/api/v1/reach/campaigns", headers=headers, json=_campaign("Later", ["whatsapp"]))
    assert launched.status_code == 201, launched.text
    assert launched.json()["queued_count"] == 1
    current = client.get("/api/v1/settings", headers=headers).json()
    without = [item for item in current["capabilities"] if item != "axiz_reach"]
    removed = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": current["business_profile"], "capabilities": without},
    )
    assert removed.status_code == 200, removed.text
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    still = client.get("/api/v1/messaging/outbox", headers=headers, params={"status": "QUEUED"}).json()
    assert any(row["template_key"] == "campaign" for row in still)
    kept = client.get("/api/v1/reach/channels", headers=headers).json()
    whatsapp = next(row for row in kept if row["channel"] == "whatsapp")
    assert whatsapp["enabled"] is True
    _enable(client, headers)
    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    sent = client.get("/api/v1/messaging/outbox", headers=headers, params={"status": "SENT"}).json()
    assert any(row["template_key"] == "campaign" for row in sent)
