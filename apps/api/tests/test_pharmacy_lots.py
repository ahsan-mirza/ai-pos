"""Pharmacy lot identity on goods receipts. Grocery FEFO and sale allocation are not involved."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from tests.test_capabilities import change_profile
from tests.test_inventory import CABLE, WH, admin, event, push, sale, seed
from tests.test_pharmacy_catalog import OTHER_TENANT, PROFILES, _create, _medicine, _pharmacy

from app.models.audit_log import AuditLog
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.inventory import InventoryLevel, StockMovement
from app.models.pharmacy_lots import BatchItemEvent
from app.services.batch_ledger import today
from app.tenancy.scoping import INCLUDE_ALL

LOT = "MFG-LOT-100"
EXPIRY = "2027-06-30"
MADE = "2026-01-15"


def _order_and_receive(client, headers, product_id: str, quantity: int, lines: list[dict] | None = None):
    created = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": quantity, "unit_cost_cents": 400}],
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    placed = client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    assert placed.status_code == 200, placed.text
    payload = lines or [
        {
            "purchase_order_line_id": order["lines"][0]["id"],
            "quantity": quantity,
            "manufacturer_lot": LOT,
            "manufactured_on": MADE,
            "expiry_date": EXPIRY,
        }
    ]
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={"lines": payload},
    )
    return order, received


def _layers(session, product_id: str) -> list[BatchItem]:
    session.expire_all()
    return list(
        session.scalars(
            select(BatchItem)
            .where(BatchItem.product_id == uuid.UUID(product_id))
            .order_by(BatchItem.created_at, BatchItem.id)
        ).all()
    )


def _on_hand(session, product_id: str) -> int:
    session.expire_all()
    return int(
        session.scalar(
            select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).where(
                InventoryLevel.product_id == uuid.UUID(product_id)
            )
        )
        or 0
    )


def test_seven_profiles_receive_without_treating_the_receipt_as_a_lot(client, session) -> None:
    seed(client)
    headers = admin(client)
    for profile in PROFILES:
        switched = change_profile(client, headers, profile)
        assert switched.status_code == 200, switched.text
        created = client.post(
            "/api/v1/inventory/purchase-orders",
            headers=headers,
            json={
                "supplier_name": "Volt Distribution",
                "destination_store_id": WH,
                "lines": [{"product_id": CABLE, "quantity_ordered": 1, "unit_cost_cents": 100}],
            },
        )
        assert created.status_code == 201, created.text
        order = created.json()
        assert order["lines"][0]["lot_controlled"] is False
        assert client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers).status_code == 200
        received = client.post(
            f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
            headers=headers,
            json={"lines": [{"purchase_order_line_id": order["lines"][0]["id"], "quantity": 1}]},
        )
        assert received.status_code == 200, received.text
        assert received.json()["receipts"][-1]["lots"]
        assert received.json()["receipts"][-1]["lots"][-1]["manufacturer_lot"] is None
    for item in _layers(session, CABLE):
        assert item.manufacturer_lot is None
        assert item.lot_status is None
        assert item.quantity_remaining == item.quantity_imported


def test_medicine_receipt_records_the_lot_separately_from_the_receipt_number(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(client, headers, "Amoxicillin 500", _medicine(), sku="AMOX-500", barcode="6291111111117")
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    before = _on_hand(session, product_id)
    order, received = _order_and_receive(client, headers, product_id, 8)
    assert received.status_code == 200, received.text
    body = received.json()
    assert body["lines"][0]["lot_controlled"] is True
    lot = body["receipts"][0]["lots"][0]
    assert lot["manufacturer_lot"] == LOT
    assert lot["lot_status"] == "UNRELEASED"
    assert lot["expiry_date"] == EXPIRY
    assert lot["receipt_batch_number"] != LOT
    assert body["receipts"][0]["number"] != LOT
    layers = _layers(session, product_id)
    assert len(layers) == 1
    item = layers[0]
    assert item.quantity_imported == 8
    assert item.quantity_remaining == 8
    assert item.manufacturer_lot == LOT
    assert item.manufactured_on == date.fromisoformat(MADE)
    assert item.expiry_date == date.fromisoformat(EXPIRY)
    assert item.lot_status == "UNRELEASED"
    batch = session.get(PurchaseBatch, item.batch_id)
    assert batch is not None
    assert batch.batch_number != LOT
    assert batch.goods_receipt_id is not None
    events = session.scalars(select(BatchItemEvent).where(BatchItemEvent.batch_item_id == item.id)).all()
    assert len(events) == 1
    assert events[0].action == "RECEIVED"
    assert events[0].from_status is None
    assert events[0].to_status == "UNRELEASED"
    assert _on_hand(session, product_id) == before + 8
    movements = session.scalars(
        select(StockMovement).where(StockMovement.product_id == uuid.UUID(product_id), StockMovement.movement_type == "PURCHASE_IN")
    ).all()
    assert len(movements) == 1
    assert movements[0].quantity == 8


def test_one_receipt_can_hold_two_lots_and_the_same_lot_can_arrive_again(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(client, headers, "Amoxicillin split", _medicine(), sku="AMOX-SPLIT", barcode="6291111111124")
    product_id = created.json()["id"]
    draft = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": 10, "unit_cost_cents": 400}],
        },
    )
    assert draft.status_code == 201, draft.text
    order = draft.json()
    line_id = order["lines"][0]["id"]
    assert client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers).status_code == 200
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {
                    "purchase_order_line_id": line_id,
                    "quantity": 4,
                    "manufacturer_lot": LOT,
                    "expiry_date": EXPIRY,
                },
                {
                    "purchase_order_line_id": line_id,
                    "quantity": 6,
                    "manufacturer_lot": "MFG-LOT-200",
                    "manufactured_on": MADE,
                    "expiry_date": "2027-12-01",
                },
            ]
        },
    )
    assert received.status_code == 200, received.text
    lots = received.json()["receipts"][0]["lots"]
    assert {lot["manufacturer_lot"] for lot in lots} == {LOT, "MFG-LOT-200"}
    assert [lot["receipt_batch_number"] for lot in lots] != [lot["manufacturer_lot"] for lot in lots]
    layers = _layers(session, product_id)
    assert len(layers) == 2
    assert {item.manufacturer_lot for item in layers} == {LOT, "MFG-LOT-200"}
    assert sum(item.quantity_remaining for item in layers) == 10
    assert _on_hand(session, product_id) == 10
    again, second = _order_and_receive(client, headers, product_id, 2)
    assert second.status_code == 200, second.text
    assert again
    layers = _layers(session, product_id)
    assert len([item for item in layers if item.manufacturer_lot == LOT]) == 2
    assert _on_hand(session, product_id) == 12


def test_medicine_receipt_rejects_missing_or_impossible_lot_data(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(client, headers, "Amoxicillin reject", _medicine(), sku="AMOX-BAD", barcode="6291111111131")
    product_id = created.json()["id"]
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": 5, "unit_cost_cents": 400}],
        },
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    line_id = order["lines"][0]["id"]

    def receive(extra: dict):
        return client.post(
            f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
            headers=headers,
            json={"lines": [{"purchase_order_line_id": line_id, "quantity": 1, **extra}]},
        )

    missing = receive({"expiry_date": EXPIRY})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "lot_required"
    no_expiry = receive({"manufacturer_lot": LOT})
    assert no_expiry.status_code == 422
    assert no_expiry.json()["error"]["code"] == "lot_required"
    backwards = receive({"manufacturer_lot": LOT, "manufactured_on": "2028-01-01", "expiry_date": EXPIRY})
    assert backwards.status_code == 422
    assert backwards.json()["error"]["code"] == "lot_required"
    too_long = receive({"manufacturer_lot": "L" * 65, "expiry_date": EXPIRY})
    assert too_long.status_code == 422
    assert _on_hand(session, product_id) == 0
    assert _layers(session, product_id) == []


def test_a_rejected_second_line_rolls_the_receipt_back(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    first = _create(client, headers, "Amoxicillin keep", _medicine(), sku="AMOX-A", barcode="6291111111148")
    second = _create(client, headers, "Amoxicillin drop", _medicine(), sku="AMOX-B", barcode="6291111111155")
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [
                {"product_id": first_id, "quantity_ordered": 3, "unit_cost_cents": 400},
                {"product_id": second_id, "quantity_ordered": 3, "unit_cost_cents": 400},
            ],
        },
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    lines = {line["product_id"]: line["id"] for line in order["lines"]}
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {
                    "purchase_order_line_id": lines[first_id],
                    "quantity": 3,
                    "manufacturer_lot": LOT,
                    "expiry_date": EXPIRY,
                },
                {"purchase_order_line_id": lines[second_id], "quantity": 3},
            ]
        },
    )
    assert received.status_code == 422
    assert _on_hand(session, first_id) == 0
    assert _on_hand(session, second_id) == 0
    assert _layers(session, first_id) == []
    assert session.scalars(select(BatchItemEvent)).all() == []


def test_non_medicine_receipt_does_not_store_a_lot(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(
        client,
        headers,
        "Cotton wool",
        _medicine(product_kind="SUPPLY", ingredients=[]),
        sku="WOOL-1",
        barcode="6291111111162",
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    order, received = _order_and_receive(
        client,
        headers,
        product_id,
        2,
        lines=None,
    )
    # The helper sends lot fields. A supply ignores them.
    assert order["lines"][0]["lot_controlled"] is False or received.status_code == 200
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]
    assert item.manufacturer_lot is None
    assert item.lot_status is None
    assert item.expiry_date is None
    assert item.quantity_remaining == 2


def test_medicine_adjustment_uses_the_lot_column_and_grocery_adjustment_does_not(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(client, headers, "Amoxicillin adjust", _medicine(), sku="AMOX-ADJ", barcode="6291111111179")
    product_id = created.json()["id"]
    missing = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product_id,
            "store_id": WH,
            "mode": "add",
            "quantity": 2,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Sample tin added to the shelf",
            "unit_cost_cents": 250,
        },
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "lot_required"
    assert _on_hand(session, product_id) == 0
    added = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product_id,
            "store_id": WH,
            "mode": "add",
            "quantity": 2,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Sample tin added to the shelf",
            "unit_cost_cents": 250,
            "manufacturer_lot": LOT,
            "manufactured_on": MADE,
            "expiry_date": EXPIRY,
            "lot_number": "SHOULD-NOT-BE-THE-RECEIPT",
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["row"]["lot_controlled"] is True
    item = _layers(session, product_id)[0]
    batch = session.get(PurchaseBatch, item.batch_id)
    assert batch is not None
    assert batch.batch_number.startswith("ADJ-")
    assert batch.batch_number != LOT
    assert item.manufacturer_lot == LOT
    assert item.lot_status == "UNRELEASED"
    assert item.quantity_remaining == 2
    grocery = change_profile(client, headers, "grocery")
    assert grocery.status_code == 200, grocery.text
    cable = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": CABLE,
            "store_id": WH,
            "mode": "add",
            "quantity": 1,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Grocery sample kept on the old batch number",
            "unit_cost_cents": 100,
            "lot_number": "GROCERY-BATCH",
            "expiry_date": str(today() + timedelta(days=10)),
        },
    )
    assert cable.status_code == 201, cable.text
    grocery_layers = [item for item in _layers(session, CABLE) if item.manufacturer_lot == "GROCERY-BATCH"]
    assert grocery_layers == []
    numbered = session.scalar(select(PurchaseBatch).where(PurchaseBatch.batch_number == "GROCERY-BATCH"))
    assert numbered is not None
    grocery_item = session.scalar(select(BatchItem).where(BatchItem.batch_id == numbered.id))
    assert grocery_item is not None
    assert grocery_item.manufacturer_lot is None
    assert grocery_item.lot_status is None
    assert grocery_item.expiry_date == today() + timedelta(days=10)


def _grocery_layer(client, headers, lot: str, days: int | None, quantity: int = 2) -> uuid.UUID:
    body = {
        "adjustment_id": str(uuid.uuid4()),
        "product_id": CABLE,
        "store_id": WH,
        "mode": "add",
        "quantity": quantity,
        "reason_code": "SUPPLIER_SAMPLE_IN",
        "note": "Grocery dated stock for the FEFO check",
        "unit_cost_cents": 100,
        "lot_number": lot,
    }
    if days is not None:
        body["expiry_date"] = str(today() + timedelta(days=days))
    added = client.post("/api/v1/inventory/adjust", headers=headers, json=body)
    assert added.status_code == 201, added.text
    return uuid.UUID(added.json()["movements"][0]["id"])


def test_grocery_fefo_still_sells_expired_stock_last(client, session) -> None:
    seed(client)
    headers = admin(client)
    assert change_profile(client, headers, "grocery").status_code == 200
    _grocery_layer(client, headers, "GROC-EXPIRED", -3)
    _grocery_layer(client, headers, "GROC-LATER", 60)
    _grocery_layer(client, headers, "GROC-SOONER", 10)
    _grocery_layer(client, headers, "GROC-UNDATED", None)
    session.expire_all()
    by_number = {
        batch.batch_number: item
        for batch, item in session.execute(
            select(PurchaseBatch, BatchItem).join(BatchItem, BatchItem.batch_id == PurchaseBatch.id)
        ).all()
        if batch.batch_number.startswith("GROC-")
    }
    assert set(by_number) == {"GROC-EXPIRED", "GROC-LATER", "GROC-SOONER", "GROC-UNDATED"}
    assert all(item.manufacturer_lot is None and item.lot_status is None for item in by_number.values())

    def sell(quantity: int) -> dict[uuid.UUID, int]:
        payload = sale(WH, CABLE, quantity)
        response = push(client, [event(f"grocery-fefo-{uuid.uuid4()}", "sale", payload)])
        assert response.status_code == 200, response.text
        session.expire_all()
        rows = session.scalars(
            select(BatchAllocation).where(BatchAllocation.sale_item_id == uuid.UUID(payload["items"][0]["id"]))
        ).all()
        return {row.batch_item_id: row.quantity for row in rows}

    first = sell(3)
    assert first == {by_number["GROC-SOONER"].id: 2, by_number["GROC-LATER"].id: 1}
    assert session.scalar(select(AuditLog).where(AuditLog.action == "inventory.expired_sold")) is None
    second = sell(4)
    assert second == {
        by_number["GROC-LATER"].id: 1,
        by_number["GROC-UNDATED"].id: 2,
        by_number["GROC-EXPIRED"].id: 1,
    }
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "inventory.expired_sold"))
    assert entry is not None and entry.action_type == "EXPIRED_STOCK_SOLD"
    assert entry.details["quantity"] == 1


def test_grocery_fefo_sells_the_earlier_layer_before_the_later_one(client, session) -> None:
    seed(client)
    headers = admin(client)
    assert change_profile(client, headers, "grocery").status_code == 200
    _grocery_layer(client, headers, "GROC-EARLIER", 12, quantity=3)
    _grocery_layer(client, headers, "GROC-LATER-SPLIT", 90, quantity=5)
    session.expire_all()
    by_number = {
        batch.batch_number: item
        for batch, item in session.execute(
            select(PurchaseBatch, BatchItem).join(BatchItem, BatchItem.batch_id == PurchaseBatch.id)
        ).all()
        if batch.batch_number in {"GROC-EARLIER", "GROC-LATER-SPLIT"}
    }
    payload = sale(WH, CABLE, 4)
    response = push(client, [event(f"grocery-split-{uuid.uuid4()}", "sale", payload)])
    assert response.status_code == 200, response.text
    session.expire_all()
    drawn = {
        row.batch_item_id: row.quantity
        for row in session.scalars(
            select(BatchAllocation).where(BatchAllocation.sale_item_id == uuid.UUID(payload["items"][0]["id"]))
        ).all()
    }
    earlier = by_number["GROC-EARLIER"]
    later = by_number["GROC-LATER-SPLIT"]
    assert drawn[earlier.id] == 3
    assert drawn[later.id] == 1
    assert session.get(BatchItem, earlier.id).quantity_remaining == 0
    assert session.get(BatchItem, later.id).quantity_remaining == 4


def test_lot_events_stay_inside_the_tenant(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    created = _create(client, headers, "Amoxicillin tenant", _medicine(), sku="AMOX-TEN", barcode="6291111111186")
    product_id = created.json()["id"]
    _, received = _order_and_receive(client, headers, product_id, 1)
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]
    session.info[INCLUDE_ALL] = True
    foreign = BatchItemEvent(
        batch_item_id=item.id,
        tenant_id=OTHER_TENANT,
        action="RECEIVED",
        to_status="UNRELEASED",
    )
    session.add(foreign)
    session.commit()
    foreign_id = foreign.id
    session.info.pop(INCLUDE_ALL, None)
    session.expire_all()
    assert session.get(BatchItemEvent, foreign_id) is None
    visible = session.scalars(select(BatchItemEvent).where(BatchItemEvent.batch_item_id == item.id)).all()
    assert len(visible) == 1
    assert visible[0].tenant_id != OTHER_TENANT
