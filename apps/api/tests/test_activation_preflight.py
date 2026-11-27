"""Activation preflight classifies a till without consuming the one-time key."""

import base64
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.device import DeviceActivation
from app.services.device_service import _hash_activation
from app.tenancy.scoping import DEFAULT_TENANT_ID
from wholesale_support import STORE, admin, seed

RFC_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
OTHER_TENANT = "11111111-1111-4111-8111-111111111111"


def _enable_signing() -> None:
    settings = get_settings()
    settings.entitlement_signing_seed = base64.b64encode(RFC_SEED).decode("ascii")
    settings.entitlement_signing_key_id = "preflight-test"
    public = Ed25519PrivateKey.from_private_bytes(RFC_SEED).public_key().public_bytes_raw()
    encoded = base64.b64encode(public).decode("ascii")
    settings.pos_entitlement_key_id = "preflight-test"
    settings.pos_entitlement_public_key = encoded
    settings.pos_entitlement_public_keys = f"preflight-test:{encoded}"


def _clear_signing() -> None:
    settings = get_settings()
    settings.entitlement_signing_seed = ""
    settings.entitlement_signing_key_id = ""
    settings.pos_entitlement_key_id = ""
    settings.pos_entitlement_public_key = ""
    settings.pos_entitlement_public_keys = ""


def _till(client, headers) -> tuple[str, dict]:
    created = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": "PF1", "name": "Preflight till"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    issued = client.post(f"/api/v1/devices/{body['device']['id']}/activation-key", headers=headers)
    assert issued.status_code == 201, issued.text
    return issued.json()["activation_key"], body["device"]


def _unused(session: Session, key: str) -> None:
    session.expire_all()
    row = session.scalar(select(DeviceActivation).where(DeviceActivation.code_hash == _hash_activation(key)))
    assert row is not None and row.used_at is None


def test_signing_failure_does_not_consume_the_key_and_retry_succeeds(client, session: Session) -> None:
    seed(client)
    headers, _user = admin(client)
    key, _device = _till(client, headers)
    _clear_signing()
    looked = client.post(
        "/api/v1/terminals/activation-preflight",
        json={"activation_key": key, "local": {}},
    )
    assert looked.status_code == 200, looked.text
    body = looked.json()
    assert body["blocked"] is True
    assert body["code"] == "entitlement_unconfigured"
    assert "Contact your administrator." in body["message"]
    assert body["signing_ready"] is False
    assert "seed" not in looked.text.lower()
    device_key = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")
    refused = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": key, "device_public_key": device_key},
    )
    assert refused.status_code == 503
    assert refused.json()["error"]["code"] == "entitlement_unconfigured"
    _unused(session, key)
    _enable_signing()
    try:
        public = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode("ascii")
        accepted = client.post(
            "/api/v1/terminals/activate",
            json={"activation_key": key, "device_public_key": public},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["entitlement"]["key_id"] == "preflight-test"
    finally:
        _clear_signing()


def test_same_store_pending_sales_do_not_block_or_consume_the_key(client, session: Session) -> None:
    seed(client)
    headers, _user = admin(client)
    key, device = _till(client, headers)
    _enable_signing()
    try:
        looked = client.post(
            "/api/v1/terminals/activation-preflight",
            json={
                "store_code": "bayrut",
                "activation_key": key,
                "local": {
                    "tenant_id": str(DEFAULT_TENANT_ID),
                    "store_id": STORE,
                    "register_id": str(uuid.uuid4()),
                    "pending_sales": 1,
                    "pending_cash_movements": 2,
                },
            },
        )
        assert looked.status_code == 200, looked.text
        body = looked.json()
        assert body["same_tenant"] is True
        assert body["same_store"] is True
        assert body["kind"] == "additional_till"
        assert body["blocked"] is False
        assert body["code"] == "pending_same_store"
        assert "Existing store detected" in body["message"]
        assert body["pending_sales"] == 1
        assert body["pending_cash_movements"] == 2
        replacement = client.post(
            "/api/v1/terminals/activation-preflight",
            json={
                "activation_key": key,
                "local": {
                    "tenant_id": str(DEFAULT_TENANT_ID),
                    "store_id": device["store_id"],
                    "register_id": device["id"],
                    "pending_sales": 1,
                },
            },
        )
        assert replacement.status_code == 200, replacement.text
        replacing = replacement.json()
        assert replacing["kind"] == "device_replacement"
        assert replacing["blocked"] is False
        assert "1 sale is waiting to sync" in replacing["message"]
        _unused(session, key)
    finally:
        _clear_signing()


def test_different_store_pending_records_block_without_consuming_the_key(client, session: Session) -> None:
    seed(client)
    headers, _user = admin(client)
    key, _device = _till(client, headers)
    _enable_signing()
    try:
        looked = client.post(
            "/api/v1/terminals/activation-preflight",
            json={
                "activation_key": key,
                "local": {
                    "tenant_id": OTHER_TENANT,
                    "store_id": str(uuid.uuid4()),
                    "register_id": str(uuid.uuid4()),
                    "pending_sales": 1,
                    "pending_returns": 1,
                    "pending_cash_movements": 1,
                },
            },
        )
        assert looked.status_code == 200, looked.text
        body = looked.json()
        assert body["same_tenant"] is False
        assert body["decision"] == "different_store"
        assert body["blocked"] is True
        assert body["code"] == "pending_different_store"
        assert "another store" in body["message"]
        _unused(session, key)
        fresh = client.post(
            "/api/v1/terminals/activation-preflight",
            json={"activation_key": key, "local": {"tenant_id": OTHER_TENANT}},
        )
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["blocked"] is False
        assert fresh.json()["decision"] == "different_store"
    finally:
        _clear_signing()


def test_key_id_mismatch_and_missing_trusted_key_do_not_consume(client, session: Session) -> None:
    seed(client)
    headers, _user = admin(client)
    key, _device = _till(client, headers)
    _enable_signing()
    settings = get_settings()
    settings.entitlement_signing_key_id = "server-only"
    try:
        mismatch = client.post("/api/v1/terminals/activation-preflight", json={"activation_key": key, "local": {}})
        assert mismatch.status_code == 200, mismatch.text
        assert mismatch.json()["blocked"] is True
        assert mismatch.json()["code"] == "entitlement_key_mismatch"
        assert "Contact your administrator." in mismatch.json()["message"]
        assert "seed" not in mismatch.text.lower()
        _unused(session, key)
        settings.entitlement_signing_key_id = "preflight-test"
        settings.pos_entitlement_public_key = ""
        other = base64.b64encode(b"\x11" * 32).decode("ascii")
        settings.pos_entitlement_public_keys = f"other-desktop:{other}"
        missing = client.post("/api/v1/terminals/activation-preflight", json={"activation_key": key, "local": {}})
        assert missing.status_code == 200, missing.text
        assert missing.json()["code"] == "entitlement_key_mismatch"
        _unused(session, key)
        settings.pos_entitlement_public_keys = ""
        settings.entitlement_signing_seed = "not-a-valid-seed"
        invalid = client.post("/api/v1/terminals/activation-preflight", json={"activation_key": key, "local": {}})
        assert invalid.status_code == 200, invalid.text
        assert invalid.json()["code"] == "entitlement_unconfigured"
        _unused(session, key)
    finally:
        _clear_signing()


def test_repeated_activation_checks_report_the_remaining_wait(client) -> None:
    from app.routers.v1 import terminals

    terminals._attempts.clear()
    try:
        for _ in range(terminals.MAX_ATTEMPTS):
            allowed = client.post("/api/v1/terminals/activation-preflight", json={"activation_key": "", "local": {}})
            assert allowed.status_code != 429
        blocked = client.post("/api/v1/terminals/activation-preflight", json={"activation_key": "", "local": {}})
        assert blocked.status_code == 429
        error = blocked.json()["error"]
        assert error["code"] == "too_many_attempts"
        seconds = error["details"]["retry_after_seconds"]
        assert 1 <= seconds <= terminals.WINDOW_SECONDS
        assert error["message"] == terminals.wait_message(seconds)
    finally:
        terminals._attempts.clear()
