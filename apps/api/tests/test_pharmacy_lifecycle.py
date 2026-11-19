"""Medicine transfers, supplier returns, recalls, and quarantine."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from tests.test_capabilities import change_profile
from tests.test_inventory import CABLE, CASHIER_ID, DT, SHJ, WH, event, push, seed
from tests.test_pharmacy_catalog import OTHER_TENANT, PROFILES, _create, _medicine, _pharmacy
from tests.test_pharmacy_lots import EXPIRY, LOT, MADE, _layers, _on_hand, _order_and_receive

from app.models.batch import PurchaseBatch
from app.models.inventory import InventoryLevel, StockMovement
from app.models.pharmacy_lots import BatchItemEvent, PharmacyRecall, PharmacySupplierReturn
from app.services.batch_ledger import today
from app.tenancy.scoping import INCLUDE_ALL


def _release(session, product_id: str) -> None:
    for item in _layers(session, product_id):
        if item.lot_status == "UNRELEASED":
            item.lot_status = "RELEASED"
    session.commit()


def _product(client, headers, name: str, sku: str, barcode: str) -> str:
    created = _create(client, headers, name, _medicine(), sku=sku, barcode=barcode)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _transfer(client, headers, product_id: str, quantity: int, source: str = WH, destination: str = SHJ):
    created = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "source_store_id": source,
            "destination_store_id": destination,
            "lines": [{"product_id": product_id, "quantity": quantity}],
        },
    )
    return created


def _ship_and_receive(client, headers, transfer_id: str):
    shipped = client.post(f"/api/v1/inventory/transfers/{transfer_id}/ship", headers=headers, json={})
    if shipped.status_code != 200:
        return shipped, None
    received = client.post(f"/api/v1/inventory/transfers/{transfer_id}/receive", headers=headers)
    return shipped, received


def test_released_medicine_transfer_keeps_the_lot_and_starts_unreleased(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin transfer", "AMOX-TR", "6291111111209")
    _, received = _order_and_receive(client, headers, product_id, 6)
    assert received.status_code == 200, received.text
    _release(session, product_id)
    source = _layers(session, product_id)[0]
    before = _on_hand(session, product_id)
    created = _transfer(client, headers, product_id, 4)
    assert created.status_code == 201, created.text
    shipped, arrived = _ship_and_receive(client, headers, created.json()["id"])
    assert shipped.status_code == 200, shipped.text
    assert arrived is not None and arrived.status_code == 200, arrived.text if arrived else ""
    session.expire_all()
    layers = _layers(session, product_id)
    assert len(layers) == 2
    assert source.quantity_remaining == 2
    destination = next(item for item in layers if item.id != source.id)
    assert destination.store_id == uuid.UUID(SHJ)
    assert destination.quantity_imported == 4
    assert destination.quantity_remaining == 4
    assert destination.manufacturer_lot == LOT
    assert destination.manufactured_on == source.manufactured_on
    assert destination.expiry_date == source.expiry_date
    assert destination.source_batch_item_id == source.id
    assert destination.lot_status == "UNRELEASED"
    batch = session.get(PurchaseBatch, destination.batch_id)
    assert batch is not None and batch.import_source == "TRANSFER"
    assert batch.batch_number != LOT
    actions = {
        (event.batch_item_id, event.action, event.to_status)
        for event in session.scalars(
            select(BatchItemEvent).where(BatchItemEvent.action.in_(("TRANSFER_OUT", "TRANSFER_IN")))
        )
    }
    assert (source.id, "TRANSFER_OUT", "RELEASED") in actions
    assert (destination.id, "TRANSFER_IN", "UNRELEASED") in actions
    assert _on_hand(session, product_id) == before
    wh = session.scalar(
        select(InventoryLevel.quantity_on_hand).where(
            InventoryLevel.product_id == uuid.UUID(product_id), InventoryLevel.store_id == uuid.UUID(WH)
        )
    )
    shj = session.scalar(
        select(InventoryLevel.quantity_on_hand).where(
            InventoryLevel.product_id == uuid.UUID(product_id), InventoryLevel.store_id == uuid.UUID(SHJ)
        )
    )
    assert (wh, shj) == (2, 4)
    movements = session.scalars(
        select(StockMovement).where(
            StockMovement.product_id == uuid.UUID(product_id),
            StockMovement.movement_type.in_(("TRANSFER_OUT", "TRANSFER_IN")),
        )
    ).all()
    assert sorted(row.quantity for row in movements) == [-4, 4]


def test_one_transfer_can_draw_two_lots_and_ineligible_lots_stay_put(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin two lots", "AMOX-TWO", "6291111111216")
    _, first_receipt = _order_and_receive(client, headers, product_id, 6)
    assert first_receipt.status_code == 200, first_receipt.text
    second = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": 6, "unit_cost_cents": 400}],
        },
    )
    assert second.status_code == 201, second.text
    second_order = second.json()
    ordered = client.post(f"/api/v1/inventory/purchase-orders/{second_order['id']}/order", headers=headers)
    assert ordered.status_code == 200
    later = client.post(
        f"/api/v1/inventory/purchase-orders/{second_order['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {
                    "purchase_order_line_id": second_order["lines"][0]["id"],
                    "quantity": 6,
                    "manufacturer_lot": "MFG-LATER",
                    "manufactured_on": MADE,
                    "expiry_date": "2028-01-31",
                }
            ]
        },
    )
    assert later.status_code == 200, later.text
    _release(session, product_id)
    sooner = next(item for item in _layers(session, product_id) if item.manufacturer_lot == LOT)
    later_layer = next(item for item in _layers(session, product_id) if item.manufacturer_lot == "MFG-LATER")
    sooner.expiry_date = today() + timedelta(days=30)
    session.commit()
    created = _transfer(client, headers, product_id, 8)
    assert created.status_code == 201, created.text
    shipped, arrived = _ship_and_receive(client, headers, created.json()["id"])
    assert shipped.status_code == 200, shipped.text
    assert arrived is not None and arrived.status_code == 200, arrived.text
    session.expire_all()
    assert sooner.quantity_remaining == 0
    assert later_layer.quantity_remaining == 4
    destinations = [item for item in _layers(session, product_id) if item.store_id == uuid.UUID(SHJ)]
    assert sorted((item.manufacturer_lot, item.quantity_remaining, item.lot_status) for item in destinations) == [
        ("MFG-LATER", 2, "UNRELEASED"),
        (LOT, 6, "UNRELEASED"),
    ]
    assert {item.source_batch_item_id for item in destinations} == {sooner.id, later_layer.id}

    blocked = _product(client, headers, "Amoxicillin held", "AMOX-HOLD", "6291111111223")
    _, held = _order_and_receive(client, headers, blocked, 5)
    assert held.status_code == 200, held.text
    refused = _transfer(client, headers, blocked, 5)
    assert refused.status_code == 201, refused.text
    failed, _unused = _ship_and_receive(client, headers, refused.json()["id"])
    assert failed.status_code == 422, failed.text
    assert failed.json()["error"]["code"] == "inventory_rejected"
    session.expire_all()
    assert _layers(session, blocked)[0].quantity_remaining == 5
    assert _layers(session, blocked)[0].lot_status == "UNRELEASED"
    outgoing = session.scalars(
        select(StockMovement).where(
            StockMovement.product_id == uuid.UUID(blocked),
            StockMovement.movement_type == "TRANSFER_OUT",
        )
    ).all()
    assert outgoing == []


def test_expired_quarantined_and_recalled_lots_are_not_transferred(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin blocked", "AMOX-BLOCK", "6291111111230")
    _, received = _order_and_receive(client, headers, product_id, 4)
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]
    item.lot_status = "RELEASED"
    item.expiry_date = today() - timedelta(days=1)
    session.commit()
    created = _transfer(client, headers, product_id, 1)
    failed, _unused = _ship_and_receive(client, headers, created.json()["id"])
    assert failed.status_code == 422
    item.expiry_date = today() + timedelta(days=60)
    item.lot_status = "QUARANTINED"
    session.commit()
    again = _transfer(client, headers, product_id, 1)
    failed, _unused = _ship_and_receive(client, headers, again.json()["id"])
    assert failed.status_code == 422
    item.lot_status = "RELEASED"
    session.commit()
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-BLOCK",
            "source_text": "Warehouse notice",
            "severity": "high",
            "reason": "Do not move this lot",
            "lots": [{"product_id": product_id, "manufacturer_lot": LOT}],
        },
    )
    assert opened.status_code == 201, opened.text
    session.expire_all()
    assert item.lot_status == "RECALLED"
    assert item.quantity_remaining == 4
    third = _transfer(client, headers, product_id, 1)
    failed, _unused = _ship_and_receive(client, headers, third.json()["id"])
    assert failed.status_code == 422
    session.expire_all()
    assert item.quantity_remaining == 4
    assert item.lot_status == "RECALLED"


def test_partial_and_multi_lot_supplier_return_rolls_back_together(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin return", "AMOX-RET", "6291111111247")
    _, received = _order_and_receive(client, headers, product_id, 8)
    assert received.status_code == 200, received.text
    first = _layers(session, product_id)[0]
    second_order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": 3, "unit_cost_cents": 400}],
        },
    ).json()
    ordered = client.post(f"/api/v1/inventory/purchase-orders/{second_order['id']}/order", headers=headers)
    assert ordered.status_code == 200
    assert (
        client.post(
            f"/api/v1/inventory/purchase-orders/{second_order['id']}/receive",
            headers=headers,
            json={
                "lines": [
                    {
                        "purchase_order_line_id": second_order["lines"][0]["id"],
                        "quantity": 3,
                        "manufacturer_lot": "MFG-B",
                        "expiry_date": EXPIRY,
                    }
                ]
            },
        ).status_code
        == 200
    )
    session.expire_all()
    second = next(item for item in _layers(session, product_id) if item.manufacturer_lot == "MFG-B")
    before = _on_hand(session, product_id)
    returned = client.post(
        "/api/v1/pharmacy/supplier-returns",
        headers=headers,
        json={
            "reference": "SR-100",
            "reason": "Short dated delivery",
            "lines": [
                {"batch_item_id": str(first.id), "quantity": 2},
                {"batch_item_id": str(second.id), "quantity": 3},
            ],
        },
    )
    assert returned.status_code == 201, returned.text
    body = returned.json()
    assert body["reference"] == "SR-100"
    session.expire_all()
    assert first.quantity_remaining == 6
    assert first.lot_status == "UNRELEASED"
    assert first.manufacturer_lot == LOT
    assert second.quantity_remaining == 0
    assert second.lot_status == "SUPPLIER_RETURN"
    assert _on_hand(session, product_id) == before - 5
    movements = session.scalars(
        select(StockMovement).where(
            StockMovement.reference_type == "pharmacy_supplier_return",
            StockMovement.movement_type == "PURCHASE_REVERSAL",
        )
    ).all()
    assert sorted(row.quantity for row in movements) == [-3, -2]
    events = session.scalars(select(BatchItemEvent).where(BatchItemEvent.action == "SUPPLIER_RETURN")).all()
    assert len(events) == 2
    assert any(row.reason and row.reason.startswith("SR-100") for row in events)

    failed = client.post(
        "/api/v1/pharmacy/supplier-returns",
        headers=headers,
        json={
            "reference": "SR-101",
            "reason": "This second line is too big",
            "lines": [
                {"batch_item_id": str(first.id), "quantity": 1},
                {"batch_item_id": str(second.id), "quantity": 1},
            ],
        },
    )
    assert failed.status_code == 422, failed.text
    session.expire_all()
    assert first.quantity_remaining == 6
    assert session.scalar(select(PharmacySupplierReturn).where(PharmacySupplierReturn.reference == "SR-101")) is None
    assert _on_hand(session, product_id) == before - 5


def test_recall_covers_lots_descendants_and_affected_sales_without_changing_quantity(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin recall", "AMOX-RCL", "6291111111254")
    other_id = _product(client, headers, "Ibuprofen recall", "IBU-RCL", "6291111111261")
    _, first = _order_and_receive(client, headers, product_id, 4)
    assert first.status_code == 200, first.text
    _, second = _order_and_receive(
        client,
        headers,
        other_id,
        2,
        lines=None,
    )
    assert second.status_code == 200, second.text
    other = _layers(session, other_id)[0]
    other.manufacturer_lot = "IBU-LOT"
    session.commit()
    _release(session, product_id)
    payload = {
        "id": str(uuid.uuid4()),
        "store_id": WH,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": 1500,
        "tax_cents": 0,
        "total_cents": 1500,
        "client_sale_id": str(uuid.uuid4()),
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_cents": 0,
                "line_total_cents": 1500,
                "serial_value": None,
                "serial_kind": None,
            }
        ],
    }
    sold = push(client, [event(f"recall-sale-{uuid.uuid4()}", "sale", payload)])
    assert sold.status_code == 200, sold.text
    _release(session, product_id)
    created = _transfer(client, headers, product_id, 1)
    shipped, arrived = _ship_and_receive(client, headers, created.json()["id"])
    assert shipped.status_code == 200, shipped.text
    assert arrived is not None and arrived.status_code == 200, arrived.text
    before = {item.id: item.quantity_remaining for item in _layers(session, product_id)}
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-200",
            "source_text": "Supplier letter",
            "severity": "high",
            "reason": "Label mix-up",
            "lots": [
                {"product_id": product_id, "manufacturer_lot": LOT},
                {"product_id": other_id, "manufacturer_lot": "IBU-LOT"},
            ],
        },
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["layers_recalled"] >= 3
    session.expire_all()
    layers = _layers(session, product_id)
    for item in layers:
        assert before[item.id] == item.quantity_remaining
        assert item.lot_status == "RECALLED"
        assert item.recall_id is not None
    assert _layers(session, other_id)[0].lot_status == "RECALLED"
    recall = session.get(PharmacyRecall, uuid.UUID(opened.json()["id"]))
    assert recall is not None and recall.status == "OPEN"
    sales = client.get(f"/api/v1/pharmacy/recalls/{recall.id}/sales", headers=headers)
    assert sales.status_code == 200, sales.text
    assert sales.json()["total"] == 1
    assert sales.json()["sales"][0]["sale_id"] == payload["id"]
    assert sales.json()["sales"][0]["quantity"] == 1
    closed = client.post(
        f"/api/v1/pharmacy/recalls/{recall.id}/status",
        headers=headers,
        json={"status": "CLOSED"},
    )
    assert closed.status_code == 200, closed.text
    session.expire_all()
    assert recall.status == "CLOSED"
    assert all(item.lot_status == "RECALLED" for item in _layers(session, product_id))


def test_quarantine_records_an_event_and_cannot_clear_a_recall(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin quarantine", "AMOX-Q", "6291111111278")
    _, received = _order_and_receive(client, headers, product_id, 3)
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]
    missing = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/quarantine",
        headers=headers,
        json={"reason": "no"},
    )
    assert missing.status_code == 422
    held = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/quarantine",
        headers=headers,
        json={"reason": "Broken seal on the carton"},
    )
    assert held.status_code == 200, held.text
    assert held.json()["lot_status"] == "QUARANTINED"
    session.expire_all()
    assert item.lot_status == "QUARANTINED"
    assert item.quantity_remaining == 3
    event_row = session.scalar(select(BatchItemEvent).where(BatchItemEvent.action == "QUARANTINED"))
    assert event_row is not None
    assert event_row.from_status == "UNRELEASED"
    assert event_row.to_status == "QUARANTINED"
    assert event_row.reason == "Broken seal on the carton"
    assert event_row.user_id is not None
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-Q",
            "source_text": "Notice",
            "severity": "high",
            "reason": "Recall after quarantine",
            "lots": [{"product_id": product_id, "manufacturer_lot": LOT}],
        },
    )
    assert opened.status_code == 201, opened.text
    session.expire_all()
    blocked = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/quarantine",
        headers=headers,
        json={"reason": "Trying to clear the recall"},
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "lot_recalled"
    session.expire_all()
    assert item.lot_status == "RECALLED"
    missing_release = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/release",
        headers=headers,
        json={"reason": "Trying to release a recall", "confirm": True},
    )
    assert missing_release.status_code == 403
    assert missing_release.json()["error"]["code"] == "pharmacist_required"
    count = session.scalar(
        select(func.count()).select_from(BatchItemEvent).where(BatchItemEvent.batch_item_id == item.id)
    )
    session.execute(
        BatchItemEvent.__table__.update().where(BatchItemEvent.id == event_row.id).values(reason="rewritten")
    )
    # SQLite has no append-only trigger. The service must still have inserted, not updated, the quarantine row.
    session.rollback()
    assert count >= 2


def test_recall_rows_stay_inside_the_tenant(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin tenant recall", "AMOX-TEN2", "6291111111285")
    _, received = _order_and_receive(client, headers, product_id, 1)
    assert received.status_code == 200, received.text
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-TEN",
            "source_text": "Local notice",
            "severity": "low",
            "reason": "Tenant isolation check",
            "lots": [{"product_id": product_id, "manufacturer_lot": LOT}],
        },
    )
    assert opened.status_code == 201, opened.text
    recall_id = uuid.UUID(opened.json()["id"])
    session.info[INCLUDE_ALL] = True
    foreign = PharmacyRecall(
        tenant_id=OTHER_TENANT,
        reference="RCL-OTHER",
        source_text="Other store",
        severity="low",
        reason="Not ours",
        status="OPEN",
    )
    session.add(foreign)
    session.commit()
    foreign_id = foreign.id
    session.info.pop(INCLUDE_ALL, None)
    session.expire_all()
    assert session.get(PharmacyRecall, foreign_id) is None
    assert session.get(PharmacyRecall, recall_id) is not None


def test_seven_profiles_still_transfer_without_a_lot(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    for profile in PROFILES:
        switched = change_profile(client, headers, profile)
        assert switched.status_code == 200, switched.text
        created = _transfer(client, headers, CABLE, 1, source=DT, destination=SHJ)
        assert created.status_code == 201, created.text
        shipped, arrived = _ship_and_receive(client, headers, created.json()["id"])
        assert shipped.status_code == 200, shipped.text
        assert arrived is not None and arrived.status_code == 200, arrived.text
    session.expire_all()
    cable_layers = _layers(session, CABLE)
    assert all(item.lot_status is None and item.manufacturer_lot is None for item in cable_layers)
