import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_token, bearer, push, seed_catalog

from app.core import capabilities as catalog
from app.models import AuditLog, CatalogChange, SaleItem


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


def test_register_pin_can_save_portion_prices(client) -> None:
    """The till saves portions with the same pos-scoped token that creates the menu item."""
    seed_catalog(client)
    portal = admin_token(client)
    as_cafe(client, portal)
    pin = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "admin", "pin": "2468"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert pin.status_code == 200, pin.text
    assert pin.json()["scope"] == "pos"
    token = pin.json()["access_token"]
    saved = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"name": "Small Plate", "price_cents": 300},
                {"name": "Full Plate", "price_cents": 900},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert [option["name"] for option in saved.json()] == ["Small Plate", "Full Plate"]
    modifiers = client.post(
        "/api/v1/menu/modifier-groups",
        headers=bearer(token),
        json={"name": "Milk", "min_select": 0, "max_select": 1, "options": [{"name": "Oat", "price_delta_cents": 0}]},
    )
    assert modifiers.status_code == 403
    assert modifiers.json()["error"]["message"] == "This token cannot be used for this action."


def test_priced_options_are_required_and_snapshotted(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    as_cafe(client, token)
    created = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"name": "Breakfast", "price_cents": 800},
                {"name": "Lunch", "price_cents": 1200},
                {"name": "Dinner", "price_cents": 1500},
            ]
        },
    )
    assert created.status_code == 200, created.text
    options = created.json()
    assert [option["name"] for option in options] == ["Breakfast", "Lunch", "Dinner"]
    duplicate = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={"options": [{"name": "Breakfast", "price_cents": 800}, {"name": "breakfast", "price_cents": 900}]},
    )
    assert duplicate.status_code == 422
    menu = client.get("/api/v1/menu/register", headers=bearer(token)).json()
    assert [option["name"] for option in menu["price_options"][CABLE_ID]] == ["Breakfast", "Lunch", "Dinner"]

    missing = sale_with([], 800)
    refused = push(client, "sale", missing)
    assert refused.status_code == 422 and "priced option" in refused.json()["error"]["message"]

    forged = sale_with([], 1)
    forged["items"][0]["price_option_id"] = options[0]["id"]
    assert push(client, "sale", forged).status_code == 422

    good = sale_with([], 800)
    good["items"][0]["price_option_id"] = options[0]["id"]
    recorded = push(client, "sale", good)
    assert recorded.status_code == 200, recorded.text
    item = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(good["items"][0]["id"])))
    assert item.price_option_name == "Breakfast"
    assert item.price_option_cents == 800
    assert item.unit_price_cents == 800

    client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"id": options[0]["id"], "name": "Breakfast", "price_cents": 900},
                {"id": options[1]["id"], "name": "Lunch", "price_cents": 1200},
                {"id": options[2]["id"], "name": "Dinner", "price_cents": 1500},
            ]
        },
    )
    session.expire_all()
    kept = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(good["items"][0]["id"])))
    assert kept.price_option_cents == 800
    assert kept.unit_price_cents == 800
    replay = sale_with([], 800)
    replay["items"][0]["price_option_id"] = options[0]["id"]
    replayed = push(client, "sale", replay)
    assert replayed.status_code == 200, replayed.text


def test_portion_prices_keep_identity_history_and_reject_bad_writes(client, session: Session) -> None:
    """Business Pro and the register write the same menu_price_options rows."""
    seed_catalog(client)
    token = admin_token(client)
    as_cafe(client, token)
    created = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"name": "Small Plate", "price_cents": 300, "position": 0},
                {"name": "Medium Plate", "price_cents": 500, "position": 1},
                {"name": "Full Plate", "price_cents": 900, "position": 2},
            ]
        },
    )
    assert created.status_code == 200, created.text
    options = created.json()
    ids = [row["id"] for row in options]
    assert [row["name"] for row in options] == ["Small Plate", "Medium Plate", "Full Plate"]
    assert [row["price_cents"] for row in options] == [300, 500, 900]

    listed = client.get("/api/v1/products", headers=bearer(token), params={"limit": 500})
    assert listed.status_code == 200, listed.text
    cable = next(row for row in listed.json() if row["id"] == CABLE_ID)
    assert [row["id"] for row in cable["price_options"]] == ids

    menu = client.get("/api/v1/menu/register", headers=bearer(token)).json()
    assert [row["id"] for row in menu["price_options"][CABLE_ID]] == ids

    session.expire_all()
    changes = session.scalars(
        select(CatalogChange).where(CatalogChange.dataset == "menu", CatalogChange.record_id.in_(ids))
    ).all()
    assert {row.record_id for row in changes} == set(ids)
    audits = session.scalars(
        select(AuditLog).where(
            AuditLog.target_entity == "MenuPriceOption",
            AuditLog.target_entity_id.in_([uuid.UUID(row) for row in ids]),
        )
    ).all()
    assert {str(row.target_entity_id) for row in audits} == set(ids)

    blank = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={"options": [{"name": "  ", "price_cents": 100}, {"name": "Full Plate", "price_cents": 900}]},
    )
    assert blank.status_code == 422
    assert "Option name is required" in blank.json()["error"]["message"]
    negative = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={"options": [{"name": "Small Plate", "price_cents": -1}, {"name": "Full Plate", "price_cents": 900}]},
    )
    assert negative.status_code == 422
    inactive = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"id": ids[0], "name": "Small Plate", "price_cents": 300, "is_active": False},
                {"id": ids[2], "name": "Full Plate", "price_cents": 900, "is_active": False},
            ]
        },
    )
    assert inactive.status_code == 422
    assert "stay active" in inactive.json()["error"]["message"]
    single = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={"options": [{"name": "Only Plate", "price_cents": 300}]},
    )
    assert single.status_code == 422

    category = client.post("/api/v1/categories", headers=bearer(token), json={"name": f"Drinks {uuid.uuid4().hex[:6]}"})
    assert category.status_code in (200, 201), category.text
    water = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "barcode": "281000000301",
            "name": "Mineral Water",
            "category_id": category.json()["id"],
            "price_cents": 200,
            "item_type": "PRE_PACKAGED",
        },
    )
    assert water.status_code == 201, water.text
    foreign = client.put(
        f"/api/v1/menu/products/{water.json()['id']}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"id": ids[0], "name": "Small Plate", "price_cents": 300},
                {"name": "Bottle", "price_cents": 200},
            ]
        },
    )
    assert foreign.status_code == 422
    assert "does not belong" in foreign.json()["error"]["message"]
    zero = client.put(
        f"/api/v1/menu/products/{water.json()['id']}/price-options",
        headers=bearer(token),
        json={"options": [{"name": "Still", "price_cents": 0}, {"name": "Sparkling", "price_cents": 200}]},
    )
    assert zero.status_code == 200, zero.text
    assert zero.json()[0]["price_cents"] == 0

    cashier = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": "1357"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert cashier.status_code == 200, cashier.text
    refused = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(cashier.json()["access_token"]),
        json={"options": [{"name": "Small Plate", "price_cents": 1}, {"name": "Full Plate", "price_cents": 2}]},
    )
    assert refused.status_code == 403

    good = sale_with([], 900)
    good["items"][0]["price_option_id"] = ids[2]
    assert push(client, "sale", good).status_code == 200, good
    edited = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"id": ids[0], "name": "Small Plate", "price_cents": 300},
                {"id": ids[1], "name": "Medium Plate", "price_cents": 550},
                {"id": ids[2], "name": "Full Plate", "price_cents": 900},
            ]
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()[1]["id"] == ids[1] and edited.json()[1]["price_cents"] == 550
    session.expire_all()
    kept = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(good["items"][0]["id"])))
    assert kept.price_option_id == uuid.UUID(ids[2])
    assert kept.price_option_name == "Full Plate"
    assert kept.price_option_cents == 900
    assert kept.unit_price_cents == 900

    dropped = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={
            "options": [
                {"id": ids[0], "name": "Small Plate", "price_cents": 300},
                {"id": ids[1], "name": "Medium Plate", "price_cents": 550},
            ]
        },
    )
    assert dropped.status_code == 200, dropped.text
    retired = next(row for row in dropped.json() if row["id"] == ids[2])
    assert retired["is_active"] is False
    session.expire_all()
    still = session.scalar(select(SaleItem).where(SaleItem.id == uuid.UUID(good["items"][0]["id"])))
    assert still.price_option_cents == 900 and still.unit_price_cents == 900

    cleared = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/price-options",
        headers=bearer(token),
        json={"options": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert [row for row in cleared.json() if row["is_active"]] == []
    assert any(row["id"] == ids[2] and row["is_active"] is False for row in cleared.json())
    again = client.get("/api/v1/products", headers=bearer(token), params={"limit": 500})
    cable = next(row for row in again.json() if row["id"] == CABLE_ID)
    assert cable["price_options"] == []
