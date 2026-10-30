"""Beige Frost: two purchases of one product keep their own costs, and sales keep the cost they posted with."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.batch import BatchItem
from app.models.product import Product
from app.models.sale_item import SaleItem
from app.tenancy.context import TenantRef, use_tenant
from wholesale_support import STORE, admin, event, line, push, sale, seed

TODAY = datetime.now(UTC).date()
SPAN = {"from": "2026-10-01", "to": str(TODAY)}
PRICE = 15_000  # 150.00
COST_A = 10_000  # 100.00
COST_B = 11_000  # 110.00


def _product(client) -> str:
    product_id = str(uuid.uuid4())
    response = push(
        client,
        [
            event(
                f"frost-{product_id[:8]}",
                "product",
                {
                    "id": product_id,
                    "store_id": STORE,
                    "sku": f"FRST-{product_id[:8]}",
                    "barcode": product_id.replace("-", "")[:12],
                    "name": "Beige Frost",
                    "category": "Paint",
                    "price_cents": PRICE,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 0,
                },
            )
        ],
    )
    assert response.status_code == 200, response.text
    return product_id


def _receive(client, headers: dict[str, str], product_id: str, quantity: int, cost: int) -> None:
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Gulf Coatings",
            "destination_store_id": STORE,
            "lines": [{"product_id": product_id, "quantity_ordered": quantity, "unit_cost_cents": cost}],
        },
    )
    assert order.status_code == 201, order.text
    body = order.json()
    placed = client.post(f"/api/v1/inventory/purchase-orders/{body['id']}/order", headers=headers)
    assert placed.status_code == 200, placed.text
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{body['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": body["lines"][0]["id"], "quantity": quantity}]},
    )
    assert received.status_code == 200, received.text


def _sell(client, product_id: str, quantity: int, key: str) -> dict:
    body = sale([line(product_id, quantity, PRICE)])
    response = push(client, [event(key, "sale", body)])
    assert response.status_code == 200, response.text
    return body


def _layers(client, headers: dict[str, str], product_id: str) -> dict:
    response = client.get(f"/api/v1/products/{product_id}/costing", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_beige_frost_keeps_each_purchase_cost_under_fifo(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    product_id = _product(client)
    _receive(client, headers, product_id, 20, COST_A)
    first = _sell(client, product_id, 15, "frost-sale-15")
    item = session.get(SaleItem, uuid.UUID(first["items"][0]["id"]))
    assert item is not None
    assert item.cost_cents == 15 * COST_A
    assert item.cost_estimated is False

    _receive(client, headers, product_id, 20, COST_B)
    session.expire_all()
    assert session.get(SaleItem, item.id).cost_cents == 15 * COST_A
    assert session.scalar(select(func.count()).select_from(Product).where(Product.name == "Beige Frost")) == 1

    costing = _layers(client, headers, product_id)
    assert costing["method"] == "FIFO"
    assert costing["on_hand"] == 25
    assert costing["uncosted_quantity"] == 0
    assert costing["inventory_value_cents"] == 5 * COST_A + 20 * COST_B
    assert costing["last_purchase_cost_cents"] == COST_B
    layers = [
        (row["original_quantity"], row["remaining_quantity"], row["unit_cost_cents"]) for row in costing["layers"]
    ]
    assert layers == [(20, 5, COST_A), (20, 20, COST_B)]
    assert costing["realized_cogs_cents"] == 15 * COST_A
    assert costing["realized_profit_cents"] == 15 * PRICE - 15 * COST_A

    second = _sell(client, product_id, 7, "frost-sale-7")
    again = push(client, [event("frost-sale-7", "sale", second)])
    assert again.status_code == 200, again.text
    sold = session.get(SaleItem, uuid.UUID(second["items"][0]["id"]))
    assert sold is not None and sold.cost_cents == 5 * COST_A + 2 * COST_B

    costing = _layers(client, headers, product_id)
    assert costing["on_hand"] == 18
    assert costing["inventory_value_cents"] == 18 * COST_B
    left = [(row["remaining_quantity"], row["unit_cost_cents"]) for row in costing["layers"]]
    assert left == [(0, COST_A), (18, COST_B)]
    history = client.get(f"/api/v1/products/{product_id}/purchase-history", headers=headers).json()
    assert [row["unit_cost_cents"] for row in history["rows"] if row["received_at"]] == [COST_B, COST_A]
    sales = client.get(f"/api/v1/products/{product_id}/sales-history", headers=headers).json()
    by_qty = {row["quantity"]: row["cost_cents"] for row in sales["rows"]}
    assert by_qty == {15: 15 * COST_A, 7: 5 * COST_A + 2 * COST_B}

    posted = client.post("/api/v1/accounting/post", headers=headers, json=SPAN)
    assert posted.status_code == 200, posted.text
    assert posted.json()["unbalanced"] == []
    sheet = client.get("/api/v1/accounting/balance-sheet", headers=headers).json()
    inventory = next(row for row in sheet["checks"] if row["key"] == "inventory")
    assert inventory["difference_cents"] == 0
    assert inventory["subledger_cents"] == 18 * COST_B


def test_weighted_average_snapshots_the_average_and_leaves_layers_intact(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    switched = client.put(
        "/api/v1/accounting/costing-method",
        headers=headers,
        json={"method": "WEIGHTED_AVERAGE", "reason": "Company values stock at weighted average"},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["inventory_costing"] == "WEIGHTED_AVERAGE"

    product_id = _product(client)
    _receive(client, headers, product_id, 20, COST_A)
    _sell(client, product_id, 15, "wac-sale-15")
    _receive(client, headers, product_id, 20, COST_B)
    costing = _layers(client, headers, product_id)
    assert costing["weighted_average_cost_cents"] == (5 * COST_A + 20 * COST_B) // 25
    assert costing["inventory_value_cents"] == 25 * costing["weighted_average_cost_cents"]
    layers = [(row["remaining_quantity"], row["unit_cost_cents"]) for row in costing["layers"]]
    assert layers == [(5, COST_A), (20, COST_B)]

    second = _sell(client, product_id, 7, "wac-sale-7")
    sold = session.get(SaleItem, uuid.UUID(second["items"][0]["id"]))
    average = (5 * COST_A + 20 * COST_B) // 25
    assert sold is not None and sold.cost_cents == 7 * average
    _receive(client, headers, product_id, 1, 12_000)
    session.expire_all()
    assert session.get(SaleItem, sold.id).cost_cents == 7 * average


def test_costing_method_stays_put_once_sales_are_posted(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    product_id = _product(client)
    _receive(client, headers, product_id, 2, COST_A)
    body = _sell(client, product_id, 1, "lock-sale")
    refused = client.put(
        "/api/v1/accounting/costing-method",
        headers=headers,
        json={"method": "WEIGHTED_AVERAGE", "reason": "Switch without a conversion"},
    )
    assert refused.status_code == 409
    converted = client.put(
        "/api/v1/accounting/costing-method",
        headers=headers,
        json={"method": "WEIGHTED_AVERAGE", "reason": "Approved conversion", "convert": True},
    )
    assert converted.status_code == 200, converted.text
    session.expire_all()
    assert session.get(SaleItem, uuid.UUID(body["items"][0]["id"])).cost_cents == COST_A


def test_cost_layers_stay_inside_the_tenant(session) -> None:
    from app.core.permissions import SUPER_ADMIN_ROLE_ID
    from app.models.batch import PurchaseBatch
    from app.models.store import Store
    from app.models.user import User
    from app.services.rbac_service import ensure_system_roles

    first, second = uuid.uuid4(), uuid.uuid4()

    def tenant(value: uuid.UUID) -> TenantRef:
        return TenantRef(id=str(value), slug="store", name="Store", database_url="sqlite://")

    with use_tenant(tenant(first)):
        ensure_system_roles(session)
        store = Store(code="DT", name="Downtown", currency="USD")
        session.add(store)
        session.flush()
        user = User(
            username="owner",
            email="owner@example.com",
            full_name="Owner",
            role_id=uuid.UUID(SUPER_ADMIN_ROLE_ID),
            store_id=store.id,
        )
        product = Product(
            sku="FRST-1",
            barcode="200000000001",
            name="Beige Frost",
            category="Paint",
            price_cents=PRICE,
            currency="USD",
        )
        session.add_all([user, product])
        session.flush()
        batch = PurchaseBatch(
            batch_number="R-001",
            store_id=store.id,
            import_source="MANUAL",
            currency="USD",
            total_cost_amount=20 * COST_A,
            total_items_count=20,
            created_by_id=user.id,
        )
        session.add(batch)
        session.flush()
        session.add(
            BatchItem(
                batch_id=batch.id,
                product_id=product.id,
                store_id=store.id,
                quantity_imported=20,
                quantity_remaining=20,
                purchase_cost_per_unit=COST_A,
                selling_price_per_unit=PRICE,
            )
        )
        session.commit()
        product_id = product.id

    with use_tenant(tenant(second)):
        assert session.get(Product, product_id) is None
        assert session.scalars(select(BatchItem).where(BatchItem.product_id == product_id)).all() == []
