from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Product, Store, User
from test_returns import (
    CABLE_ID,
    STORE_ID,
    STORE_MANAGER_ROLE,
    admin_id,
    admin_token,
    approval,
    bearer,
    device,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)


def change_currency(client, token: str, currency: str):
    return client.put("/api/v1/settings/currency", headers=bearer(token), json={"currency": currency})


def portal_user(client, token: str, *, username: str, role_id: str, store_id: str | None) -> str:
    created = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": username.title(),
            "role_id": role_id,
            "store_id": store_id,
            "password": "portal-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/v1/auth/login-password", json={"username": username, "password": "portal-password-1"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_registers_and_portal_read_the_business_currency(client) -> None:
    body = client.get("/api/v1/settings", headers=device()).json()
    assert body["currency"] == "USD"
    assert "AED" in body["supported_currencies"]
    assert "CNY" in body["supported_currencies"]
    assert client.get("/api/v1/settings").status_code == 401


def test_only_business_wide_super_admins_change_currency(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    manager = portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=STORE_ID)
    assert change_currency(client, manager, "EUR").status_code == 403

    role = client.post(
        "/api/v1/roles",
        headers=bearer(token),
        json={"name": "Branch Settings", "permissions": ["portal:access", "settings:manage"]},
    ).json()
    scoped = portal_user(client, token, username="branch", role_id=role["id"], store_id=STORE_ID)
    assert change_currency(client, scoped, "EUR").status_code == 403

    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    ).json()["access_token"]
    assert change_currency(client, cashier, "EUR").status_code == 403
    assert client.put("/api/v1/settings/currency", headers=device(), json={"currency": "EUR"}).status_code == 403

    assert change_currency(client, token, "XYZ").status_code == 422
    assert client.get("/api/v1/settings", headers=device()).json()["currency"] == "USD"


def test_changing_currency_relabels_the_catalog(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    response = change_currency(client, token, "aed")
    assert response.status_code == 200, response.text
    assert response.json()["currency"] == "AED"
    assert response.json()["updated_by_name"] == "Root Admin"

    session.expire_all()
    assert {store.currency for store in session.scalars(select(Store))} == {"AED"}
    assert {product.currency for product in session.scalars(select(Product))} == {"AED"}
    cable = client.get(f"/api/v1/products/{CABLE_ID}", headers=device()).json()
    assert cable["price_cents"] == 1500

    log = session.scalars(select(AuditLog).where(AuditLog.action == "settings.currency")).one()
    assert log.details["from"] == "USD" and log.details["to"] == "AED"

    assert change_currency(client, token, "AED").status_code == 200
    assert len(session.scalars(select(AuditLog).where(AuditLog.action == "settings.currency")).all()) == 1


def test_sync_follows_the_business_currency(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500)
    assert change_currency(client, admin_token(client), "AED").status_code == 200

    stale_store = push(client, "store", {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "USD"})
    assert stale_store.status_code == 422
    assert "business currency AED" in stale_store.json()["error"]["message"]
    fresh_store = push(client, "store", {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "AED"})
    assert fresh_store.status_code == 200, fresh_store.text

    stale_sale = {**sale, "id": "00000000-0000-4000-8000-0000000000f1", "client_sale_id": "stale-usd-sale"}
    stale_sale["items"] = [{**sale["items"][0], "id": "00000000-0000-4000-8000-0000000000f2"}]
    assert push(client, "sale", stale_sale).status_code == 422
    fresh_sale = {**stale_sale, "currency": "AED"}
    assert push(client, "sale", fresh_sale).status_code == 200

    body = receipt(client, sale["id"])
    returned = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert returned.status_code == 200, returned.text


def test_reports_default_to_the_business_currency(client) -> None:
    seed_catalog(client)
    record_sale(client, product_id=CABLE_ID, price=1500)
    token = admin_token(client)
    assert client.get("/api/v1/analytics/summary", headers=bearer(token)).json()["currency"] == "USD"

    change_currency(client, token, "GBP")
    summary = client.get("/api/v1/analytics/summary", headers=bearer(token)).json()
    assert summary["currency"] == "GBP"
    history = client.get("/api/v1/analytics/summary?currency=USD", headers=bearer(token)).json()
    assert history["currency"] == "USD"


def change_identity(client, token: str, body: dict):
    return client.put("/api/v1/settings/identity", headers=bearer(token), json=body)


def test_pos_and_portal_update_the_same_business_identity(client, session: Session) -> None:
    current = client.get("/api/v1/settings", headers=device()).json()
    revision = current["entitlement_revision"]
    rate = current["standard_rate_bps"]
    pin = client.post("/api/v1/auth/login-pin", json={"username": "admin", "pin": "2468"}, headers=device())
    assert pin.status_code == 200, pin.text
    pos = pin.json()["access_token"]
    payload = {
        "legal_name": "Portion Identity",
        "legal_name_ar": None,
        "country": "SA",
        "location": "Deira",
        "expected_revision": revision,
    }
    saved = change_identity(client, pos, payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["legal_name"] == "Portion Identity"
    assert body["country"] == "SA"
    assert body["location"] == "Deira"
    assert body["entitlement_revision"] == revision + 1
    assert body["updated_by_name"] == "Root Admin"
    assert body["standard_rate_bps"] == rate
    assert body["updated_at"]

    replay = change_identity(client, pos, payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["entitlement_revision"] == revision + 1

    stale = change_identity(client, pos, {**payload, "location": "Karama"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_settings"
    assert stale.json()["error"]["details"]["entitlement_revision"] == revision + 1

    portal = admin_token(client)
    moved = change_identity(
        client,
        portal,
        {**payload, "location": "Karama", "expected_revision": revision + 1},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["entitlement_revision"] == revision + 2
    assert client.get("/api/v1/settings", headers=device()).json()["location"] == "Karama"

    session.expire_all()
    logs = list(session.scalars(select(AuditLog).where(AuditLog.action == "settings.identity")))
    by_source = {log.details["source"]: log for log in logs}
    assert set(by_source) == {"pos", "business_pro"}
    assert by_source["pos"].client_device == "desktop"
    assert by_source["pos"].new_values["legal_name"] == "Portion Identity"
    assert by_source["business_pro"].client_device == "web"
    assert by_source["business_pro"].new_values["location"] == "Karama"


def test_identity_rejects_bad_values_and_the_wrong_actor(client, session: Session) -> None:
    current = client.get("/api/v1/settings", headers=device()).json()
    revision = current["entitlement_revision"]
    token = admin_token(client)
    assert change_identity(client, token, {
        "legal_name": "   ",
        "country": "AE",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 422
    assert change_identity(client, token, {
        "legal_name": "Portion",
        "country": "ZZ",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 422

    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    ).json()["access_token"]
    assert change_identity(client, cashier, {
        "legal_name": "Cashier Edit",
        "country": "AE",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 403
    assert client.put("/api/v1/settings/identity", headers=device(), json={
        "legal_name": "Device Edit",
        "country": "AE",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 403

    seed_catalog(client)
    role = client.post(
        "/api/v1/roles",
        headers=bearer(token),
        json={"name": "Branch Identity", "permissions": ["portal:access", "settings:manage"]},
    ).json()
    manager = portal_user(client, token, username="branch-identity", role_id=role["id"], store_id=STORE_ID)
    assert change_identity(client, manager, {
        "legal_name": "Branch Edit",
        "country": "AE",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 403
    assert client.get("/api/v1/settings", headers=device()).json()["legal_name"] == current["legal_name"]

    admin = session.scalar(select(User).where(User.username == "admin"))
    assert admin is not None
    admin.is_active = False
    session.commit()
    assert client.post(
        "/api/v1/auth/login-pin", json={"username": "admin", "pin": "2468"}, headers=device()
    ).status_code in {401, 403}
    assert change_identity(client, token, {
        "legal_name": "Disabled Edit",
        "country": "AE",
        "location": "Deira",
        "expected_revision": revision,
    }).status_code == 401
