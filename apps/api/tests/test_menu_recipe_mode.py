"""Restaurant and cafe dishes follow the product recipe toggle on new lines."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import on_hand
from tests.test_menu import enable, sale_with
from tests.test_recipes import ingredient
from tests.test_returns import (
    CASHIER_ID,
    CASHIER_PIN,
    STORE_ID,
    admin_id,
    admin_token,
    bearer,
    device,
    push,
    seed_catalog,
)

from app.models import Product, SaleItem, StockMovement


def _category(client, token: str) -> str:
    response = client.post("/api/v1/categories", headers=bearer(token), json={"name": f"Menu {uuid.uuid4().hex[:8]}"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _dish(client, token: str, category_id: str, *, name: str, prepared: bool) -> object:
    suffix = uuid.uuid4().hex[:8]
    return client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": f"DISH-{suffix}",
            "barcode": f"28{suffix}",
            "name": name,
            "category_id": category_id,
            "price_cents": 500,
            "item_type": "MADE_TO_ORDER",
            "sell_without_recipe": prepared,
            "opening_quantity": 0,
        },
    )


def _sale(product_id: str, cents: int, *, skip: bool, cashier: str, option_id: str | None = None) -> dict:
    body = sale_with([], cents)
    body["cashier_id"] = cashier
    body["subtotal_cents"] = cents
    body["total_cents"] = cents
    item = body["items"][0]
    item["product_id"] = product_id
    item["unit_price_cents"] = cents
    item["list_price_cents"] = cents
    item["line_total_cents"] = cents
    item["skip_recipe"] = skip
    if option_id is not None:
        item["price_option_id"] = option_id
    return body


def test_prepared_toggle_is_authoritative_for_new_lines(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "recipes", "menu_modifiers", "open_orders", "tables")
    category_id = _category(client, token)

    blocked = _dish(client, token, category_id, name="Daal Channa", prepared=False)
    assert blocked.status_code == 422, blocked.text
    assert "recipe is required" in blocked.json()["error"]["message"]

    created = _dish(client, token, category_id, name="Daal Channa", prepared=True)
    assert created.status_code in (200, 201), created.text
    dish = created.json()
    assert dish["sell_without_recipe"] is True and dish["item_type"] == "MADE_TO_ORDER"
    assert dish["has_recipe"] is False

    packed = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": f"WATER-{uuid.uuid4().hex[:6]}",
            "barcode": f"27{uuid.uuid4().hex[:8]}",
            "name": "Mineral Water",
            "category_id": category_id,
            "price_cents": 200,
            "item_type": "PRE_PACKAGED",
            "sell_without_recipe": True,
            "opening_store_id": STORE_ID,
            "opening_quantity": 4,
        },
    )
    assert packed.status_code in (200, 201), packed.text
    assert packed.json()["sell_without_recipe"] is False

    beans = ingredient(client, token, "Channa", quantity=100, by_weight=False, category_id=category_id)
    saved = client.put(
        f"/api/v1/recipes/{dish['id']}",
        headers=bearer(token),
        json={"yield_quantity": 1, "lines": [{"ingredient_id": beans["id"], "quantity": 10}]},
    )
    assert saved.status_code == 200, saved.text
    kept = client.get(f"/api/v1/products/{dish['id']}", headers=bearer(token))
    assert kept.status_code == 200 and kept.json()["sell_without_recipe"] is True
    assert client.get(f"/api/v1/recipes/{dish['id']}", headers=bearer(token)).status_code == 200

    portions = client.put(
        f"/api/v1/menu/products/{dish['id']}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"name": "Small Plate", "price_cents": 300, "is_active": True, "position": 0},
                {"name": "Medium Plate", "price_cents": 500, "is_active": True, "position": 1},
                {"name": "Full Plate", "price_cents": 900, "is_active": True, "position": 2},
            ]
        },
    )
    assert portions.status_code == 200, portions.text
    full = next(option for option in portions.json() if option["name"] == "Full Plate")
    listed = client.get(f"/api/v1/products/{dish['id']}", headers=bearer(token))
    assert listed.status_code == 200, listed.text
    row = listed.json()
    assert row["sell_without_recipe"] is True
    assert [option["price_cents"] for option in row["price_options"]] == [300, 500, 900]

    cashier = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": CASHIER_PIN},
        headers=device(),
    ).json()["access_token"]
    refused_write = client.patch(
        f"/api/v1/products/{dish['id']}",
        headers=bearer(cashier),
        json={"sell_without_recipe": False},
    )
    assert refused_write.status_code == 403, refused_write.text

    plate = _sale(dish["id"], 900, skip=True, cashier=CASHIER_ID, option_id=full["id"])
    key = f"sale-{plate['id']}"
    assert push(client, "sale", plate, key=key).status_code == 200, plate
    assert push(client, "sale", plate, key=key).status_code == 200
    session.expire_all()
    assert on_hand(session, beans["id"]) == 100
    movements = session.scalars(select(StockMovement).where(StockMovement.movement_type == "RECIPE_OUT")).all()
    assert movements == []
    stored = session.get(SaleItem, uuid.UUID(plate["items"][0]["id"]))
    assert stored is not None
    assert stored.skip_recipe is True and stored.price_option_name == "Full Plate" and stored.price_option_cents == 900

    mismatch = _sale(dish["id"], 900, skip=False, cashier=admin_id(client), option_id=full["id"])
    denied = push(client, "sale", mismatch)
    assert denied.status_code == 422 and "menu item" in denied.json()["error"]["message"]
    assert on_hand(session, beans["id"]) == 100

    managed = client.patch(
        f"/api/v1/products/{dish['id']}",
        headers=bearer(token),
        json={"sell_without_recipe": False},
    )
    assert managed.status_code == 200, managed.text
    assert managed.json()["sell_without_recipe"] is False
    assert client.get(f"/api/v1/recipes/{dish['id']}", headers=bearer(token)).status_code == 200
    session.expire_all()
    assert session.get(SaleItem, uuid.UUID(plate["items"][0]["id"])).skip_recipe is True

    drawn = _sale(dish["id"], 900, skip=False, cashier=CASHIER_ID, option_id=full["id"])
    assert push(client, "sale", drawn).status_code == 200, drawn
    session.expire_all()
    assert on_hand(session, beans["id"]) == 90
    assert stored.skip_recipe is True

    override = _sale(dish["id"], 900, skip=True, cashier=admin_id(client), option_id=full["id"])
    blocked_sale = push(client, "sale", override)
    assert blocked_sale.status_code == 422 and "menu item" in blocked_sale.json()["error"]["message"]
    assert on_hand(session, beans["id"]) == 90

    renamed = client.patch(
        f"/api/v1/products/{dish['id']}",
        headers=bearer(token),
        json={"name": "Daal Channa House"},
    )
    assert renamed.status_code == 200, renamed.text
    assert session.get(SaleItem, uuid.UUID(plate["items"][0]["id"])).skip_recipe is True

    plain = _dish(client, token, category_id, name="House Rice", prepared=True)
    assert plain.status_code in (200, 201), plain.text
    rice = session.get(Product, uuid.UUID(plain.json()["id"]))
    assert rice is not None
    rice.sell_without_recipe = False
    session.commit()
    untouched = client.patch(
        f"/api/v1/products/{rice.id}",
        headers=bearer(token),
        json={"name": "House Rice Bowl"},
    )
    assert untouched.status_code == 200, untouched.text
    assert untouched.json()["sell_without_recipe"] is False
    missing = client.patch(
        f"/api/v1/products/{rice.id}",
        headers=bearer(token),
        json={"sell_without_recipe": False},
    )
    assert missing.status_code == 422 and "recipe is required" in missing.json()["error"]["message"]
