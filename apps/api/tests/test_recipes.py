import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import on_hand
from tests.test_menu import choice, enable, extras_group, sale_with
from tests.test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_id, admin_token, bearer, device, push, seed_catalog
from tests.test_weighed import category

from app.models import AuditLog, RecipeUsage, SaleItem, StockMovement


def ingredient(client, token: str, name: str, *, quantity: int, by_weight: bool, category_id: str) -> dict:
    response = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": f"ING-{name.upper().replace(' ', '-')}",
            "barcode": f"29{abs(hash(name)) % 10**10:010d}",
            "name": name,
            "category_id": category_id,
            "price_cents": 0,
            "sold_by_weight": by_weight,
            "is_ingredient": True,
            "opening_store_id": STORE_ID,
            "opening_quantity": quantity,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_dishes_draw_ingredients_with_modifier_deltas_and_report_usage(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert client.get("/api/v1/recipes", headers=bearer(token)).status_code == 403
    enable(client, token, "menu_modifiers", "recipes")
    extras = extras_group(client, token)
    client.put(
        f"/api/v1/menu/products/{CABLE_ID}/modifier-groups", headers=bearer(token), json={"group_ids": [extras["id"]]}
    )
    pantry = category(client, token)
    beans = ingredient(client, token, "Coffee beans", quantity=1000, by_weight=True, category_id=pantry)
    milk = ingredient(client, token, "Milk", quantity=300, by_weight=False, category_id=pantry)
    assert beans["is_ingredient"] is True

    nested = client.put(
        f"/api/v1/recipes/{CABLE_ID}",
        headers=bearer(token),
        json={"yield_quantity": 1, "lines": [{"ingredient_id": CABLE_ID, "quantity": 1}]},
    )
    assert nested.status_code == 422
    saved = client.put(
        f"/api/v1/recipes/{CABLE_ID}",
        headers=bearer(token),
        json={
            "yield_quantity": 1,
            "lines": [{"ingredient_id": beans["id"], "quantity": 18}, {"ingredient_id": milk["id"], "quantity": 200}],
        },
    )
    assert saved.status_code == 200, saved.text
    assert [line["quantity"] for line in saved.json()["lines"]] == [18, 200]
    shot = extras["options"][0]["id"]
    delta = client.put(
        f"/api/v1/recipes/modifier-options/{shot}",
        headers=bearer(token),
        json={"lines": [{"ingredient_id": beans["id"], "quantity": 9}]},
    )
    assert delta.status_code == 200 and delta.json()["lines"][0]["quantity"] == 9

    cable_before = on_hand(session, CABLE_ID)
    first = sale_with([choice(extras, 0)], 1500 + 300)
    assert push(client, "sale", first).status_code == 200
    assert (on_hand(session, beans["id"]), on_hand(session, milk["id"])) == (1000 - 27, 100)
    assert on_hand(session, CABLE_ID) == cable_before

    # Not enough milk left: the sale still goes through, the shortfall is recorded.
    second = sale_with([], 1500)
    assert push(client, "sale", second).status_code == 200
    assert on_hand(session, milk["id"]) == 0
    short = session.scalar(select(AuditLog).where(AuditLog.action == "recipe.stock_short"))
    assert short is not None and short.details["short"] == {milk["id"]: 100}
    item = session.get(SaleItem, uuid.UUID(second["items"][0]["id"]))
    assert item.cost_estimated is True

    sold_alone = sale_with([], 0)
    sold_alone["items"][0]["product_id"] = milk["id"]
    refused = push(client, "sale", sold_alone)
    assert refused.status_code == 422 and "ingredient" in refused.json()["error"]["message"]

    today = datetime.now(UTC).date().isoformat()
    report = client.get("/api/v1/recipes/variance", headers=bearer(token), params={"from": "2026-10-01", "to": today})
    assert report.status_code == 200, report.text
    rows = {row["ingredient_id"]: row for row in report.json()["rows"]}
    assert (rows[milk["id"]]["theoretical"], rows[milk["id"]]["drawn"], rows[milk["id"]]["variance"]) == (
        400,
        300,
        -100,
    )
    assert rows[beans["id"]]["theoretical"] == 45


def test_prepared_dishes_are_omitted_from_stock_and_report_buildable_portions(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "menu_modifiers", "recipes")
    pantry = category(client, token)
    beans = ingredient(client, token, "Coffee beans", quantity=1000, by_weight=True, category_id=pantry)
    milk = ingredient(client, token, "Milk", quantity=300, by_weight=False, category_id=pantry)
    assert beans["item_type"] == "RAW_INGREDIENT" and beans["is_stock_tracked"] is True
    headers = bearer(token)
    level = client.patch(
        f"/api/v1/inventory/levels/{milk['id']}/{STORE_ID}",
        headers=headers,
        json={"min_reorder_level": 250},
    )
    assert level.status_code == 200, level.text
    saved = client.put(
        f"/api/v1/recipes/{CABLE_ID}",
        headers=headers,
        json={
            "yield_quantity": 1,
            "lines": [{"ingredient_id": beans["id"], "quantity": 18}, {"ingredient_id": milk["id"], "quantity": 200}],
        },
    )
    assert saved.status_code == 200, saved.text

    stock = client.get("/api/v1/inventory/stock", headers=headers, params={"store_id": STORE_ID}).json()
    assert "ACC-CABLE-USBC" not in [row["sku"] for row in stock["rows"]]
    assert stock["view"] == "stock"
    milk_row = next(row for row in stock["rows"] if row["sku"] == milk["sku"])
    assert milk_row["status"] != "out"

    menu = client.get(
        "/api/v1/inventory/stock", headers=headers, params={"store_id": STORE_ID, "view": "menu"}
    ).json()
    dish = next(row for row in menu["rows"] if row["sku"] == "ACC-CABLE-USBC")
    assert (dish["menu_status"], dish["max_portions"], dish["limiting_ingredient"]) == ("available", 1, "Milk")
    assert dish["availability_note"] == "1 portion available based on Milk stock"
    assert menu["out_count"] == 0

    assert push(client, "sale", sale_with([], 1500)).status_code == 200
    session.expire_all()
    alert = session.scalar(select(AuditLog).where(AuditLog.action == "inventory.reorder_alert"))
    assert alert is not None and alert.details["name"] == "Milk" and alert.details["on_hand"] == 100
    after = client.get(
        "/api/v1/inventory/stock", headers=headers, params={"store_id": STORE_ID, "view": "menu"}
    ).json()
    sold_out = next(row for row in after["rows"] if row["sku"] == "ACC-CABLE-USBC")
    assert sold_out["menu_status"] == "unavailable" and sold_out["status"] == "unavailable"
    assert after["out_count"] == 1
    physical = client.get("/api/v1/inventory/stock", headers=headers, params={"store_id": STORE_ID}).json()
    assert all(row["item_type"] != "MADE_TO_ORDER" for row in physical["rows"])


def _recipe(client, token: str) -> dict:
    seed_catalog(client)
    enable(client, token, "menu_modifiers", "recipes", "open_orders", "tables")
    pantry = category(client, token)
    milk = ingredient(client, token, "Milk", quantity=0, by_weight=False, category_id=pantry)
    saved = client.put(
        f"/api/v1/recipes/{CABLE_ID}",
        headers=bearer(token),
        json={"yield_quantity": 1, "lines": [{"ingredient_id": milk["id"], "quantity": 200}]},
    )
    assert saved.status_code == 200, saved.text
    return milk


def test_skip_recipe_follows_the_product_and_a_shortfall_still_sells(client, session: Session) -> None:
    token = admin_token(client)
    milk = _recipe(client, token)
    prepared = client.patch(
        f"/api/v1/products/{CABLE_ID}",
        headers=bearer(token),
        json={"sell_without_recipe": True},
    )
    assert prepared.status_code == 200 and prepared.json()["sell_without_recipe"] is True
    blocked = sale_with([], 1500)
    blocked["items"][0]["skip_recipe"] = False
    refused = push(client, "sale", blocked)
    assert refused.status_code == 422
    assert "menu item" in refused.json()["error"]["message"]
    assert on_hand(session, milk["id"]) == 0

    allowed = sale_with([], 1500)
    allowed["items"][0]["skip_recipe"] = True
    key = f"sale-{allowed['id']}"
    assert push(client, "sale", allowed, key=key).status_code == 200
    assert push(client, "sale", allowed, key=key).status_code == 200
    session.expire_all()
    assert on_hand(session, milk["id"]) == 0
    item = session.get(SaleItem, uuid.UUID(allowed["items"][0]["id"]))
    assert item is not None and item.skip_recipe is True and item.unit_price_cents == 1500 and item.quantity == 1
    assert session.scalar(select(RecipeUsage).where(RecipeUsage.sale_id == item.sale_id)) is None
    movements = session.scalars(select(StockMovement).where(StockMovement.movement_type == "RECIPE_OUT")).all()
    assert movements == []
    skipped = session.scalar(select(AuditLog).where(AuditLog.action == "recipe.skip"))
    assert skipped is not None and skipped.details["ingredient_requirement"] == "not_required"
    assert skipped.user_id is not None

    managed = client.patch(
        f"/api/v1/products/{CABLE_ID}",
        headers=bearer(token),
        json={"sell_without_recipe": False},
    )
    assert managed.status_code == 200, managed.text
    # The saved line keeps its skip. A new line draws, and a shortfall does not refuse the sale.
    assert session.get(SaleItem, uuid.UUID(allowed["items"][0]["id"])).skip_recipe is True
    drawn = sale_with([], 1500)
    assert push(client, "sale", drawn).status_code == 200
    session.expire_all()
    usage = session.scalar(select(RecipeUsage).where(RecipeUsage.sale_id == uuid.UUID(drawn["id"])))
    assert usage is not None and usage.quantity_drawn == 0 and usage.quantity_needed == 200


def test_an_order_line_skips_its_recipe_only_when_the_product_says_so(client, session: Session) -> None:
    token = admin_token(client)
    milk = _recipe(client, token)
    prepared = client.patch(
        f"/api/v1/products/{CABLE_ID}",
        headers=bearer(token),
        json={"sell_without_recipe": True},
    )
    assert prepared.status_code == 200, prepared.text
    floor = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Terrace"})
    assert floor.status_code == 201, floor.text
    area = floor.json()["areas"][0]
    tables = client.post(
        "/api/v1/dining/tables", headers=bearer(token), json={"area_id": area["id"], "label": "T1", "seats": 4}
    )
    table = tables.json()["areas"][0]["tables"][0]
    line = {
        "id": str(uuid.uuid4()),
        "product_id": CABLE_ID,
        "quantity": 2,
        "unit_price_cents": 1500,
        "skip_recipe": False,
    }
    denied = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 2,
            "user_id": CASHIER_ID,
            "items": [line],
        },
    )
    assert denied.status_code == 422 and "menu item" in denied.json()["error"]["message"]
    line["skip_recipe"] = True
    opened = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 2,
            "user_id": CASHIER_ID,
            "items": [line],
        },
    )
    assert opened.status_code == 201, opened.text
    saved = opened.json()["items"][0]
    assert saved["skip_recipe"] is True and saved["unit_price_cents"] == 1500 and saved["quantity"] == 2
    assert on_hand(session, milk["id"]) == 0
    again = client.get(f"/api/v1/orders/{opened.json()['id']}", headers=device())
    assert again.status_code == 200 and again.json()["items"][0]["skip_recipe"] is True
    extra = {**line, "id": str(uuid.uuid4()), "skip_recipe": True}
    added = client.post(
        f"/api/v1/orders/{opened.json()['id']}/items",
        headers=device(),
        json={"revision": opened.json()["revision"], "user_id": CASHIER_ID, "items": [extra]},
    )
    assert added.status_code == 200, added.text
    assert added.json()["status"] == "OPEN"
    assert [item["skip_recipe"] for item in added.json()["items"]] == [True, True]
    blocked_add = client.post(
        f"/api/v1/orders/{opened.json()['id']}/items",
        headers=device(),
        json={
            "revision": added.json()["revision"],
            "user_id": admin_id(client),
            "items": [{**line, "id": str(uuid.uuid4()), "skip_recipe": False}],
        },
    )
    assert blocked_add.status_code == 422
    enable(client, token, "kds")
    station = client.post(
        "/api/v1/kds/stations",
        headers=bearer(token),
        json={"store_id": STORE_ID, "name": "Kitchen", "is_default": True},
    )
    assert station.status_code == 201, station.text
    sent = client.post(
        f"/api/v1/orders/{opened.json()['id']}/send",
        headers=device(),
        json={"revision": added.json()["revision"], "user_id": admin_id(client)},
    )
    assert sent.status_code == 200, sent.text
    board = client.get(f"/api/v1/kds/stations/{station.json()['id']}/tickets", headers=device())
    assert board.status_code == 200, board.text
    flagged = [item for ticket in board.json()["tickets"] for item in ticket["items"] if item["skip_recipe"]]
    assert flagged and flagged[0]["voided_at"] is None and flagged[0]["ready_at"] is None
    assert on_hand(session, milk["id"]) == 0

