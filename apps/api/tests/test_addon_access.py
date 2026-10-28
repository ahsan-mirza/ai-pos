"""Store administrators assign paid add-ons. The subscription does not open them for every user."""

import uuid
from datetime import UTC, datetime, timedelta

from tests.wholesale_support import admin, device

from app.core.cache import get_value
from app.core.permissions import CASHIER_ROLE_ID, STORE_MANAGER_ROLE_ID
from app.models.addon_access import UserAddonAccess
from app.models.store import Store
from app.services.settings_service import clear_settings_cache, load_settings

GIFT = "gift_cards:manage"


def _purchase(session, *, until: datetime | None = None) -> None:
    row = load_settings(session)
    row.purchased_capabilities = ["gift_cards"]
    row.entitlement_until = until or (datetime.now(UTC) + timedelta(days=30))
    session.commit()
    clear_settings_cache()


def _pin(client, username: str, pin: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-pin", json={"username": username, "pin": pin}, headers=device())
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


def _user(client, headers, **extra) -> dict:
    payload = {
        "username": extra.pop("username"),
        "email": extra.pop("email"),
        "full_name": extra.pop("full_name"),
        "role_id": extra.pop("role_id", CASHIER_ROLE_ID),
        "password": "staff-password-123",
        "pin": extra.pop("pin"),
        "has_pos_access": True,
        "has_portal_access": True,
        "is_active": True,
    }
    payload.update(extra)
    response = client.post("/api/v1/users", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _grant(client, headers, user_id: str, permissions: list[str] | None = None, status: str = "granted") -> None:
    response = client.put(
        "/api/v1/addon-access/assignments",
        headers=headers,
        json={
            "changes": [
                {
                    "user_id": user_id,
                    "module_key": "gift_cards",
                    "status": status,
                    "permissions": [GIFT] if permissions is None else permissions,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text


def _product(client, headers: dict[str, str]):
    return client.get("/api/v1/gift-cards/product", headers=headers)


def test_a_grant_opens_the_add_on_for_one_user_and_a_revoke_leaves_the_other(client, session) -> None:
    _purchase(session)
    headers, _admin_id = admin(client)
    first = _user(
        client, headers, username="cashier2", email="c2@example.com", full_name="Second Cashier", pin="9753"
    )
    denied = _product(client, _pin(client, "cashier", "1357")[0])
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "addon_access_denied"

    _grant(client, headers, first["id"], [GIFT])
    allowed, body = _pin(client, "cashier2", "9753")
    assert "gift_cards" in body["addon_modules"]
    assert _product(client, allowed).status_code == 200
    assert _product(client, _pin(client, "cashier", "1357")[0]).status_code == 403

    _grant(client, headers, first["id"], [], status="revoked")
    assert _product(client, _pin(client, "cashier2", "9753")[0]).status_code == 403
    assert session.query(UserAddonAccess).count() == 1


def test_module_access_without_the_edit_permission_cannot_list_cards(client, session) -> None:
    _purchase(session)
    headers, _ = admin(client)
    role = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "Floor lead", "permissions": ["portal:access", "pos:access"]},
    )
    assert role.status_code == 201, role.text
    person = _user(
        client,
        headers,
        username="viewer",
        email="view@example.com",
        full_name="Viewer",
        pin="8642",
        role_id=role.json()["id"],
    )
    _grant(client, headers, person["id"], [])
    pin_token, body = _pin(client, "viewer", "8642")
    assert GIFT not in body["permissions"]
    assert _product(client, pin_token).status_code == 200
    portal = client.post(
        "/api/v1/auth/login-password", json={"username": "viewer", "password": "staff-password-123"}
    )
    assert portal.status_code == 200, portal.text
    listed = client.get(
        "/api/v1/gift-cards", headers={"Authorization": f"Bearer {portal.json()['access_token']}"}
    )
    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "forbidden"


def test_a_role_grant_is_blocked_by_an_explicit_revoke(client, session) -> None:
    _purchase(session)
    headers, _ = admin(client)
    manager = _user(
        client,
        headers,
        username="manager1",
        email="manager@example.com",
        full_name="Store Manager",
        role_id=STORE_MANAGER_ROLE_ID,
        pin="2222",
    )
    token, body = _pin(client, "manager1", "2222")
    assert "gift_cards" in body["addon_modules"]
    assert _product(client, token).status_code == 200
    _grant(client, headers, manager["id"], [], status="revoked")
    denied = _product(client, _pin(client, "manager1", "2222")[0])
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "addon_access_denied"


def test_a_cashier_cannot_grant_themselves_and_a_manager_stays_in_their_store(client, session) -> None:
    _purchase(session)
    headers, _ = admin(client)
    own = client.put(
        "/api/v1/addon-access/assignments",
        headers=_pin(client, "cashier", "1357")[0],
        json={
            "changes": [
                {
                    "user_id": "00000000-0000-4000-8000-000000000002",
                    "module_key": "gift_cards",
                    "status": "granted",
                    "permissions": [],
                }
            ]
        },
    )
    assert own.status_code == 403

    downtown = Store(id=uuid.uuid4(), code="DT", name="Downtown", currency="AED")
    marina = Store(id=uuid.uuid4(), code="MA", name="Marina", currency="AED")
    session.add_all([downtown, marina])
    session.commit()
    pinned = _user(
        client,
        headers,
        username="pinned",
        email="pinned@example.com",
        full_name="Pinned Manager",
        role_id=STORE_MANAGER_ROLE_ID,
        pin="3333",
        store_id=str(downtown.id),
    )
    other = _user(
        client,
        headers,
        username="marina",
        email="marina@example.com",
        full_name="Marina Cashier",
        pin="4444",
        store_id=str(marina.id),
    )
    manager = client.post("/api/v1/auth/login-password", json={"username": "pinned", "password": "staff-password-123"})
    assert manager.status_code == 200, manager.text
    refused = client.put(
        "/api/v1/addon-access/assignments",
        headers={"Authorization": f"Bearer {manager.json()['access_token']}"},
        json={
            "changes": [
                {"user_id": other["id"], "module_key": "gift_cards", "status": "granted", "permissions": []}
            ]
        },
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "store_scope"
    missing = client.put(
        "/api/v1/addon-access/assignments",
        headers=headers,
        json={
            "changes": [
                {
                    "user_id": str(uuid.uuid4()),
                    "module_key": "gift_cards",
                    "status": "granted",
                    "permissions": [],
                }
            ]
        },
    )
    assert missing.status_code == 404
    assert pinned["store_id"] == str(downtown.id)

    limited = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "Staff admin", "permissions": ["portal:access", "users:read", "users:update"]},
    )
    assert limited.status_code == 201, limited.text
    clerk = _user(
        client,
        headers,
        username="clerk",
        email="clerk@example.com",
        full_name="Staff Admin",
        pin="5555",
        role_id=limited.json()["id"],
    )
    signed = client.post(
        "/api/v1/auth/login-password", json={"username": "clerk", "password": "staff-password-123"}
    )
    assert signed.status_code == 200, signed.text
    self_grant = client.put(
        "/api/v1/addon-access/assignments",
        headers={"Authorization": f"Bearer {signed.json()['access_token']}"},
        json={
            "changes": [
                {"user_id": clerk["id"], "module_key": "gift_cards", "status": "granted", "permissions": [GIFT]}
            ]
        },
    )
    assert self_grant.status_code == 403
    assert self_grant.json()["error"]["code"] == "privilege_escalation"


def test_an_expired_add_on_stays_closed_and_the_cache_generation_moves(client, session) -> None:
    _purchase(session, until=datetime.now(UTC) - timedelta(days=1))
    headers, admin_id = admin(client)
    refused = client.put(
        "/api/v1/addon-access/assignments",
        headers=headers,
        json={
            "changes": [
                {"user_id": admin_id, "module_key": "gift_cards", "status": "granted", "permissions": [GIFT]}
            ]
        },
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "addon_inactive"
    modules = client.get("/api/v1/addon-access/modules", headers=headers)
    assert modules.status_code == 200
    assert modules.json()[0]["entitlement"] == "expired"

    _purchase(session)
    _grant(client, headers, admin_id, [GIFT])
    settings = load_settings(session)
    assert get_value(f"tenant:{settings.tenant_id}:addon-generation") not in (None, "0")
    again = client.put(
        "/api/v1/addon-access/assignments",
        headers=headers,
        json={"changes": [{"user_id": admin_id, "module_key": "gift_cards", "status": "revoked", "permissions": []}]},
    )
    assert again.status_code == 200
    assert session.query(UserAddonAccess).count() == 1
    assert session.query(UserAddonAccess).one().status == "revoked"
