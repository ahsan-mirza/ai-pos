"""The locked register may list cashiers for its own branch, and a profile still needs a PIN."""

import uuid

from sqlalchemy import select
from tests.test_auth import API_KEY, CASHIER_ROLE, OTHER_STORE_ID, STORE_ID, admin_token, bearer, seed_stores

from app.core.config import get_settings
from app.core.permissions import CASHIER_ROLE_ID
from app.core.security import hash_pin
from app.models.audit_log import AuditLog
from app.models.user import User

OTHER_TENANT = uuid.UUID("00000000-0000-4000-8000-00000000bb01")
FOREIGN_USER = uuid.UUID("00000000-0000-4000-8000-00000000bb02")


def _names(client, headers: dict[str, str]) -> set[str]:
    response = client.get("/api/v1/auth/cashiers", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "email" not in response.text
    assert "hashed_pin" not in response.text
    assert "username" not in response.text
    return {row["display_name"] for row in body}


def test_directory_lists_only_active_pos_users_and_hides_secrets(client) -> None:
    headers = {"X-Api-Key": API_KEY}
    names = _names(client, headers)
    assert names == {"Front Cashier", "Root Admin"}
    listed = client.get("/api/v1/auth/cashiers", headers=headers).json()
    row = next(item for item in listed if item["display_name"] == "Front Cashier")
    assert row["initials"] == "FC"
    assert row["role_label"] == "Cashier"
    assert row["avatar_url"] is None
    assert set(row) == {"id", "display_name", "initials", "role_label", "avatar_url"}

    token = admin_token(client)
    created = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "portal.only",
            "email": "portal.only@example.com",
            "full_name": "Portal Only",
            "role_id": CASHIER_ROLE,
            "password": "portal-password-1",
            "has_portal_access": True,
            "has_pos_access": False,
        },
    )
    assert created.status_code == 201, created.text
    cashier = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "gone.cashier",
            "email": "gone.cashier@example.com",
            "full_name": "Gone Cashier",
            "role_id": CASHIER_ROLE,
            "pin": "3333",
            "has_pos_access": True,
        },
    )
    assert cashier.status_code == 201, cashier.text
    turned_off = client.patch(
        f"/api/v1/users/{cashier.json()['id']}",
        headers=bearer(token),
        json={"is_active": False},
    )
    assert turned_off.status_code == 200, turned_off.text
    assert "Gone Cashier" not in _names(client, headers)
    assert "Portal Only" not in _names(client, headers)
    assert client.get("/api/v1/auth/cashiers").status_code == 401


def test_bound_register_ignores_a_client_store_and_another_tenant(client, session) -> None:
    seed_stores(client)
    token = admin_token(client)
    here = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "here.cashier",
            "email": "here.cashier@example.com",
            "full_name": "Here Cashier",
            "role_id": CASHIER_ROLE,
            "store_id": STORE_ID,
            "pin": "4444",
            "has_pos_access": True,
        },
    )
    assert here.status_code == 201, here.text
    elsewhere = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "elsewhere.cashier",
            "email": "elsewhere.cashier@example.com",
            "full_name": "Elsewhere Cashier",
            "role_id": CASHIER_ROLE,
            "store_id": OTHER_STORE_ID,
            "pin": "5555",
            "has_pos_access": True,
        },
    )
    assert elsewhere.status_code == 201, elsewhere.text
    session.add(
        User(
            id=FOREIGN_USER,
            username="foreign.cashier",
            email="foreign.cashier@example.com",
            full_name="Foreign Cashier",
            hashed_pin=hash_pin("6666", get_settings()),
            is_active=True,
            role_id=uuid.UUID(CASHIER_ROLE_ID),
            has_pos_access=True,
            has_portal_access=False,
            tenant_id=OTHER_TENANT,
        )
    )
    session.commit()

    device = client.post(
        "/api/v1/devices",
        headers=bearer(token),
        json={"store_id": STORE_ID, "code": "T1", "name": "Till 1"},
    )
    assert device.status_code == 201, device.text
    terminal = {"X-Terminal-Token": device.json()["key"]}

    names = _names(client, terminal)
    assert "Here Cashier" in names
    assert "Front Cashier" in names
    assert "Elsewhere Cashier" not in names
    assert "Foreign Cashier" not in names

    spoofed = client.get(f"/api/v1/auth/cashiers?store_id={OTHER_STORE_ID}", headers=terminal)
    assert spoofed.status_code == 200, spoofed.text
    assert "Elsewhere Cashier" not in {row["display_name"] for row in spoofed.json()}

    unlocked = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": here.json()["id"], "pin": "4444"},
    )
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["scope"] == "pos"
    assert unlocked.json()["user"]["username"] == "here.cashier"

    wrong_pin = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": here.json()["id"], "pin": "0000"},
    )
    assert wrong_pin.status_code == 401
    assert "0000" not in wrong_pin.text
    assert "hashed" not in wrong_pin.text

    other_branch = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": elsewhere.json()["id"], "pin": "5555"},
    )
    assert other_branch.status_code == 401
    assert "access_token" not in other_branch.json()

    foreign = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": str(FOREIGN_USER), "pin": "6666"},
    )
    assert foreign.status_code == 401

    named = client.post(
        "/api/v1/auth/login-pin",
        headers=terminal,
        json={"username": "elsewhere.cashier", "pin": "5555"},
    )
    assert named.status_code == 401

    missing = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": str(uuid.uuid4()), "pin": "4444"},
    )
    assert missing.status_code == 401

    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/unlock",
                headers=terminal,
                json={"user_id": here.json()["id"], "pin": "9999"},
            ).status_code
            == 401
        )
    locked = client.post(
        "/api/v1/auth/unlock",
        headers=terminal,
        json={"user_id": here.json()["id"], "pin": "4444"},
    )
    assert locked.status_code == 423
    assert session.scalars(select(AuditLog).where(AuditLog.action == "auth.login_pin_failed")).first() is not None
