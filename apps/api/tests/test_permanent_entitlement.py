"""Permanent entitlement issuance. The signing seed is the public RFC 8032 test vector, not a deployment key."""

import base64
import json
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import create_engine, func, inspect, select, text  # noqa: TID251
from sqlalchemy.orm import Session
from tests.test_inventory import DT, admin, seed

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.services.entitlement_service import thumbprint

# RFC 8032 section 7.1 TEST 1. Not a production signing key.
RFC_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")


@pytest.fixture(autouse=True)
def signing_key() -> None:
    settings = get_settings()
    settings.entitlement_signing_seed = base64.b64encode(RFC_SEED).decode("ascii")
    settings.entitlement_signing_key_id = "o2-test"
    yield
    settings.entitlement_signing_seed = ""
    settings.entitlement_signing_key_id = ""


def _public_b64() -> tuple[str, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    return base64.b64encode(public).decode("ascii"), public


def _register(client, headers, code: str = "E2") -> str:
    created = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": DT, "code": code, "name": "Entitlement"},
    )
    assert created.status_code == 201, created.text
    return created.json()["device"]["id"]


def _activation_key(client, headers, device_id: str) -> str:
    issued = client.post(f"/api/v1/devices/{device_id}/activation-key", headers=headers)
    assert issued.status_code == 201, issued.text
    return issued.json()["activation_key"]


def _verify(body: dict, public: bytes) -> dict:
    signed = body["entitlement"]
    assert signed["key_id"] == "o2-test"
    assert signed["schema_version"] == 1
    payload = signed["payload"]
    Ed25519PublicKey.from_public_bytes(Ed25519PrivateKey.from_private_bytes(RFC_SEED).public_key().public_bytes_raw()).verify(
        base64.b64decode(signed["signature"]),
        payload.encode("utf-8"),
    )
    document = json.loads(payload)
    assert document["permanent"] is True
    assert "expires_at" not in document
    assert document["device_public_key_thumbprint"] == thumbprint(public)
    assert document["subscription_status"] == "informational"
    assert document["branch_id"] == body["store_id"]
    assert document["terminal_id"] == body["register_id"]
    assert document["tenant_id"] == body["tenant_id"]
    return document


def test_activation_signs_a_permanent_entitlement_and_hides_the_seed(client, session: Session) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    public_b64, public = _public_b64()
    before = int(session.scalar(select(func.count()).select_from(Device)) or 0)
    activated = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _activation_key(client, headers, device_id), "device_public_key": public_b64},
    )
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert get_settings().entitlement_signing_seed not in activated.text
    assert RFC_SEED.hex() not in activated.text
    document = _verify(body, public)
    assert int(session.scalar(select(func.count()).select_from(Device)) or 0) == before
    session.expire_all()
    device = session.get(Device, uuid.UUID(device_id))
    assert device is not None
    assert device.device_public_key_thumbprint == document["device_public_key_thumbprint"]
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "device.entitlement"))
    assert entry is not None
    assert "signature" not in json.dumps(entry.new_values)
    me = client.get("/api/v1/devices/me", headers={"X-Terminal-Token": body["device_token"]})
    assert me.status_code == 200, me.text


def test_repeat_issuance_keeps_the_terminal_and_rejects_a_different_device_key(client, session: Session) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers, "E3")
    public_b64, public = _public_b64()
    other_b64, _other = _public_b64()
    activated = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _activation_key(client, headers, device_id), "device_public_key": public_b64},
    )
    assert activated.status_code == 200, activated.text
    token = activated.json()["device_token"]
    again = client.post(
        "/api/v1/terminals/entitlement",
        headers={"X-Terminal-Token": token},
        json={"device_public_key": public_b64},
    )
    assert again.status_code == 200, again.text
    second = json.loads(again.json()["payload"])
    first = json.loads(activated.json()["entitlement"]["payload"])
    assert second["terminal_id"] == first["terminal_id"]
    assert second["entitlement_id"] != first["entitlement_id"]
    assert second["device_public_key_thumbprint"] == thumbprint(public)
    clash = client.post(
        "/api/v1/terminals/entitlement",
        headers={"X-Terminal-Token": token},
        json={"device_public_key": other_b64},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "device_binding"
    session.expire_all()
    device = session.get(Device, uuid.UUID(device_id))
    assert device is not None
    assert device.device_public_key_thumbprint == thumbprint(public)


def test_a_new_activation_key_is_the_only_rebind(client, session: Session) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers, "E4")
    first_b64, first = _public_b64()
    second_b64, second = _public_b64()
    client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _activation_key(client, headers, device_id), "device_public_key": first_b64},
    )
    rebound = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _activation_key(client, headers, device_id), "device_public_key": second_b64},
    )
    assert rebound.status_code == 200, rebound.text
    document = _verify(rebound.json(), second)
    assert document["device_public_key_thumbprint"] != thumbprint(first)
    session.expire_all()
    device = session.get(Device, uuid.UUID(device_id))
    assert device is not None
    assert device.device_public_key_thumbprint == thumbprint(second)


def test_unsigned_requests_and_a_missing_signing_key_fail_closed(client) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers, "E5")
    public_b64, _public = _public_b64()
    missing = client.post("/api/v1/terminals/entitlement", json={"device_public_key": public_b64})
    assert missing.status_code == 401
    key = _activation_key(client, headers, device_id)
    settings = get_settings()
    settings.entitlement_signing_seed = ""
    refused = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": key, "device_public_key": public_b64},
    )
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "entitlement_unconfigured"
    settings.entitlement_signing_seed = base64.b64encode(RFC_SEED).decode("ascii")
    restored = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": key, "device_public_key": public_b64},
    )
    assert restored.status_code == 200, restored.text


def test_entitlement_issuance_is_rate_limited(client) -> None:
    for _ in range(10):
        response = client.post("/api/v1/terminals/entitlement", json={"device_public_key": "aa"})
        assert response.status_code == 401
    blocked = client.post("/api/v1/terminals/entitlement", json={"device_public_key": "aa"})
    assert blocked.status_code == 429


def test_throwaway_sqlite_can_add_the_thumbprint_column(tmp_path: Path) -> None:
    path = tmp_path / "o2-entitlement.sqlite"
    engine = create_engine(f"sqlite:///{path}")
    assert engine.url.drivername == "sqlite"
    assert "inventory" not in str(path).lower()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE devices (id VARCHAR(36) NOT NULL)"))
        connection.execute(text("ALTER TABLE devices ADD COLUMN device_public_key_thumbprint VARCHAR(64)"))
    columns = {column["name"] for column in inspect(engine).get_columns("devices")}
    assert "device_public_key_thumbprint" in columns
    engine.dispose()
    revision_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261122_0124_device_entitlement.py"
    revision = revision_path.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20261121_0123"' in revision
    assert "inventory_levels" not in revision
    assert "stock_movements" not in revision
