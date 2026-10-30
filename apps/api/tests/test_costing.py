import uuid

from app.models.batch import BatchItem, PurchaseBatch
from app.models.sale_item import SaleItem
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, device, event, line, push, sale, seed


def add_batch(session, *, quantity: int, cost: int) -> None:
    batch = PurchaseBatch(
        batch_number=f"B-{uuid.uuid4().hex[:6]}",
        store_id=uuid.UUID(STORE),
        import_source="MANUAL",
        currency="USD",
        total_cost_amount=quantity * cost,
        total_items_count=quantity,
        created_by_id=uuid.UUID(CASHIER_ID),
    )
    session.add(batch)
    session.flush()
    session.add(
        BatchItem(
            batch_id=batch.id,
            product_id=uuid.UUID(CABLE),
            store_id=uuid.UUID(STORE),
            quantity_imported=quantity,
            quantity_remaining=quantity,
            purchase_cost_per_unit=cost,
            selling_price_per_unit=1500,
        )
    )
    session.commit()


def test_sale_lines_carry_fifo_cost(client, session) -> None:
    seed(client)
    add_batch(session, quantity=3, cost=600)
    add_batch(session, quantity=10, cost=700)
    body = sale([line(CABLE, 5, 1500)])
    assert push(client, [event("fifo-sale-key", "sale", body)]).status_code == 200
    item = session.get(SaleItem, uuid.UUID(body["items"][0]["id"]))
    assert item.cost_cents == 3 * 600 + 2 * 700
    assert item.cost_estimated is False


def test_goods_receipt_opens_a_cost_layer(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Volt",
            "destination_store_id": STORE,
            "lines": [{"product_id": CABLE, "quantity_ordered": 5, "unit_cost_cents": 640}],
        },
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": order["lines"][0]["id"], "quantity": 5}]},
    )
    assert received.status_code == 200, received.text
    body = sale([line(CABLE, 2, 1500)])
    assert push(client, [event("estimated-sale", "sale", body)]).status_code == 200
    item = session.get(SaleItem, uuid.UUID(body["items"][0]["id"]))
    assert (item.cost_cents, item.cost_estimated) == (1280, False)
    summary = client.get("/api/v1/analytics/summary", headers=device()).json()
    assert summary["cogs_cents"] == 1280
    assert summary["gross_margin_cents"] == 3000 - 1280
