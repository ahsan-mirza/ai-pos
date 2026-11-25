"""Restaurant and cafe products can be saved without a SKU. Other profiles cannot."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_returns import CASHIER_ID, STORE_ID, TAX_BPS, admin_token, bearer, push, seed_catalog

from app.models import Product, SaleItem


def _switch(client, token: str, profile: str) -> None:
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": profile, "capabilities": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["business_profile"] == profile


def _category(client, token: str) -> str:
    response = client.post(
        "/api/v1/categories",
        headers=bearer(token),
        json={"name": f"Kitchen {uuid.uuid4().hex[:6]}"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _create(client, token: str, category_id: str, **extra: object):
    body = {
        "barcode": extra.pop("barcode"),
        "name": extra.pop("name"),
        "category_id": category_id,
        "price_cents": 300,
        "opening_quantity": 0,
    }
    body.update(extra)
    return client.post("/api/v1/inventory/products", headers=bearer(token), json=body)


def test_grocery_still_requires_a_sku_and_a_menu_does_not(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    category_id = _category(client, token)
    refused = _create(client, token, category_id, barcode="281000000101", name="Rice 1kg", sku="")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "sku_required"

    _switch(client, token, "restaurant")
    small = _create(
        client,
        token,
        category_id,
        barcode="281000000102",
        name="Daal Channa",
        item_type="MADE_TO_ORDER",
        sell_without_recipe=True,
    )
    assert small.status_code == 201, small.text
    full = _create(
        client,
        token,
        category_id,
        barcode="281000000103",
        name="Daal Channa Full",
        item_type="MADE_TO_ORDER",
        sell_without_recipe=True,
        sku="   ",
    )
    assert full.status_code == 201, full.text
    ingredient = _create(
        client,
        token,
        category_id,
        barcode="281000000104",
        name="Channa",
        item_type="RAW_INGREDIENT",
        price_cents=0,
    )
    assert ingredient.status_code == 201, ingredient.text
    first, second, raw = small.json(), full.json(), ingredient.json()
    assert first["id"] != second["id"]
    assert first["sku"] == "" and second["sku"] == "" and raw["sku"] == ""
    for row in (first, second, raw):
        stored = session.get(Product, uuid.UUID(row["id"]))
        assert stored is not None and stored.sku is None

    kept = _create(
        client,
        token,
        category_id,
        barcode="281000000105",
        name="Mineral Water",
        sku="WATER-1",
        item_type="PRE_PACKAGED",
    )
    assert kept.status_code == 201, kept.text
    renamed = client.patch(
        f"/api/v1/products/{kept.json()['id']}",
        headers=bearer(token),
        json={"name": "Mineral Water Still"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["sku"] == "WATER-1"
    assert session.get(Product, uuid.UUID(kept.json()["id"])).sku == "WATER-1"

    options = client.put(
        f"/api/v1/menu/products/{first['id']}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"name": "Small Plate", "price_cents": 300, "is_active": True, "position": 0},
                {"name": "Full Plate", "price_cents": 500, "is_active": True, "position": 1},
            ]
        },
    )
    assert options.status_code == 200, options.text
    assert all(row["sku"] in (None, "") for row in options.json())

    found = client.get("/api/v1/products/search", headers=bearer(token), params={"q": "Daal Channa", "limit": 10})
    assert found.status_code == 200, found.text
    names = {row["product"]["name"] for row in found.json()}
    assert "Daal Channa" in names and "Daal Channa Full" in names


def test_cafe_can_omit_a_sku(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _switch(client, token, "cafe")
    category_id = _category(client, token)
    created = _create(
        client,
        token,
        category_id,
        barcode="281000000201",
        name="House Coffee",
        item_type="MADE_TO_ORDER",
        sell_without_recipe=True,
    )
    assert created.status_code == 201, created.text
    assert created.json()["sku"] == ""


def test_selling_a_menu_item_without_a_sku_syncs(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _switch(client, token, "restaurant")
    category_id = _category(client, token)
    created = _create(
        client,
        token,
        category_id,
        barcode="281000000301",
        name="Karak",
        item_type="MADE_TO_ORDER",
        sell_without_recipe=True,
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    price = 300
    tax = round(price * TAX_BPS / 10_000)
    sale_id = str(uuid.uuid4())
    response = push(
        client,
        "sale",
        {
            "id": sale_id,
            "store_id": STORE_ID,
            "cashier_id": CASHIER_ID,
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": price,
            "tax_cents": tax,
            "total_cents": price + tax,
            "client_sale_id": sale_id,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "quantity": 1,
                    "unit_price_cents": price,
                    "tax_cents": tax,
                    "line_total_cents": price + tax,
                    "skip_recipe": True,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    session.expire_all()
    item = session.scalar(select(SaleItem).where(SaleItem.sale_id == uuid.UUID(sale_id)))
    assert item is not None
    assert item.sku is None
