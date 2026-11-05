"""Delivery Integrations stays on the existing channel path and refuses unapproved marketplaces."""

import uuid

from app.core import capabilities as catalog
from app.models.delivery import DeliveryConnection
from app.tenancy.scoping import INCLUDE_ALL
from wholesale_support import STORE, admin, device, seed

FOOD = [item.value for item in catalog.compatible("restaurant")]


def _enable(client, headers, capabilities: list[str] | None = None, profile: str = "restaurant"):
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": profile, "capabilities": capabilities if capabilities is not None else FOOD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _connection(client, headers, provider: str = "generic") -> dict:
    created = client.post(
        "/api/v1/delivery/connections",
        headers=headers,
        json={"provider": provider, "market": "AE", "store_id": STORE},
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_addon_off_and_non_food_are_rejected(client) -> None:
    seed(client)
    headers, _ = admin(client)
    blocked = client.get("/api/v1/delivery/providers", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "capability_disabled"

    grocery = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "grocery", "capabilities": ["loyalty", "delivery_integrations"]},
    )
    assert grocery.status_code == 422
    assert grocery.json()["error"]["code"] == "module_not_available"
    still = client.get("/api/v1/delivery/providers", headers=headers)
    assert still.status_code == 403
    assert still.json()["error"]["code"] == "capability_disabled"


def test_catalogue_hides_unapproved_providers_and_generic_links_one_channel(client) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    listed = client.get("/api/v1/delivery/providers", headers=headers)
    assert listed.status_code == 200, listed.text
    by_code = {item["code"]: item for item in listed.json()}
    assert by_code["generic"]["status"] == "available"
    assert by_code["talabat"]["status"] == "awaiting_partner"
    assert by_code["talabat"]["capabilities"] == []
    assert by_code["deliverect"]["status"] == "awaiting_partner"

    first = _connection(client, headers)
    again = _connection(client, headers)
    assert again["id"] == first["id"]
    assert len(client.get("/api/v1/delivery/connections", headers=headers).json()) == 1

    waiting = _connection(client, headers, "talabat")
    refused = client.post(f"/api/v1/delivery/connections/{waiting['id']}/activate", headers=headers)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "provider_unavailable"
    assert client.get("/api/v1/channels", headers=headers).json() == []

    activated = client.post(f"/api/v1/delivery/connections/{first['id']}/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert body["status"] == "active"
    assert body["webhook_secret"]
    assert body["webhook_path"]
    repeat = client.post(f"/api/v1/delivery/connections/{first['id']}/activate", headers=headers)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["webhook_secret"] is None
    assert repeat.json()["channel_id"] == body["channel_id"]
    channels = client.get("/api/v1/channels", headers=headers).json()
    assert len(channels) == 1
    assert channels[0]["is_active"] is True

    paused = client.post(f"/api/v1/delivery/connections/{first['id']}/pause", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    assert client.get("/api/v1/channels", headers=headers).json()[0]["is_active"] is False


def test_turning_the_addon_off_keeps_the_connection(client) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    created = _connection(client, headers)
    activated = client.post(f"/api/v1/delivery/connections/{created['id']}/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    preset = [item.value for item in catalog.PROFILES["restaurant"]] + ["delivery_channels"]
    _enable(client, headers, preset)
    hidden = client.get("/api/v1/delivery/connections", headers=headers)
    assert hidden.status_code == 403
    assert client.get("/api/v1/channels", headers=headers).json()[0]["is_active"] is False
    _enable(client, headers)
    visible = client.get("/api/v1/delivery/connections", headers=headers)
    assert visible.status_code == 200, visible.text
    assert [item["id"] for item in visible.json()] == [created["id"]]
    assert visible.json()[0]["status"] == "paused"


def test_another_tenant_and_a_cashier_cannot_read_a_connection(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _connection(client, headers)
    foreign = uuid.uuid4()
    session.info[INCLUDE_ALL] = True
    session.add(
        DeliveryConnection(
            id=foreign,
            tenant_id=uuid.uuid4(),
            provider_code="generic",
            market="AE",
            store_id=uuid.UUID(STORE),
            status="draft",
        )
    )
    session.commit()
    session.info.pop(INCLUDE_ALL, None)
    visible = client.get("/api/v1/delivery/connections", headers=headers)
    assert visible.status_code == 200, visible.text
    assert str(foreign) not in {item["id"] for item in visible.json()}
    denied = client.post(f"/api/v1/delivery/connections/{foreign}/test", headers=headers)
    assert denied.status_code == 404

    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    cashier_headers = {"Authorization": f"Bearer {cashier.json()['access_token']}"}
    blocked = client.get("/api/v1/delivery/providers", headers=cashier_headers)
    assert blocked.status_code == 403
