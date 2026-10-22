import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import on_hand
from tests.test_kds import MODULES, board, floor_table, stations
from tests.test_menu import enable
from tests.test_orders import settle
from tests.test_recipes import ingredient
from tests.test_returns import CABLE_ID, CASHIER_ID, PHONE_ID, STORE_ID, admin_token, bearer, device, push, seed_catalog
from tests.test_weighed import category

from app.models import KitchenTicket, SaleItem

BURGER_ID = "00000000-0000-4000-8000-000000000081"
FRIES_ID = "00000000-0000-4000-8000-000000000082"


def menu_item(client, product_id: str, sku: str, name: str, category_name: str, price: int, stock: int) -> None:
    payload = {
        "id": product_id,
        "store_id": STORE_ID,
        "sku": sku,
        "barcode": f"10000000{sku[-4:]}",
        "name": name,
        "category": category_name,
        "price_cents": price,
        "currency": "USD",
        "is_serialized": False,
        "stock_quantity": stock,
    }
    assert push(client, "product", payload).status_code == 200


def burger_meal(client, token: str) -> dict:
    """Main: Burger. Side: Cable (default, stocked) or Fries (+2.00, cooked from a recipe)."""
    menu_item(client, BURGER_ID, "FD-0081", "Burger", "Mains", 1800, 20)
    menu_item(client, FRIES_ID, "FD-0082", "Fries", "Sides", 900, 0)
    response = client.post(
        "/api/v1/menu/combos",
        headers=bearer(token),
        json={
            "name": "Burger Meal",
            "category": "Meals",
            "price_cents": 2500,
            "slots": [
                {"name": "Main", "options": [{"product_id": BURGER_ID, "is_default": True}]},
                {
                    "name": "Side",
                    "options": [
                        {"product_id": CABLE_ID, "is_default": True},
                        {"product_id": FRIES_ID, "surcharge_cents": 200},
                    ],
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def pick(meal: dict, slot: int, product_id: str) -> dict:
    return {"slot_id": meal["slots"][slot]["id"], "product_id": product_id}


def meal_sale(meal: dict, components: list[dict], unit: int) -> dict:
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
                "product_id": meal["product_id"],
                "quantity": 1,
                "unit_price_cents": unit,
                "list_price_cents": unit,
                "tax_cents": 0,
                "line_total_cents": unit,
                "components": components,
            }
        ],
    }


def test_meals_are_validated_and_offered_to_registers(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert client.get("/api/v1/menu/combos", headers=bearer(token)).status_code == 403
    enable(client, token, "menu_modifiers")
    meal = burger_meal(client, token)
    assert meal["sku"].startswith("MEAL-")
    assert [slot["name"] for slot in meal["slots"]] == ["Main", "Side"]
    assert [(option["name"], option["surcharge_cents"]) for option in meal["slots"][1]["options"]] == [
        ("USB-C Cable", 0),
        ("Fries", 200),
    ]

    menu = client.get("/api/v1/menu/register", headers=device()).json()
    assert list(menu["combos"]) == [meal["product_id"]]
    listed = client.get("/api/v1/menu/combos", headers=bearer(token)).json()
    assert [combo["name"] for combo in listed] == ["Burger Meal"]

    def create(slot_options: list[dict]):
        return client.post(
            "/api/v1/menu/combos",
            headers=bearer(token),
            json={
                "name": "Bad",
                "category": "Meals",
                "price_cents": 100,
                "slots": [{"name": "X", "options": slot_options}],
            },
        )

    assert create([{"product_id": meal["product_id"]}]).status_code == 422  # meals do not nest
    assert create([{"product_id": PHONE_ID}]).status_code == 422  # serialized items are sold with their IMEI
    assert create([{"product_id": BURGER_ID}, {"product_id": BURGER_ID}]).status_code == 422

    edited = client.put(
        f"/api/v1/menu/combos/{meal['product_id']}",
        headers=bearer(token),
        json={
            "name": "Burger Meal",
            "category": "Meals",
            "price_cents": 2600,
            "slots": [{"name": "Main", "options": [{"product_id": BURGER_ID, "is_default": True}]}],
        },
    )
    assert edited.status_code == 200 and edited.json()["price_cents"] == 2600
    assert client.delete(f"/api/v1/menu/combos/{meal['product_id']}", headers=bearer(token)).status_code == 204
    assert client.get("/api/v1/menu/register", headers=device()).json()["combos"] == {}


def test_meal_sales_price_surcharges_and_draw_each_part(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "menu_modifiers", "recipes")
    meal = burger_meal(client, token)
    potatoes = ingredient(client, token, "Potatoes", quantity=1000, by_weight=True, category_id=category(client, token))
    recipe = client.put(
        f"/api/v1/recipes/{FRIES_ID}",
        headers=bearer(token),
        json={"yield_quantity": 1, "lines": [{"ingredient_id": potatoes["id"], "quantity": 150}]},
    )
    assert recipe.status_code == 200, recipe.text

    missing = push(client, "sale", meal_sale(meal, [pick(meal, 1, CABLE_ID)], 2500))
    assert missing.status_code == 422 and "needs a choice of Main" in missing.json()["error"]["message"]
    stranger = push(client, "sale", meal_sale(meal, [pick(meal, 0, BURGER_ID), pick(meal, 0, CABLE_ID)], 2500))
    assert stranger.status_code == 422

    burger_before, cable_before = on_hand(session, BURGER_ID), on_hand(session, CABLE_ID)
    plain = meal_sale(meal, [pick(meal, 0, BURGER_ID), pick(meal, 1, CABLE_ID)], 2500)
    assert push(client, "sale", plain).status_code == 200
    assert (on_hand(session, BURGER_ID), on_hand(session, CABLE_ID)) == (burger_before - 1, cable_before - 1)

    upgraded = meal_sale(meal, [pick(meal, 0, BURGER_ID), pick(meal, 1, FRIES_ID)], 2700)
    response = push(client, "sale", upgraded)
    assert response.status_code == 200, response.text
    assert on_hand(session, BURGER_ID) == burger_before - 2
    assert on_hand(session, CABLE_ID) == cable_before - 1
    assert on_hand(session, potatoes["id"]) == 1000 - 150
    item = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(upgraded["items"][0]["id"])))
    assert item is not None and item.unit_price_cents == 2700
    assert [(part["slot"], part["name"], part["surcharge_cents"]) for part in item.components] == [
        ("Main", "Burger", 0),
        ("Side", "Fries", 200),
    ]
    assert item.cost_estimated is True


def test_meal_parts_fire_to_their_own_stations_and_settle(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    meal = burger_meal(client, token)
    bar, kitchen = stations(client, token, session)
    table = floor_table(client, token)
    components = [pick(meal, 0, BURGER_ID), pick(meal, 1, CABLE_ID)]
    item = {
        "id": str(uuid.uuid4()),
        "product_id": meal["product_id"],
        "quantity": 1,
        "unit_price_cents": 2500,
        "components": components,
    }
    bad = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "user_id": CASHIER_ID,
            "items": [{**item, "id": str(uuid.uuid4()), "components": components[1:]}],
        },
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_meal"

    created = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "user_id": CASHIER_ID,
            "items": [item],
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert len(order["items"][0]["components"]) == 2
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send", headers=device(), json={"revision": 1, "user_id": CASHIER_ID}
    )
    assert sent.status_code == 200, sent.text

    bar_items = board(client, bar)["tickets"][0]["items"]
    kitchen_items = board(client, kitchen)["tickets"][0]["items"]
    assert [(entry["product_name"], entry["combo_name"]) for entry in bar_items] == [("USB-C Cable", "Burger Meal")]
    assert [(entry["product_name"], entry["combo_name"]) for entry in kitchen_items] == [("Burger", "Burger Meal")]
    assert session.scalar(select(KitchenTicket.id).where(KitchenTicket.order_id == uuid.UUID(order["id"]))) is not None

    sale = settle(sent.json(), [item["id"]])
    sale["items"][0]["components"] = components
    response = push(client, "sale", sale)
    assert response.status_code == 200, response.text
    paid = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assert paid["status"] == "SETTLED"
