"""A retail profile keeps birthday, sizes and notes, and the till can read recent purchases."""

from wholesale_support import admin, device, seed


def test_profile_fields_and_empty_history(client):
    seed(client)
    headers, _ = admin(client)
    created = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Lina Noor",
            "customer_type": "RETAIL",
            "phone": "0501112233",
            "birthday": "1992-10-21",
            "gender": "women",
            "preferred_sizes": {"tops": "M", "bottoms": "32"},
            "notes": "Prefers navy",
            "tags": ["vip"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["birthday"] == "1992-10-21"
    assert body["preferred_sizes"] == {"tops": "M", "bottoms": "32"}
    assert body["notes"] == "Prefers navy"
    assert body["tags"] == ["vip"]
    history = client.get(f"/api/v1/customers/{body['id']}/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json() == []


def test_register_pin_can_open_customers_and_bills(client):
    """A till token keeps the role check and can open the register's customer and bill pages."""
    seed(client)
    pin = client.post("/api/v1/auth/login-pin", json={"username": "admin", "pin": "2468"}, headers=device())
    assert pin.status_code == 200, pin.text
    headers = {"Authorization": f"Bearer {pin.json()['access_token']}"}
    customers = client.get("/api/v1/customers", headers=headers, params={"limit": 5})
    assert customers.status_code == 200, customers.text
    bills = client.get("/api/v1/sales", headers=headers, params={"limit": 5})
    assert bills.status_code == 200, bills.text
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    denied = client.get(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {cashier.json()['access_token']}"},
        params={"limit": 5},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["message"] == "You do not have permission for this action."
