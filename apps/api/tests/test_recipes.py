import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import on_hand
from tests.test_menu import choice, enable, extras_group, sale_with
from tests.test_returns import CABLE_ID, STORE_ID, admin_token, bearer, push, seed_catalog
from tests.test_weighed import category

from app.models import AuditLog, SaleItem


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
