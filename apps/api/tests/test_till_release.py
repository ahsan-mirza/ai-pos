"""Releasing a till retires its credential and frees the package seat. History stays."""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.document_sequence import DocumentSequence
from app.models.sale import Sale
from app.models.shift import CashMovement
from wholesale_support import CABLE, STORE, admin, device, event, line, recent_occurred_at, sale, seed

RFC_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")


def _cap_one(resource: str) -> int | None:
    return 1 if resource == "registers" else None


def _public() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    return base64.b64encode(raw).decode("ascii")


def _create(client, headers, code: str) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": code, "name": f"Till {code}"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["device"]["activation_status"] == "pending"
    assert body["device"]["machine_name"] is None
    return body["key"], body["device"]


@pytest.fixture
def signing_key() -> None:
    settings = get_settings()
    settings.entitlement_signing_seed = base64.b64encode(RFC_SEED).decode("ascii")
    settings.entitlement_signing_key_id = "till-release-test"
    yield
    settings.entitlement_signing_seed = ""
    settings.entitlement_signing_key_id = ""


def test_release_frees_the_seat_and_keeps_history(client, session: Session, monkeypatch) -> None:
    seed(client)
    headers, user_id = admin(client)
    monkeypatch.setattr("app.console.plan_limits.limit_value", _cap_one)
    key, till = _create(client, headers, "REL1")
    invoice = "DT-01-REL1-000001"
    pushed = client.post(
        "/api/v1/sync/push",
        headers={"X-Api-Key": key},
        json={
            "device_id": "REL1",
            "events": [
                event(
                    "rel-sale",
                    "sale",
                    sale([line(CABLE, 1, 1500)], invoice_number=invoice),
                    occurred_at=recent_occurred_at(),
                )
            ],
        },
    )
    assert pushed.status_code == 200, pushed.text
    sales_before = int(session.scalar(select(func.count()).select_from(Sale)) or 0)
    cash_before = int(session.scalar(select(func.count()).select_from(CashMovement)) or 0)
    sequence = session.scalar(select(DocumentSequence).where(DocumentSequence.prefix == "DT-01-REL1"))
    assert sequence is not None and sequence.last_value == 1

    blocked = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": "REL2", "name": "Replacement"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "plan_limit"
    assert "Delete an existing till or upgrade the package" in blocked.json()["error"]["message"]
    full = client.get("/api/v1/devices/capacity", headers=headers)
    assert full.status_code == 200
    assert full.json() == {"used": 1, "limit": 1, "available": 0}

    reported = client.get("/api/v1/settings", headers={"X-Api-Key": key, "X-Pending-Sales": "2"})
    assert reported.status_code == 200, reported.text
    waiting = client.post(f"/api/v1/devices/{till['id']}/release", headers=headers)
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "pending_offline"
    assert "Sync it before releasing" in waiting.json()["error"]["message"]
    session.expire_all()
    assert session.get(Device, uuid.UUID(till["id"])).revoked_at is None
    assert int(session.scalar(select(func.count()).select_from(Sale)) or 0) == sales_before

    cleared = client.get("/api/v1/settings", headers={"X-Api-Key": key, "X-Pending-Sales": "0"})
    assert cleared.status_code == 200, cleared.text
    released = client.post(f"/api/v1/devices/{till['id']}/release", headers=headers)
    assert released.status_code == 200, released.text
    assert released.json()["revoked_at"] is not None
    assert released.json()["activation_status"] == "revoked"
    assert released.json()["last_invoice_value"] == 1
    assert client.get("/api/v1/devices/me", headers={"X-Api-Key": key}).status_code == 401

    session.expire_all()
    assert int(session.scalar(select(func.count()).select_from(Sale)) or 0) == sales_before
    assert int(session.scalar(select(func.count()).select_from(CashMovement)) or 0) == cash_before
    kept = session.scalar(select(DocumentSequence).where(DocumentSequence.prefix == "DT-01-REL1"))
    assert kept is not None and kept.last_value == 1
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "device.release"))
    assert entry is not None
    assert entry.user_id == uuid.UUID(user_id)
    assert entry.store_id == uuid.UUID(STORE)
    assert entry.occurred_at is not None

    opened = client.get("/api/v1/devices/capacity", headers=headers)
    assert opened.json()["available"] == 1
    _, replacement = _create(client, headers, "REL2")
    assert replacement["invoice_prefix"] == "DT-01-REL2"
    again = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": "REL3", "name": "Over the cap"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "plan_limit"

    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    denied = client.post(
        f"/api/v1/devices/{replacement['id']}/release",
        headers={"Authorization": f"Bearer {cashier.json()['access_token']}"},
    )
    assert denied.status_code == 403
    revived = client.post(f"/api/v1/devices/{till['id']}/rotate", headers=headers)
    assert revived.status_code == 409
    assert revived.json()["error"]["code"] == "plan_limit"
    session.expire_all()
    assert session.get(Device, uuid.UUID(till["id"])).revoked_at is not None


def test_a_revoked_key_and_a_copied_device_identity_are_rejected(client, session: Session, signing_key) -> None:
    del signing_key
    seed(client)
    headers, _user = admin(client)
    _key, till = _create(client, headers, "OLD1")
    first_key = client.post(f"/api/v1/devices/{till['id']}/activation-key", headers=headers)
    assert first_key.status_code == 201, first_key.text
    public_old = _public()
    activated = client.post(
        "/api/v1/terminals/activate",
        json={
            "activation_key": first_key.json()["activation_key"],
            "machine_name": "Old counter",
            "device_public_key": public_old,
        },
    )
    assert activated.status_code == 200, activated.text
    old_token = activated.json()["device_token"]
    assert activated.json()["register_id"] == till["id"]
    assert activated.json()["store_id"] == STORE
    me = client.get("/api/v1/devices/me", headers={"X-Terminal-Token": old_token})
    assert me.status_code == 200, me.text

    reported = client.get("/api/v1/settings", headers={"X-Terminal-Token": old_token, "X-Pending-Sales": "1"})
    assert reported.status_code == 200, reported.text
    second_key = client.post(f"/api/v1/devices/{till['id']}/activation-key", headers=headers)
    assert second_key.status_code == 201, second_key.text
    held = second_key.json()["activation_key"]
    blocked = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": held, "machine_name": "Replacement", "device_public_key": _public()},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "pending_offline"
    cleared = client.get("/api/v1/settings", headers={"X-Terminal-Token": old_token, "X-Pending-Sales": "0"})
    assert cleared.status_code == 200, cleared.text

    released = client.post(f"/api/v1/devices/{till['id']}/release", headers=headers)
    assert released.status_code == 200, released.text
    reused = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": held, "machine_name": "Replacement", "device_public_key": _public()},
    )
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "activation_invalid"
    assert client.get("/api/v1/devices/me", headers={"X-Terminal-Token": old_token}).status_code == 401

    _replacement_key, replacement = _create(client, headers, "NEW1")
    fresh = client.post(f"/api/v1/devices/{replacement['id']}/activation-key", headers=headers)
    assert fresh.status_code == 201, fresh.text
    copied = client.post(
        "/api/v1/terminals/activate",
        json={
            "activation_key": fresh.json()["activation_key"],
            "machine_name": "Copied identity",
            "device_public_key": public_old,
        },
    )
    assert copied.status_code == 409
    assert copied.json()["error"]["code"] == "device_binding"
    public_new = _public()
    bound = client.post(
        "/api/v1/terminals/activate",
        json={
            "activation_key": fresh.json()["activation_key"],
            "machine_name": "New counter",
            "device_public_key": public_new,
        },
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["register_id"] == replacement["id"]
    assert bound.json()["register_code"] == "NEW1"
    new_token = bound.json()["device_token"]
    seen = client.get("/api/v1/devices/me", headers={"X-Terminal-Token": new_token})
    assert seen.status_code == 200, seen.text
    listing = client.get("/api/v1/devices", headers=headers)
    assert listing.status_code == 200, listing.text
    by_code = {row["code"]: row for row in listing.json()}
    assert by_code["OLD1"]["activation_status"] == "revoked"
    assert by_code["OLD1"]["machine_name"] == "Old counter"
    assert by_code["NEW1"]["activation_status"] == "active"
    assert by_code["NEW1"]["machine_name"] == "New counter"
    session.expire_all()
    old = session.get(Device, uuid.UUID(till["id"]))
    assert old is not None and old.revoked_at is not None
    assert old.device_public_key_thumbprint is not None
    current = session.get(Device, uuid.UUID(replacement["id"]))
    assert current is not None and current.revoked_at is None
    assert current.device_public_key_thumbprint != old.device_public_key_thumbprint


def test_delete_frees_the_seat_and_the_till_code(client, session: Session, monkeypatch) -> None:
    seed(client)
    headers, user_id = admin(client)
    monkeypatch.setattr("app.console.plan_limits.limit_value", _cap_one)
    key, till = _create(client, headers, "DEL1")
    invoice = "DT-01-DEL1-000001"
    pushed = client.post(
        "/api/v1/sync/push",
        headers={"X-Api-Key": key},
        json={
            "device_id": "DEL1",
            "events": [
                event(
                    "del-sale",
                    "sale",
                    sale([line(CABLE, 1, 1500)], invoice_number=invoice),
                    occurred_at=recent_occurred_at(),
                )
            ],
        },
    )
    assert pushed.status_code == 200, pushed.text
    sales_before = int(session.scalar(select(func.count()).select_from(Sale)) or 0)
    blocked = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": "DEL2", "name": "Needs a free seat"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "plan_limit"

    reported = client.get("/api/v1/settings", headers={"X-Api-Key": key, "X-Pending-Sales": "1"})
    assert reported.status_code == 200, reported.text
    waiting = client.post(f"/api/v1/devices/{till['id']}/delete", headers=headers)
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "pending_offline"

    cleared = client.get("/api/v1/settings", headers={"X-Api-Key": key, "X-Pending-Sales": "0"})
    assert cleared.status_code == 200, cleared.text
    deleted = client.post(f"/api/v1/devices/{till['id']}/delete", headers=headers)
    assert deleted.status_code == 200, deleted.text
    listed = client.get("/api/v1/devices", headers=headers)
    assert listed.status_code == 200
    assert all(item["id"] != till["id"] for item in listed.json())
    opened = client.get("/api/v1/devices/capacity", headers=headers)
    assert opened.json()["available"] == 1

    session.expire_all()
    kept = session.get(Device, uuid.UUID(till["id"]))
    assert kept is not None and kept.deleted_at is not None and kept.revoked_at is not None
    assert kept.code != "DEL1"
    assert int(session.scalar(select(func.count()).select_from(Sale)) or 0) == sales_before
    sequence = session.scalar(select(DocumentSequence).where(DocumentSequence.prefix == "DT-01-DEL1"))
    assert sequence is not None and sequence.last_value == 1
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "device.delete"))
    assert entry is not None and entry.user_id == uuid.UUID(user_id)

    _, replacement = _create(client, headers, "DEL1")
    assert replacement["invoice_prefix"] == "DT-01-DEL1"
    over = client.post(
        "/api/v1/devices",
        headers=headers,
        json={"store_id": STORE, "code": "DEL2", "name": "Over the cap"},
    )
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "plan_limit"
    gone = client.post(f"/api/v1/devices/{till['id']}/activation-key", headers=headers)
    assert gone.status_code == 404


def test_an_offline_till_is_not_marked_active(client, session: Session) -> None:
    seed(client)
    headers, _user = admin(client)
    _key, till = _create(client, headers, "OFF1")
    row = session.get(Device, uuid.UUID(till["id"]))
    assert row is not None
    row.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    session.commit()
    listed = client.get("/api/v1/devices", headers=headers)
    found = next(item for item in listed.json() if item["id"] == till["id"])
    assert found["activation_status"] == "offline"
