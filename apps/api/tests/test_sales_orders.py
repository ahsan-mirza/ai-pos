import uuid

import pytest
from sqlalchemy import select

from app.core import capabilities as catalog
from app.models.inventory import InventoryLevel
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from wholesale_support import CABLE, CASHIER_ID, PHONE, STORE, admin, create_customer, device, line, seed

SIGNATURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def enable_orders(client) -> None:
    headers, _ = admin(client)
    chosen = [capability.value for capability in catalog.ELECTRONICS_WHOLESALE] + ["sales_orders"]
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "electronics_wholesale", "capabilities": chosen},
    )
    assert response.status_code == 200, response.text


@pytest.fixture(autouse=True)
def orders_on(client) -> None:
    enable_orders(client)


def product(client, product_id: str) -> dict:
    return client.get(f"/api/v1/products/{product_id}", headers=device()).json()


def create(client, headers, customer_id: str, lines: list[dict], **extra):
    body = {"store_id": STORE, "customer_id": customer_id, "lines": lines, **extra}
    return client.post("/api/v1/sales-orders", headers=headers, json=body)


def test_partial_delivery_backorder_and_allocation(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    created = create(client, headers, customer["id"], [{"product_id": CABLE, "quantity": 600}], confirm=True)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["number"] == "DT-01-SO-000001"
    assert order["status"] == "CONFIRMED"
    assert order["total_cents"] == 600 * 1500
    order_line = order["lines"][0]
    assert order_line["quantity_reserved"] == 500 and order_line["backordered"] == 100
    assert product(client, CABLE)["quantity_reserved"] == 500

    waiting = client.get("/api/v1/sales-orders/backorders", headers=headers).json()
    assert [(row["order_number"], row["backordered"]) for row in waiting] == [(order["number"], 100)]

    picked = client.post(f"/api/v1/sales-orders/{order['id']}/pick", headers=headers)
    assert picked.status_code == 200, picked.text
    assert picked.json()["status"] == "PICKING"
    pick = picked.json()["pick_lists"][0]
    assert pick["lines"][0]["quantity"] == 500
    pdf = client.get(f"/api/v1/sales-orders/pick-lists/{pick['id']}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    first = client.post(
        f"/api/v1/sales-orders/{order['id']}/dispatch",
        headers=headers,
        json={"lines": [{"order_line_id": order_line["id"], "quantity": 300}], "vehicle": "VAN-1"},
    )
    assert first.status_code == 200, first.text
    state = first.json()
    assert state["status"] == "PARTIALLY_DELIVERED"
    assert state["lines"][0]["quantity_delivered"] == 300
    assert state["lines"][0]["quantity_reserved"] == 200
    note = state["deliveries"][0]
    assert note["number"] == "DT-01-DN-000001"
    assert note["invoice_total_cents"] == 300 * 1500
    stock = product(client, CABLE)
    assert stock["stock_quantity"] == 200 and stock["quantity_reserved"] == 200

    invoice = session.get(Sale, uuid.UUID(note["sale_id"]))
    assert invoice.sales_order_id == uuid.UUID(order["id"])
    assert invoice.payment_method == "on_account"
    items = session.scalars(select(SaleItem).where(SaleItem.sale_id == invoice.id)).all()
    assert {item.sales_order_line_id for item in items} == {uuid.UUID(order_line["id"])}

    level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(CABLE), InventoryLevel.store_id == uuid.UUID(STORE)
        )
    )
    level.quantity_on_hand += 150
    session.commit()
    allocated = client.post(f"/api/v1/sales-orders/{order['id']}/allocate", headers=headers).json()
    assert allocated["lines"][0]["quantity_reserved"] == 300 and allocated["lines"][0]["backordered"] == 0

    rest = client.post(
        f"/api/v1/sales-orders/{order['id']}/dispatch",
        headers=headers,
        json={"lines": [{"order_line_id": order_line["id"], "quantity": 300}]},
    )
    assert rest.status_code == 200, rest.text
    assert rest.json()["status"] == "DELIVERED"
    assert rest.json()["delivered_cents"] == order["total_cents"]
    assert product(client, CABLE)["quantity_reserved"] == 0
    invoices = session.scalars(select(Sale).where(Sale.sales_order_id == uuid.UUID(order["id"]))).all()
    assert sorted(sale.total_cents for sale in invoices) == [300 * 1500, 300 * 1500]

    over = client.post(
        f"/api/v1/sales-orders/{order['id']}/dispatch",
        headers=headers,
        json={"lines": [{"order_line_id": order_line["id"], "quantity": 1}]},
    )
    assert over.status_code == 409


def test_credit_limit_blocks_confirmation_without_approval(client) -> None:
    seed(client)
    headers, admin_id = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=50_000)
    order = create(client, headers, customer["id"], [{"product_id": CABLE, "quantity": 40}]).json()
    assert order["status"] == "DRAFT"
    assert product(client, CABLE)["quantity_reserved"] == 0

    blocked = client.post(f"/api/v1/sales-orders/{order['id']}/confirm", headers=headers, json={})
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "credit_limit"

    approved = client.post(
        f"/api/v1/sales-orders/{order['id']}/confirm", headers=headers, json={"credit_approved_by_id": admin_id}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "CONFIRMED"
    assert product(client, CABLE)["quantity_reserved"] == 40


def test_serialized_dispatch_assigns_imeis_and_records_pod(client, session) -> None:
    values = seed(client, phone_units=3)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    order = create(client, headers, customer["id"], [{"product_id": PHONE, "quantity": 2}], confirm=True).json()
    order_line = order["lines"][0]
    assert order_line["is_serialized"] and order_line["quantity_reserved"] == 2

    shipped = client.post(
        f"/api/v1/sales-orders/{order['id']}/dispatch",
        headers=headers,
        json={"lines": [{"order_line_id": order_line["id"], "quantity": 2}]},
    )
    assert shipped.status_code == 200, shipped.text
    note = shipped.json()["deliveries"][0]
    assert len(note["lines"][0]["serial_suffixes"]) == 2
    sale_out = client.get(f"/api/v1/sales/{note['sale_id']}", headers=device()).json()
    sold = [item["serial_value"] for item in sale_out["items"]]
    assert len(sold) == 2 and set(sold) <= set(values)

    signed = client.post(
        f"/api/v1/sales-orders/deliveries/{note['id']}/deliver",
        headers=headers,
        json={"receiver_name": "Omar at reception", "signature": SIGNATURE},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "DELIVERED" and signed.json()["has_signature"]
    again = client.post(
        f"/api/v1/sales-orders/deliveries/{note['id']}/deliver", headers=headers, json={"receiver_name": "Omar"}
    )
    assert again.status_code == 409

    for path in (f"/api/v1/sales-orders/deliveries/{note['id']}/pdf", f"/api/v1/sales-orders/{order['id']}/pdf"):
        pdf = client.get(path, headers=headers)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_quote_becomes_order_and_moves_the_hold(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    quote_id = str(uuid.uuid4())
    items = [line(CABLE, 30, 1500)]
    quote = client.post(
        "/api/v1/quotes",
        headers=device(),
        json={
            "id": quote_id,
            "store_id": STORE,
            "cashier_id": CASHIER_ID,
            "currency": "USD",
            "sale_type": "WHOLESALE",
            "customer_id": customer["id"],
            "valid_days": 7,
            "subtotal_cents": 45_000,
            "tax_cents": 0,
            "total_cents": 45_000,
            "items": items,
        },
    )
    assert quote.status_code == 201, quote.text
    assert product(client, CABLE)["quantity_reserved"] == 30

    converted = client.post(f"/api/v1/sales-orders/from-quote/{quote_id}", headers=headers)
    assert converted.status_code == 201, converted.text
    order = converted.json()
    assert order["status"] == "CONFIRMED" and order["source"] == "quote"
    assert order["lines"][0]["quantity_ordered"] == 30 and order["lines"][0]["quantity_reserved"] == 30
    assert product(client, CABLE)["quantity_reserved"] == 30
    assert client.get(f"/api/v1/quotes/{quote_id}", headers=headers).json()["quote_status"] == "CONVERTED"
    assert client.post(f"/api/v1/sales-orders/from-quote/{quote_id}", headers=headers).status_code == 422


def test_cancel_releases_stock_and_agreed_prices_need_approval(client) -> None:
    seed(client)
    headers, admin_id = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    cheaper = [{"product_id": CABLE, "quantity": 10, "unit_price_cents": 1100}]
    assert create(client, headers, customer["id"], cheaper).status_code == 403
    order = create(client, headers, customer["id"], cheaper, confirm=True, price_approved_by_id=admin_id).json()
    assert order["lines"][0]["unit_price_cents"] == 1100 and order["lines"][0]["list_price_cents"] == 1500
    assert product(client, CABLE)["quantity_reserved"] == 10

    trimmed = client.post(
        f"/api/v1/sales-orders/{order['id']}/cancel-lines",
        headers=headers,
        json={"lines": [{"order_line_id": order["lines"][0]["id"], "quantity": 4}], "reason": "Customer cut back"},
    )
    assert trimmed.status_code == 200, trimmed.text
    assert trimmed.json()["lines"][0]["outstanding"] == 6
    assert product(client, CABLE)["quantity_reserved"] == 6

    cancelled = client.post(
        f"/api/v1/sales-orders/{order['id']}/cancel", headers=headers, json={"reason": "Order withdrawn"}
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert product(client, CABLE)["quantity_reserved"] == 0
    listing = client.get("/api/v1/sales-orders", headers=headers, params={"status": "CANCELLED"})
    assert listing.headers["X-Total-Count"] == "1"


def test_register_saves_an_order_for_its_cashier(client) -> None:
    seed(client)
    headers, admin_id = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    saved = create(
        client,
        device(),
        customer["id"],
        [{"product_id": CABLE, "quantity": 5}],
        user_id=admin_id,
        source="register",
        confirm=True,
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["source"] == "register"
    nobody = create(client, device(), customer["id"], [{"product_id": CABLE, "quantity": 5}])
    assert nobody.status_code == 422


def test_module_off_hides_orders(client) -> None:
    headers, _ = admin(client)
    chosen = [capability.value for capability in catalog.ELECTRONICS_WHOLESALE]
    client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "electronics_wholesale", "capabilities": chosen},
    )
    assert client.get("/api/v1/sales-orders", headers=headers).status_code == 403
