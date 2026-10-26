"""Grocery till rules: age checks, bag fees, produce waste, and co-purchase suggestions."""

import uuid

from sqlalchemy.orm import Session
from tests.test_batches import cable_batch, on_hand
from tests.test_returns import (
    CABLE_ID,
    CASHIER_ID,
    STORE_ID,
    TAX_BPS,
    admin_id,
    admin_token,
    bearer,
    device,
    push,
    seed_catalog,
)

from app.core.capabilities import Capability


def category_id(client, token: str, name: str = "Produce") -> str:
    response = client.post("/api/v1/categories", headers=bearer(token), json={"name": name})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def grocery(client, token: str) -> None:
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={
            "business_profile": "grocery",
            "capabilities": [
                Capability.LOYALTY.value,
                Capability.PROMOTIONS.value,
                Capability.WEIGHED_ITEMS.value,
                Capability.FEFO.value,
            ],
        },
    )
    assert response.status_code == 200, response.text


def wine(client, token: str) -> dict:
    response = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": "WINE-RED",
            "barcode": "2000000000099",
            "name": "Red wine",
            "category_id": category_id(client, token),
            "price_cents": 1000,
            "is_serialized": False,
            "tax_category": "EXEMPT",
            "minimum_age": 21,
            "opening_store_id": STORE_ID,
            "opening_quantity": 5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def sell(client, product_id: str, price: int, *, age_check: dict | None = None, tax_bps: int = 0):
    tax = round(price * tax_bps / 10_000)
    sale_id = str(uuid.uuid4())
    item = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "quantity": 1,
        "unit_price_cents": price,
        "tax_cents": tax,
        "line_total_cents": price + tax,
    }
    if age_check is not None:
        item["age_check"] = age_check
    payload = {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": price,
        "tax_cents": tax,
        "total_cents": price + tax,
        "client_sale_id": sale_id,
        "items": [item],
    }
    return push(client, "sale", payload)


def test_restricted_products_need_an_age_check(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    grocery(client, token)
    product = wine(client, token)

    blocked = sell(client, product["id"], 1000)
    assert blocked.status_code == 422
    assert "age check" in blocked.json()["error"]["message"]

    sold = sell(client, product["id"], 1000, age_check={"confirmed": True})
    assert sold.status_code == 200, sold.text

    missing_reason = sell(
        client,
        product["id"],
        1000,
        age_check={"confirmed": True, "override_by_id": admin_id(client), "reason": "  "},
    )
    assert missing_reason.status_code == 422

    overridden = sell(
        client,
        product["id"],
        1000,
        age_check={"confirmed": True, "override_by_id": admin_id(client), "reason": "ID checked at the desk"},
    )
    assert overridden.status_code == 200, overridden.text


def test_bag_fee_matches_the_configured_amount(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    grocery(client, token)
    settings = client.get("/api/v1/settings", headers=bearer(token)).json()
    modules = settings["module_settings"]
    modules["bags"] = {"enabled": True, "fee_cents": 25, "tax_category": "EXEMPT"}
    saved = client.put("/api/v1/settings/modules", headers=bearer(token), json=modules)
    assert saved.status_code == 200, saved.text
    products = client.get("/api/v1/products", headers=bearer(token), params={"limit": 50}).json()
    bag = next(row for row in products if row["sku"] == "BAG-FEE")
    assert bag["is_service"] is True

    mismatch = sell(client, bag["id"], 26)
    assert mismatch.status_code == 422
    assert "bag fee" in mismatch.json()["error"]["message"].lower()

    added = sell(client, bag["id"], 25)
    assert added.status_code == 200, added.text


def test_produce_waste_is_idempotent(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    grocery(client, token)
    batch = cable_batch(client, token, 6, "5.00")
    item_id = batch["items"][0]["id"]
    before = on_hand(session, CABLE_ID)
    adjustment_id = str(uuid.uuid4())
    body = {
        "adjustment_id": adjustment_id,
        "batch_item_id": item_id,
        "quantity": 2,
        "reason_code": "SPOILAGE",
        "note": "Soft fruit",
    }
    first = client.post("/api/v1/inventory/waste", headers=bearer(token), json=body)
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    assert on_hand(session, CABLE_ID) == before - 2
    second = client.post("/api/v1/inventory/waste", headers=bearer(token), json=body)
    assert second.status_code == 200, second.text
    assert second.json()["duplicate"] is True
    assert on_hand(session, CABLE_ID) == before - 2


def test_suggestions_are_grocery_only_and_need_three_shared_sales(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    refused = client.get(
        "/api/v1/grocery/suggestions",
        headers=device(),
        params={"store_id": STORE_ID, "product_id": CABLE_ID},
    )
    assert refused.status_code == 403
    grocery(client, token)
    bread = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": "BREAD",
            "barcode": "2000000000088",
            "name": "Arabic bread",
            "category_id": category_id(client, token, "Bakery"),
            "price_cents": 300,
            "is_serialized": False,
            "tax_category": "EXEMPT",
            "opening_store_id": STORE_ID,
            "opening_quantity": 20,
        },
    )
    assert bread.status_code == 201, bread.text
    bread_id = bread.json()["id"]

    def together() -> None:
        sale_id = str(uuid.uuid4())
        cable_tax = round(1500 * TAX_BPS / 10_000)
        payload = {
            "id": sale_id,
            "store_id": STORE_ID,
            "cashier_id": CASHIER_ID,
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": 1500 + 300,
            "tax_cents": cable_tax,
            "total_cents": 1500 + 300 + cable_tax,
            "client_sale_id": sale_id,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": CABLE_ID,
                    "quantity": 1,
                    "unit_price_cents": 1500,
                    "tax_cents": cable_tax,
                    "line_total_cents": 1500 + cable_tax,
                },
                {
                    "id": str(uuid.uuid4()),
                    "product_id": bread_id,
                    "quantity": 1,
                    "unit_price_cents": 300,
                    "tax_cents": 0,
                    "line_total_cents": 300,
                },
            ],
        }
        response = push(client, "sale", payload)
        assert response.status_code == 200, response.text

    together()
    together()
    thin = client.get(
        "/api/v1/grocery/suggestions",
        headers=device(),
        params={"store_id": STORE_ID, "product_id": CABLE_ID},
    )
    assert thin.status_code == 200 and thin.json()["suggestions"] == []
    together()
    found = client.get(
        "/api/v1/grocery/suggestions",
        headers=device(),
        params={"store_id": STORE_ID, "product_id": CABLE_ID},
    )
    assert found.status_code == 200, found.text
    suggestions = found.json()["suggestions"]
    assert [row["product_id"] for row in suggestions] == [bread_id]
    assert suggestions[0]["pitch"] == "Frequently bought together."
