import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from tests.test_batches import on_hand
from tests.test_returns import (
    CASHIER_ID,
    STORE_ID,
    admin_id,
    admin_token,
    approval,
    bearer,
    push,
    receipt,
    seed_catalog,
)

from app.services import weighed

APPLES_PER_KG = 1299


def category(client, token: str) -> str:
    response = client.post("/api/v1/categories", headers=bearer(token), json={"name": "Produce"})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def apples(client, token: str, *, grams: int = 10_000) -> dict:
    response = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": "PRD-APPLE-RED",
            "barcode": "2000000000001",
            "name": "Red apples",
            "category_id": category(client, token),
            "price_cents": APPLES_PER_KG,
            "sold_by_weight": True,
            "plu_code": "4016",
            "tare_grams": 15,
            "opening_store_id": STORE_ID,
            "opening_quantity": grams,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def weighed_sale(product_id: str, grams: int, *, per_kg: int = APPLES_PER_KG, line_cents: int | None = None) -> dict:
    line = weighed.amount(grams, per_kg, 1000) if line_cents is None else line_cents
    sale_id = str(uuid.uuid4())
    return {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": line,
        "tax_cents": 0,
        "total_cents": line,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": grams,
                "unit_price_cents": per_kg,
                "tax_cents": 0,
                "line_total_cents": line,
            }
        ],
    }


def test_weight_math_rounds_half_up() -> None:
    assert weighed.amount(1234, 1299, 1000) == 1603  # 1602.966
    assert weighed.amount(500, 1001, 1000) == 501  # 500.5 rounds up
    assert weighed.amount(3, 7, 1) == 21
    assert weighed.format_weight(950) == "950 g" and weighed.format_weight(1234) == "1.234 kg"


def test_portal_creates_weighed_products_with_unique_plu(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    product = apples(client, token)
    assert (product["sold_by_weight"], product["plu_code"], product["tare_grams"]) == (True, "4016", 15)
    assert product["stock_quantity"] == 10_000
    clash = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": "PRD-APPLE-GREEN",
            "barcode": "2000000000002",
            "name": "Green apples",
            "category_id": product["category_id"],
            "price_cents": 1499,
            "sold_by_weight": True,
            "plu_code": "4016",
        },
    )
    assert clash.status_code == 409
    serial = client.post(
        "/api/v1/inventory/products",
        headers=bearer(token),
        json={
            "sku": "X-1",
            "barcode": "x1",
            "name": "X",
            "category_id": product["category_id"],
            "price_cents": 1,
            "sold_by_weight": True,
            "is_serialized": True,
        },
    )
    assert serial.status_code == 422
    locked = client.patch(f"/api/v1/products/{product['id']}", headers=bearer(token), json={"sold_by_weight": False})
    assert locked.status_code == 422 and locked.json()["error"]["code"] == "stock_on_hand"


def test_weighed_sale_draws_grams_and_partial_return(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    product = apples(client, token)

    wrong = weighed_sale(product["id"], 1234, line_cents=1299 * 1234)
    assert push(client, "sale", wrong).status_code == 422

    sale = weighed_sale(product["id"], 1234)
    assert sale["total_cents"] == 1603
    response = push(client, "sale", sale)
    assert response.status_code == 200, response.text
    assert on_hand(session, product["id"]) == 10_000 - 1234

    body = receipt(client, sale["id"])
    line = body["items"][0]
    assert line["sold_by_weight"] is True and line["quantity"] == 1234
    returned_grams = 500
    subtotal = weighed.amount(returned_grams, line["unit_price_cents"], 1000)
    refund = {
        "id": str(uuid.uuid4()),
        "original_sale_id": body["sale_id"],
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "processed_at": datetime.now(UTC).isoformat(),
        "subtotal_cents": subtotal,
        "tax_refund_cents": 0,
        "restocking_fee_cents": 0,
        "total_refund_cents": subtotal,
        "reason_notes": "Bruised apples.",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "sale_item_id": line["sale_item_id"],
                "product_id": line["product_id"],
                "quantity": returned_grams,
                "unit_price_cents": line["unit_price_cents"],
                "tax_refund_cents": 0,
                "restocking_fee_cents": 0,
                "refund_cents": subtotal,
                "condition_status": "unopened_resealable",
                "reason_code": "changed_mind",
            }
        ],
        "tenders": [{"method": "cash", "amount_cents": subtotal}],
        "override": approval(admin_id(client)),
    }
    returned = push(client, "sale_return", refund)
    assert returned.status_code == 200, returned.text
    assert subtotal == 650
    assert on_hand(session, product["id"]) == 10_000 - 1234 + 500
