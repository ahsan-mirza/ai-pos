"""Permanent entitlement issuance. Uses the in-memory SQLite suite, not a protected database."""

import base64
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import select
from tests.test_inventory import admin, seed
from tests.test_terminal_activation import _key, _register

from app.core.config import get_settings
from app.models.audit_log import AuditLog

SEED = bytes([7]) * 32
KEY_ID = "o2-test-1"


def _configure(monkeypatch: pytest.MonkeyPatch, present: bool) -> None:
    if present:
        monkeypatch.setenv("ENTITLEMENT_SIGNING_SEED", base64.b64encode(SEED).decode("ascii"))
        monkeypatch.setenv("ENTITLEMENT_SIGNING_KEY_ID", KEY_ID)
    else:
        monkeypatch.delenv("ENTITLEMENT_SIGNING_SEED", raising=False)
        monkeypatch.delenv("ENTITLEMENT_SIGNING_KEY_ID", raising=False)
    get_settings.cache_clear()


def _device_public() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def test_activation_issues_a_signed_permanent_entitlement(client, session, monkeypatch) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    _configure(monkeypatch, True)
    public = _device_public()
    try:
        activated = client.post(
            "/api/v1/terminals/activate",
            json={
                "activation_key": _key(client, headers, device_id),
                "machine_name": "O2-TILL",
                "device_public_key": public,
            },
        )
        assert activated.status_code == 200, activated.text
        body = activated.json()
        signed = body["entitlement"]
        assert signed["key_id"] == KEY_ID
        assert SEED.hex() not in activated.text
        assert base64.b64encode(SEED).decode("ascii") not in activated.text
        payload = json.loads(signed["payload"])
        assert payload["permanent"] is True
        assert payload["capabilities"] == []
        assert payload["terminal_id"] == device_id
        assert payload["branch_id"] == body["store_id"]
        assert payload["tenant_id"] == body["tenant_id"]
        assert "expires_at" not in payload
        Ed25519PrivateKey.from_private_bytes(SEED).public_key().verify(
            base64.b64decode(signed["signature"]),
            signed["payload"].encode("utf-8"),
        )
        tampered = signed["payload"] + " "
        with pytest.raises(InvalidSignature):
            Ed25519PrivateKey.from_private_bytes(SEED).public_key().verify(
                base64.b64decode(signed["signature"]),
                tampered.encode("utf-8"),
            )
        session.expire_all()
        actions = session.scalars(select(AuditLog.action).where(AuditLog.action == "device.entitlement")).all()
        assert "device.entitlement" in actions
        again = client.post(
            "/api/v1/terminals/entitlement",
            headers={"X-Terminal-Token": body["device_token"]},
            json={"device_public_key": _device_public()},
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "device_binding"
    finally:
        get_settings.cache_clear()


def test_missing_signing_key_does_not_consume_the_activation_key(client, monkeypatch) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    activation_key = _key(client, headers, device_id)
    _configure(monkeypatch, False)
    try:
        refused = client.post(
            "/api/v1/terminals/activate",
            json={"activation_key": activation_key, "device_public_key": _device_public()},
        )
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "entitlement_unconfigured"
        assert "device_token" not in refused.text
        _configure(monkeypatch, True)
        accepted = client.post(
            "/api/v1/terminals/activate",
            json={"activation_key": activation_key, "device_public_key": _device_public()},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["entitlement"]["key_id"] == KEY_ID
    finally:
        get_settings.cache_clear()


def test_preflight_reports_a_missing_seed_and_a_matching_desktop_key(client, monkeypatch, tmp_path) -> None:
    seed(client)
    headers = admin(client)
    _configure(monkeypatch, False)
    try:
        missing = client.get("/api/v1/devices/activation-preflight", headers=headers)
        assert missing.status_code == 200, missing.text
        assert missing.json()["ready"] is False
        assert missing.json()["code"] == "entitlement_unconfigured"
        assert "seed" not in missing.text.lower() or "signing" in missing.json()["message"].lower()
        assert SEED.hex() not in missing.text

        public = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode("ascii")
        secret = tmp_path / "seed.txt"
        secret.write_text(base64.b64encode(SEED).decode("ascii"), encoding="utf-8")
        monkeypatch.setenv("ENTITLEMENT_SIGNING_SEED_FILE", str(secret))
        monkeypatch.delenv("ENTITLEMENT_SIGNING_KEY_ID", raising=False)
        monkeypatch.setenv("POS_ENTITLEMENT_KEY_ID", KEY_ID)
        monkeypatch.setenv("POS_ENTITLEMENT_PUBLIC_KEY", public)
        monkeypatch.setenv("POS_ENTITLEMENT_PUBLIC_KEYS", f"{KEY_ID}:{public}")
        get_settings.cache_clear()
        ready = client.get("/api/v1/devices/activation-preflight", headers=headers)
        assert ready.status_code == 200, ready.text
        body = ready.json()
        assert body["ready"] is True
        assert body["key_id"] == KEY_ID
        assert body["public_key"] == public
        assert base64.b64encode(SEED).decode("ascii") not in ready.text
    finally:
        get_settings.cache_clear()


def test_a_desktop_key_mismatch_does_not_consume_the_activation_key(client, monkeypatch) -> None:
    seed(client)
    headers = admin(client)
    device_id = _register(client, headers)
    activation_key = _key(client, headers, device_id)
    _configure(monkeypatch, True)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("POS_ENTITLEMENT_PUBLIC_KEY", base64.b64encode(other).decode("ascii"))
    monkeypatch.setenv("POS_ENTITLEMENT_KEY_ID", KEY_ID)
    get_settings.cache_clear()
    try:
        refused = client.post(
            "/api/v1/terminals/activate",
            json={"activation_key": activation_key, "device_public_key": _device_public()},
        )
        assert refused.status_code == 503
        assert refused.json()["error"]["code"] == "entitlement_key_mismatch"
        assert "device_token" not in refused.text
        monkeypatch.delenv("POS_ENTITLEMENT_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("POS_ENTITLEMENT_KEY_ID", raising=False)
        get_settings.cache_clear()
        accepted = client.post(
            "/api/v1/terminals/activate",
            json={"activation_key": activation_key, "device_public_key": _device_public()},
        )
        assert accepted.status_code == 200, accepted.text
    finally:
        get_settings.cache_clear()


def test_bad_activation_and_anonymous_entitlement_are_refused(client) -> None:
    refused = client.post("/api/v1/terminals/activate", json={"activation_key": "NOT-A-REAL-KEY"})
    assert refused.status_code == 401
    assert "signature" not in refused.text
    anonymous = client.post("/api/v1/terminals/entitlement", json={"device_public_key": _device_public()})
    assert anonymous.status_code == 401
