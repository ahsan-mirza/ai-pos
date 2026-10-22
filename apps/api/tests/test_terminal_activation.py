from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from tests.test_inventory import DT, admin, seed

from app.models.device import DeviceActivation


def _register(client, headers) -> str:
    created = client.post("/api/v1/devices", headers=headers, json={"store_id": DT, "code": "R9", "name": "Till 9"})
    assert created.status_code == 201, created.text
    return created.json()["device"]["id"]


def _key(client, headers, device_id: str) -> str:
    issued = client.post(f"/api/v1/devices/{device_id}/activation-key", headers=headers)
    assert issued.status_code == 201, issued.text
    body = issued.json()
    assert len(body["activation_key"]) == 14 and body["activation_key"].count("-") == 2
    return body["activation_key"]


def test_activation_key_is_exchanged_once_for_a_terminal_token(client) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    key = _key(client, headers, device_id)

    activated = client.post(
        "/api/v1/terminals/activate", json={"activation_key": key.lower(), "machine_name": "FRONT-PC"}
    )
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert body["register_id"] == device_id
    assert body["store_id"] == DT
    assert body["register_code"] == "R9"
    token = body["device_token"]

    me = client.get("/api/v1/devices/me", headers={"X-Terminal-Token": token})
    assert me.status_code == 200, me.text
    assert me.json()["code"] == "R9"

    again = client.post("/api/v1/terminals/activate", json={"activation_key": key})
    assert again.status_code == 401
    assert again.json()["error"]["code"] == "activation_invalid"


def test_new_key_cancels_the_old_one_and_expired_keys_fail(client, session) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    first = _key(client, headers, device_id)
    second = _key(client, headers, device_id)
    assert client.post("/api/v1/terminals/activate", json={"activation_key": first}).status_code == 401

    session.execute(update(DeviceActivation).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    session.commit()
    expired = client.post("/api/v1/terminals/activate", json={"activation_key": second})
    assert expired.status_code == 401


def test_activation_rotates_the_previous_device_key(client) -> None:
    seed(client)
    headers = admin(client)
    created = client.post("/api/v1/devices", headers=headers, json={"store_id": DT, "code": "R8", "name": "Till 8"})
    old_key = created.json()["key"]
    device_id = created.json()["device"]["id"]
    assert client.get("/api/v1/devices/me", headers={"X-Api-Key": old_key}).status_code == 200

    token = client.post("/api/v1/terminals/activate", json={"activation_key": _key(client, headers, device_id)}).json()[
        "device_token"
    ]
    assert client.get("/api/v1/devices/me", headers={"X-Api-Key": old_key}).status_code == 401
    assert client.get("/api/v1/devices/me", headers={"X-Terminal-Token": token}).status_code == 200
