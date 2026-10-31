import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_token, bearer, push, seed_catalog

from app.core import capabilities as catalog
from app.models import SaleItem


def enable(client, token: str, *names: str) -> None:
    """Turn modules on for a test store.

    Modules that fit the current business type are added there. Food-service modules do not fit an electronics
    store, so those tests move onto the restaurant preset, which is allowed to hold them.
    """
    current = client.get("/api/v1/settings", headers=bearer(token))
    assert current.status_code == 200, current.text
    body = current.json()
    profile = body["business_profile"]
    chosen = sorted(set(body["capabilities"]) | set(names))
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": profile, "capabilities": chosen},
    )
    if response.status_code == 422 and response.json()["error"]["code"] == "module_not_available":
        food = [capability.value for capability in catalog.PROFILES["restaurant"]]
        response = client.put(
            "/api/v1/settings/profile",
            headers=bearer(token),
            json={"business_profile": "restaurant", "capabilities": sorted(set(food) | set(names))},
        )
    assert response.status_code == 200, response.text


def as_cafe(client, token: str) -> None:
    """Menu modifiers belong to a food business. An electronics store cannot turn them on."""
    chosen = [capability.value for capability in catalog.PROFILES["cafe"]]
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": "cafe", "capabilities": chosen},
    )
    assert response.status_code == 200, response.text


def milk_group(client, token: str) -> dict:
    response = client.post(
        "/api/v1/menu/modifier-groups",
        headers=bearer(token),
        json={
            "name": "Milk",
            "min_select": 1,
            "max_select": 1,
            "options": [
                {"name": "Whole", "price_delta_cents": 0, "is_default": True},
                {"name": "Oat", "price_delta_cents": 250},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def extras_group(client, token: str) -> dict:
    response = client.post(
        "/api/v1/menu/modifier-groups",
        headers=bearer(token),
        json={
            "name": "Extras",
            "min_select": 0,
            "max_select": 2,
            "options": [{"name": "Extra shot", "price_delta_cents": 300}, {"name": "Syrup", "price_delta_cents": 150}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def sale_with(choices: list[dict], unit: int) -> dict:
    sale_id = str(uuid.uuid4())
    return {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": unit,
        "tax_cents": 0,
        "total_cents": unit,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": CABLE_ID,
                "quantity": 1,
                "unit_price_cents": unit,
                "list_price_cents": unit,
                "tax_cents": 0,
                "line_total_cents": unit,
                "modifiers": choices,
            }
        ],
    }


def choice(group: dict, index: int) -> dict:
    option = group["options"][index]
    return {
        "group_id": group["id"],
        "option_id": option["id"],
        "group": group["name"],
        "option": option["name"],
        "price_delta_cents": option["price_delta_cents"],
    }


def test_menu_is_gated_and_validated(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert client.get("/api/v1/menu/modifier-groups", headers=bearer(token)).status_code == 403
    as_cafe(client, token)
    bad = client.post(
        "/api/v1/menu/modifier-groups",
        headers=bearer(token),
        json={"name": "Size", "min_select": 2, "max_select": 1, "options": [{"name": "S"}]},
    )
    assert bad.status_code == 422
    milk = milk_group(client, token)
    assert [option["name"] for option in milk["options"]] == ["Whole", "Oat"]

    linked = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/modifier-groups", headers=bearer(token), json={"group_ids": [milk["id"]]}
    )
    assert linked.status_code == 200 and linked.json() == [milk["id"]]
    menu = client.get("/api/v1/menu/register", headers=bearer(token)).json()
    assert menu["products"] == {CABLE_ID: [milk["id"]]}

    # Removing an option retires it (past sales name it) instead of deleting it.
    edited = client.put(
        f"/api/v1/menu/modifier-groups/{milk['id']}",
        headers=bearer(token),
        json={
            "name": "Milk",
            "min_select": 1,
            "max_select": 1,
            "options": [{"id": milk["options"][0]["id"], "name": "Whole milk", "is_default": True}],
        },
    )
    assert edited.status_code == 200, edited.text
    assert [(option["name"], option["is_active"]) for option in edited.json()["options"]] == [
        ("Whole milk", True),
        ("Oat", False),
    ]
    menu = client.get("/api/v1/menu/register", headers=bearer(token)).json()
    assert [option["name"] for option in menu["groups"][0]["options"]] == ["Whole milk"]


def test_sales_price_modifiers_from_the_catalogue(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    as_cafe(client, token)
    milk, extras = milk_group(client, token), extras_group(client, token)
    client.put(
        f"/api/v1/menu/products/{CABLE_ID}/modifier-groups",
        headers=bearer(token),
        json={"group_ids": [milk["id"], extras["id"]]},
    )

    missing = push(client, "sale", sale_with([choice(extras, 0)], 1500 + 300))
    assert missing.status_code == 422 and "needs a choice of Milk" in missing.json()["error"]["message"]
    too_many = push(client, "sale", sale_with([choice(milk, 0), choice(milk, 1)], 1500 + 250))
    assert too_many.status_code == 422

    good = sale_with([choice(milk, 1), choice(extras, 0), choice(extras, 1)], 1500 + 250 + 300 + 150)
    response = push(client, "sale", good)
    assert response.status_code == 200, response.text
    item = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(good["items"][0]["id"])))
    assert item.unit_price_cents == 2200
    assert [(entry["group"], entry["option"], entry["price_delta_cents"]) for entry in item.modifiers] == [
        ("Milk", "Oat", 250),
        ("Extras", "Extra shot", 300),
        ("Extras", "Syrup", 150),
    ]

    lied = choice(milk, 1)
    lied["price_delta_cents"] = 1
    priced = sale_with([lied], 1500 + 250)
    recorded = push(client, "sale", priced)
    assert recorded.status_code == 200, recorded.text
    stored = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(priced["items"][0]["id"])))
    assert stored.modifiers[0]["price_delta_cents"] == 250
