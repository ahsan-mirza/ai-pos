import uuid

API_KEY = "test-api-key-value"
ADMIN_PASSWORD = "root-password-123"
CASHIER_PIN = "1357"
STORE_ID = "00000000-0000-4000-8000-000000000001"
OTHER_STORE_ID = "00000000-0000-4000-8000-000000000009"
SUPER_ADMIN_ROLE = "00000000-0000-4000-8000-0000000000a1"
STORE_MANAGER_ROLE = "00000000-0000-4000-8000-0000000000a2"
CASHIER_ROLE = "00000000-0000-4000-8000-0000000000a3"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client, username: str = "admin", password: str = ADMIN_PASSWORD):
    return client.post("/api/v1/auth/login-password", json={"username": username, "password": password})


def admin_token(client) -> str:
    response = login(client)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def seed_stores(client) -> None:
    events = [
        {
            "idempotency_key": f"store-{store_id[-4:]}",
            "entity_type": "store",
            "operation": "upsert",
            "payload": {"id": store_id, "code": code, "name": code, "currency": "USD"},
            "occurred_at": "2026-10-19T08:00:00Z",
        }
        for store_id, code in ((STORE_ID, "DT-01"), (OTHER_STORE_ID, "UP-02"))
    ]
    response = client.post(
        "/api/v1/sync/push",
        headers={"X-Api-Key": API_KEY},
        json={"device_id": "seed", "events": events},
    )
    assert response.status_code == 200, response.text


def create_manager(client, token: str) -> dict:
    response = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "manager.dt",
            "email": "manager@example.com",
            "full_name": "Store Manager",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": STORE_ID,
            "password": "manager-password-1",
            "pin": "8642",
            "has_portal_access": True,
            "has_pos_access": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_password_login_returns_portal_token(client) -> None:
    response = login(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "portal"
    assert "roles:manage" in body["user"]["permissions"]
    assert response.headers["Cache-Control"] == "no-store"

    me = client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_failed_logins_lock_the_account(client) -> None:
    for _ in range(3):
        assert login(client, password="wrong-password").status_code == 401
    locked = login(client)
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "account_locked"


def test_unknown_user_gets_generic_error(client) -> None:
    response = login(client, username="nobody")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid username or credentials."


def test_pin_login_requires_device_key(client) -> None:
    body = {"username": "cashier", "pin": CASHIER_PIN}
    assert client.post("/api/v1/auth/login-pin", json=body).status_code == 401

    response = client.post("/api/v1/auth/login-pin", json=body, headers={"X-Api-Key": API_KEY})
    assert response.status_code == 200, response.text
    assert response.json()["scope"] == "pos"


def test_cashier_cannot_use_portal(client) -> None:
    assert login(client, username="cashier", password="anything-at-all").status_code == 401
    pos = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": CASHIER_PIN},
        headers={"X-Api-Key": API_KEY},
    ).json()["access_token"]
    assert client.get("/api/v1/users", headers=bearer(pos)).status_code == 403


def test_portal_reads_require_auth(client) -> None:
    assert client.get("/api/v1/products").status_code == 401
    token = admin_token(client)
    assert client.get("/api/v1/products", headers=bearer(token)).status_code == 200


def test_store_manager_is_scoped_and_cannot_escalate(client) -> None:
    seed_stores(client)
    token = admin_token(client)
    create_manager(client, token)
    manager = login(client, "manager.dt", "manager-password-1").json()["access_token"]

    escalate = client.post(
        "/api/v1/users",
        headers=bearer(manager),
        json={
            "username": "sneaky",
            "email": "sneaky@example.com",
            "full_name": "Sneaky",
            "role_id": SUPER_ADMIN_ROLE,
            "password": "sneaky-password-1",
            "has_portal_access": True,
        },
    )
    assert escalate.status_code == 403
    assert escalate.json()["error"]["code"] == "privilege_escalation"

    other_store = client.post(
        "/api/v1/users",
        headers=bearer(manager),
        json={
            "username": "elsewhere",
            "email": "elsewhere@example.com",
            "full_name": "Elsewhere",
            "role_id": CASHIER_ROLE,
            "store_id": OTHER_STORE_ID,
            "pin": "1111",
            "has_pos_access": True,
        },
    )
    assert other_store.status_code == 403

    cashier = client.post(
        "/api/v1/users",
        headers=bearer(manager),
        json={
            "username": "dt.cashier",
            "email": "dt.cashier@example.com",
            "full_name": "Downtown Cashier",
            "role_id": CASHIER_ROLE,
            "pin": "1111",
            "has_pos_access": True,
        },
    )
    assert cashier.status_code == 201, cashier.text
    assert cashier.json()["store_id"] == STORE_ID

    visible = {user["username"] for user in client.get("/api/v1/users", headers=bearer(manager)).json()}
    assert visible == {"manager.dt", "dt.cashier"}

    admin_id = next(
        user["id"] for user in client.get("/api/v1/users", headers=bearer(token)).json() if user["username"] == "admin"
    )
    reset = client.post(f"/api/v1/users/{admin_id}/password", headers=bearer(manager), json={"password": "x" * 12})
    assert reset.status_code == 404


def test_password_reset_revokes_existing_tokens(client) -> None:
    seed_stores(client)
    token = admin_token(client)
    manager = create_manager(client, token)
    manager_token = login(client, "manager.dt", "manager-password-1").json()["access_token"]

    reset = client.post(
        f"/api/v1/users/{manager['id']}/password",
        headers=bearer(token),
        json={"password": "brand-new-password"},
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/auth/me", headers=bearer(manager_token)).status_code == 401
    assert login(client, "manager.dt", "brand-new-password").status_code == 200


def test_disabling_portal_access_blocks_login(client) -> None:
    seed_stores(client)
    token = admin_token(client)
    manager = create_manager(client, token)
    response = client.patch(
        f"/api/v1/users/{manager['id']}",
        headers=bearer(token),
        json={"has_portal_access": False},
    )
    assert response.status_code == 200
    assert login(client, "manager.dt", "manager-password-1").status_code == 403


def test_last_super_admin_is_protected(client) -> None:
    token = admin_token(client)
    me = client.get("/api/v1/auth/me", headers=bearer(token)).json()
    response = client.patch(f"/api/v1/users/{me['id']}", headers=bearer(token), json={"is_active": False})
    assert response.status_code == 422
    assert client.delete(f"/api/v1/users/{me['id']}", headers=bearer(token)).status_code == 422


def test_custom_roles(client) -> None:
    token = admin_token(client)
    created = client.post(
        "/api/v1/roles",
        headers=bearer(token),
        json={"name": "Inventory Clerk", "permissions": ["portal:access", "portal:inventory_manage"]},
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["permissions"] == ["portal:access", "portal:inventory_manage"]

    unknown = client.post("/api/v1/roles", headers=bearer(token), json={"name": "Bad", "permissions": ["root:all"]})
    assert unknown.status_code == 422

    renamed = client.patch(
        f"/api/v1/roles/{SUPER_ADMIN_ROLE}",
        headers=bearer(token),
        json={"permissions": ["portal:access"]},
    )
    assert renamed.status_code == 422

    client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "clerk",
            "email": "clerk@example.com",
            "full_name": "Clerk",
            "role_id": role["id"],
            "password": "clerk-password-1",
            "has_portal_access": True,
        },
    )
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=bearer(token)).status_code == 409

    catalog = client.get("/api/v1/roles/permissions", headers=bearer(token)).json()
    keys = {item["key"] for group in catalog for item in group["permissions"]}
    assert "pos:drawer_override" in keys


def test_sync_rejects_unknown_or_out_of_store_cashier(client) -> None:
    seed_stores(client)
    token = admin_token(client)
    manager = create_manager(client, token)

    product = {
        "id": str(uuid.uuid4()),
        "store_id": OTHER_STORE_ID,
        "sku": "UP-CABLE",
        "barcode": "200000000001",
        "name": "Cable",
        "category": "Accessories",
        "price_cents": 1000,
        "currency": "USD",
        "is_serialized": False,
        "stock_quantity": 5,
    }

    def sale(cashier_id: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "store_id": OTHER_STORE_ID,
            "cashier_id": cashier_id,
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": 1000,
            "tax_cents": 0,
            "total_cents": 1000,
            "client_sale_id": str(uuid.uuid4()),
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": product["id"],
                    "quantity": 1,
                    "unit_price_cents": 1000,
                    "tax_cents": 0,
                    "line_total_cents": 1000,
                }
            ],
        }

    def push(key: str, payload: dict):
        events = [
            {
                "idempotency_key": f"{key}-product",
                "entity_type": "product",
                "operation": "upsert",
                "payload": product,
                "occurred_at": "2026-10-19T08:00:00Z",
            },
            {
                "idempotency_key": f"{key}-sale",
                "entity_type": "sale",
                "operation": "upsert",
                "payload": payload,
                "occurred_at": "2026-10-19T08:00:00Z",
            },
        ]
        return client.post(
            "/api/v1/sync/push",
            headers={"X-Api-Key": API_KEY},
            json={"device_id": "register-2", "events": events},
        )

    unknown = push("unknown-cashier", sale(str(uuid.uuid4())))
    assert unknown.status_code == 422
    assert unknown.json()["error"]["message"] == "Cashier does not exist."

    wrong_store = push("wrong-store", sale(manager["id"]))
    assert wrong_store.status_code == 422
    assert wrong_store.json()["error"]["message"] == "Cashier is not assigned to this store."
