"""Strict medicine sale allocation. Grocery FEFO is covered in test_pharmacy_lots."""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select
from tests.test_capabilities import change_profile
from tests.test_inventory import CABLE, CASHIER_ID, DT, SHJ, WH, event, push, sale, seed, stock
from tests.test_pharmacy_catalog import OTHER_TENANT, PROFILES, _create, _medicine, _pharmacy
from tests.test_pharmacy_lots import LOT, MADE, _layers, _on_hand, _order_and_receive

from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.inventory import StockMovement
from app.models.sale import Sale
from app.services.batch_ledger import today
from app.tenancy.scoping import INCLUDE_ALL

UNIT = 1500


def _product(client, headers, name: str, sku: str) -> str:
    barcode = f"629{abs(hash(sku)) % 10**10:010d}"[:13]
    created = _create(client, headers, name, _medicine(), sku=sku, barcode=barcode)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _release(session, product_id: str) -> None:
    for item in _layers(session, product_id):
        if item.lot_status == "UNRELEASED":
            item.lot_status = "RELEASED"
    session.commit()


def _priced(store_id: str, lines: list[tuple[str, int]]) -> dict:
    items = []
    total = 0
    for product_id, quantity in lines:
        line_total = UNIT * quantity
        total += line_total
        items.append(
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": quantity,
                "unit_price_cents": UNIT,
                "tax_cents": 0,
                "line_total_cents": line_total,
            }
        )
    return {
        "id": str(uuid.uuid4()),
        "store_id": store_id,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": total,
        "tax_cents": 0,
        "total_cents": total,
        "client_sale_id": str(uuid.uuid4()),
        "items": items,
    }


def _sell(client, store_id: str, lines: list[tuple[str, int]]):
    payload = _priced(store_id, lines)
    response = push(client, [event(str(uuid.uuid4()), "sale", payload)])
    return response, payload


def _reason(response) -> str | None:
    details = response.json().get("error", {}).get("details") or {}
    return details.get("reason")


def _allocations(session, sale_id: str) -> list[BatchAllocation]:
    session.expire_all()
    return list(
        session.scalars(
            select(BatchAllocation)
            .join(StockMovement, StockMovement.id == BatchAllocation.stock_movement_id)
            .where(StockMovement.reference_type == "sale", StockMovement.reference_id == uuid.UUID(sale_id))
            .order_by(BatchAllocation.created_at, BatchAllocation.id)
        ).all()
    )


def test_released_in_date_lot_sells_and_records_the_allocation(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin sell", "AMOX-SELL")
    _, received = _order_and_receive(client, headers, product_id, 4)
    assert received.status_code == 200, received.text
    assert _on_hand(session, product_id) == 4
    blocked, _ = _sell(client, WH, [(product_id, 1)])
    assert blocked.status_code == 422, blocked.text
    assert _reason(blocked) == "lot_unreleased"
    assert "not released" in blocked.json()["error"]["message"]
    assert _on_hand(session, product_id) == 4
    assert session.scalar(select(func.count()).select_from(Sale)) == 0

    _release(session, product_id)
    summary = stock(client, headers, store_id=WH)
    row = next(item for item in summary["rows"] if item["product_id"] == product_id)
    assert row["lot_controlled"] is True
    assert row["eligible_quantity"] == 4
    assert row["quantity_on_hand"] == 4

    response, payload = _sell(client, WH, [(product_id, 2)])
    assert response.status_code == 200, response.text
    assert _on_hand(session, product_id) == 2
    allocations = _allocations(session, payload["id"])
    assert len(allocations) == 1
    assert allocations[0].quantity == 2
    assert allocations[0].sale_item_id is not None
    assert allocations[0].movement_type == "SALE_OUT"
    layer = session.get(BatchItem, allocations[0].batch_item_id)
    assert layer is not None
    assert layer.lot_status == "RELEASED"
    assert layer.quantity_remaining == 2

    replay = push(client, [event(str(uuid.uuid4()), "sale", payload)])
    assert replay.status_code == 422
    assert "already exists" in replay.json()["error"]["message"].lower()
    assert _on_hand(session, product_id) == 2

    first = event("medicine-sale-once", "sale", _priced(WH, [(product_id, 1)]))
    assert push(client, [first]).status_code == 200
    again = push(client, [first])
    assert again.status_code == 200, again.text
    assert again.json()["results"] == [{"idempotency_key": "medicine-sale-once", "status": "duplicate"}]
    assert _on_hand(session, product_id) == 1


def test_ineligible_lots_cannot_fill_a_sale(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)

    expired = _product(client, headers, "Expired amoxicillin", "AMOX-EXP")
    _, received = _order_and_receive(client, headers, expired, 3)
    assert received.status_code == 200, received.text
    item = _layers(session, expired)[0]
    item.expiry_date = today() - timedelta(days=1)
    item.lot_status = "RELEASED"
    session.commit()
    response, _ = _sell(client, WH, [(expired, 1)])
    assert response.status_code == 422, response.text
    assert _reason(response) == "lot_expired"
    assert _on_hand(session, expired) == 3

    blank = _product(client, headers, "No expiry", "AMOX-NULL-EXP")
    _, received = _order_and_receive(client, headers, blank, 2)
    assert received.status_code == 200, received.text
    item = _layers(session, blank)[0]
    item.expiry_date = None
    item.lot_status = "RELEASED"
    session.commit()
    response, _ = _sell(client, WH, [(blank, 1)])
    assert _reason(response) == "lot_ineligible"
    assert _on_hand(session, blank) == 2

    naked = _product(client, headers, "Null status", "AMOX-NULL-STATUS")
    _, received = _order_and_receive(client, headers, naked, 2)
    assert received.status_code == 200, received.text
    item = _layers(session, naked)[0]
    item.lot_status = None
    session.commit()
    response, _ = _sell(client, WH, [(naked, 1)])
    assert _reason(response) == "lot_ineligible"
    assert _on_hand(session, naked) == 2

    empty = _product(client, headers, "Zero remaining", "AMOX-ZERO")
    _, received = _order_and_receive(client, headers, empty, 2)
    assert received.status_code == 200, received.text
    item = _layers(session, empty)[0]
    item.quantity_remaining = 0
    item.lot_status = "RELEASED"
    session.commit()
    response, _ = _sell(client, WH, [(empty, 1)])
    assert response.status_code == 422
    assert _reason(response) == "insufficient_released_stock"
    assert _on_hand(session, empty) == 2

    held = _product(client, headers, "Quarantine", "AMOX-QUAR")
    _, received = _order_and_receive(client, headers, held, 2)
    assert received.status_code == 200, received.text
    _release(session, held)
    layer = _layers(session, held)[0]
    quarantined = client.post(
        f"/api/v1/pharmacy/lots/{layer.id}/quarantine",
        headers=headers,
        json={"reason": "Quality hold"},
    )
    assert quarantined.status_code == 200, quarantined.text
    response, _ = _sell(client, WH, [(held, 1)])
    assert _reason(response) == "lot_quarantined"
    assert _on_hand(session, held) == 2

    recalled = _product(client, headers, "Recalled", "AMOX-RCL")
    _, received = _order_and_receive(client, headers, recalled, 2)
    assert received.status_code == 200, received.text
    _release(session, recalled)
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-SALE",
            "source_text": "Supplier letter",
            "severity": "high",
            "reason": "Do not sell this lot",
            "lots": [{"product_id": recalled, "manufacturer_lot": LOT}],
        },
    )
    assert opened.status_code == 201, opened.text
    response, _ = _sell(client, WH, [(recalled, 1)])
    assert _reason(response) == "lot_recalled"
    assert _on_hand(session, recalled) == 2

    damaged = _product(client, headers, "Damaged", "AMOX-DMG")
    _, received = _order_and_receive(client, headers, damaged, 2)
    assert received.status_code == 200, received.text
    item = _layers(session, damaged)[0]
    item.lot_status = "DAMAGED"
    session.commit()
    response, _ = _sell(client, WH, [(damaged, 1)])
    assert _reason(response) == "lot_damaged"
    assert _on_hand(session, damaged) == 2

    returned = _product(client, headers, "Supplier returned", "AMOX-RET")
    _, received = _order_and_receive(client, headers, returned, 2)
    assert received.status_code == 200, received.text
    item = _layers(session, returned)[0]
    item.lot_status = "SUPPLIER_RETURN"
    session.commit()
    response, _ = _sell(client, WH, [(returned, 1)])
    assert _reason(response) == "lot_supplier_return"
    assert _on_hand(session, returned) == 2


def test_fefo_spans_lots_and_refuses_ineligible_cover(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Multi lot", "AMOX-FEFO")
    soon = "2027-03-01"
    later = "2027-12-01"
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Example Pharma",
            "destination_store_id": WH,
            "lines": [{"product_id": product_id, "quantity_ordered": 7, "unit_cost_cents": 400}],
        },
    )
    assert order.status_code == 201, order.text
    body = order.json()
    line_id = body["lines"][0]["id"]
    placed = client.post(f"/api/v1/inventory/purchase-orders/{body['id']}/order", headers=headers)
    assert placed.status_code == 200, placed.text
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{body['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {
                    "purchase_order_line_id": line_id,
                    "quantity": 2,
                    "manufacturer_lot": "LOT-LATER",
                    "manufactured_on": MADE,
                    "expiry_date": later,
                },
                {
                    "purchase_order_line_id": line_id,
                    "quantity": 3,
                    "manufacturer_lot": "LOT-SOON",
                    "manufactured_on": MADE,
                    "expiry_date": soon,
                },
                {
                    "purchase_order_line_id": line_id,
                    "quantity": 2,
                    "manufacturer_lot": "LOT-SAME",
                    "manufactured_on": MADE,
                    "expiry_date": soon,
                },
            ]
        },
    )
    assert received.status_code == 200, received.text
    _release(session, product_id)
    layers = _layers(session, product_id)
    soonest = [item for item in layers if item.manufacturer_lot == "LOT-SOON"][0]
    same = [item for item in layers if item.manufacturer_lot == "LOT-SAME"][0]
    late = [item for item in layers if item.manufacturer_lot == "LOT-LATER"][0]
    # Same expiry as the soon lot, but received first, so it is drawn first among that date.
    same.created_at = soonest.created_at - timedelta(seconds=5)
    session.commit()

    response, payload = _sell(client, WH, [(product_id, 1)])
    assert response.status_code == 200, response.text
    drawn = _allocations(session, payload["id"])
    assert [row.batch_item_id for row in drawn] == [same.id]
    assert drawn[0].quantity == 1

    response, payload = _sell(client, WH, [(product_id, 5)])
    assert response.status_code == 200, response.text
    drawn = _allocations(session, payload["id"])
    quantities = {row.batch_item_id: row.quantity for row in drawn}
    # same has 1 left, soon has 3, later has 2. Five units take 1 + 3 + 1.
    assert quantities[same.id] == 1
    assert quantities[soonest.id] == 3
    assert quantities[late.id] == 1
    assert sum(quantities.values()) == 5
    session.expire_all()
    assert late.quantity_remaining == 1

    # Unreleased stock must not cover the remaining released unit.
    extra = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product_id,
            "store_id": WH,
            "mode": "add",
            "quantity": 4,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Unreleased sample",
            "unit_cost_cents": 250,
            "manufacturer_lot": "LOT-NEW",
            "manufactured_on": MADE,
            "expiry_date": "2028-01-01",
        },
    )
    assert extra.status_code == 201, extra.text
    response, _ = _sell(client, WH, [(product_id, 2)])
    assert response.status_code == 422, response.text
    assert _reason(response) == "insufficient_released_stock"
    session.expire_all()
    assert late.quantity_remaining == 1
    assert late.lot_status == "RELEASED"
    fresh = [item for item in _layers(session, product_id) if item.manufacturer_lot == "LOT-NEW"][0]
    assert fresh.lot_status == "UNRELEASED"
    assert fresh.quantity_remaining == 4


def test_a_failed_second_line_rolls_the_whole_sale_back(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    first = _product(client, headers, "First medicine", "AMOX-ONE")
    second = _product(client, headers, "Second medicine", "AMOX-TWO")
    assert _order_and_receive(client, headers, first, 3)[1].status_code == 200
    assert _order_and_receive(client, headers, second, 3)[1].status_code == 200
    _release(session, first)
    response, payload = _sell(client, WH, [(first, 2), (second, 1)])
    assert response.status_code == 422, response.text
    assert _reason(response) == "lot_unreleased"
    assert session.get(Sale, uuid.UUID(payload["id"])) is None
    assert _on_hand(session, first) == 3
    assert _on_hand(session, second) == 3
    assert _allocations(session, payload["id"]) == []


def test_store_and_tenant_layers_are_not_allocated(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Branch medicine", "AMOX-BRANCH")
    assert _order_and_receive(client, headers, product_id, 3)[1].status_code == 200
    _release(session, product_id)
    other_store = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product_id,
            "store_id": SHJ,
            "mode": "add",
            "quantity": 5,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Other branch",
            "unit_cost_cents": 250,
            "manufacturer_lot": "LOT-SHJ",
            "manufactured_on": MADE,
            "expiry_date": "2027-01-01",
        },
    )
    assert other_store.status_code == 201, other_store.text
    shj = [item for item in _layers(session, product_id) if item.store_id == uuid.UUID(SHJ)][0]
    shj.lot_status = "RELEASED"
    session.commit()
    local = [item for item in _layers(session, product_id) if item.store_id == uuid.UUID(WH)][0]

    session.info[INCLUDE_ALL] = True
    foreign_batch = PurchaseBatch(
        tenant_id=OTHER_TENANT,
        batch_number="OTHER-LOT",
        store_id=local.store_id,
        import_source="MANUAL",
        currency="USD",
        status="ACTIVE",
        total_cost_amount=100,
        total_items_count=9,
        created_by_id=uuid.UUID(CASHIER_ID),
    )
    session.add(foreign_batch)
    session.flush()
    foreign = BatchItem(
        tenant_id=OTHER_TENANT,
        batch_id=foreign_batch.id,
        product_id=local.product_id,
        store_id=local.store_id,
        quantity_imported=9,
        quantity_remaining=9,
        purchase_cost_per_unit=100,
        selling_price_per_unit=UNIT,
        expiry_date=today(),
        manufacturer_lot="FOREIGN",
        lot_status="RELEASED",
        imported_serials=[],
    )
    session.add(foreign)
    session.commit()
    session.info.pop(INCLUDE_ALL, None)

    response, payload = _sell(client, WH, [(product_id, 1)])
    assert response.status_code == 200, response.text
    drawn = _allocations(session, payload["id"])
    assert [row.batch_item_id for row in drawn] == [local.id]
    session.expire_all()
    assert shj.quantity_remaining == 5
    session.info[INCLUDE_ALL] = True
    assert session.get(BatchItem, foreign.id).quantity_remaining == 9
    session.info.pop(INCLUDE_ALL, None)

    wrong_store, _ = _sell(client, DT, [(product_id, 1)])
    assert wrong_store.status_code == 422
    assert _on_hand(session, product_id) == 7


def test_seven_profiles_still_sell_without_pharmacy_rules(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    headers = {"Authorization": headers["Authorization"]}
    # Switch back through each existing profile. Cable has no lot status and must keep selling.
    for profile in PROFILES:
        switched = change_profile(client, headers, profile)
        assert switched.status_code == 200, switched.text
        response = push(client, [event(str(uuid.uuid4()), "sale", sale(DT, CABLE, 1))])
        assert response.status_code == 200, (profile, response.text)
    layers = list(session.scalars(select(BatchItem).where(BatchItem.product_id == uuid.UUID(CABLE))).all())
    assert all(item.lot_status is None and item.manufacturer_lot is None for item in layers)


def test_customer_return_holds_the_medicine_layer(client, session) -> None:
    from datetime import UTC, datetime

    from tests.test_inventory import ADMIN_PASSWORD, device

    from app.services.returns_service import prorated_tax, restocking_fee

    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers, "Amoxicillin return", "AMOX-RET")
    _, received = _order_and_receive(client, headers, product_id, 2)
    assert received.status_code == 200, received.text
    _release(session, product_id)
    sold, payload = _sell(client, WH, [(product_id, 1)])
    assert sold.status_code == 200, sold.text
    looked = client.get(f"/api/v1/returns/receipts/{payload['id']}", headers=device())
    assert looked.status_code == 200, looked.text
    body = looked.json()
    line = body["items"][0]
    condition = "unopened_resealable"
    fee_bps = next(row["fee_bps"] for row in body["policy"]["conditions"] if row["key"] == condition)
    tax = prorated_tax(line["tax_cents"], line["quantity"], 1, line["returned_quantity"], line["refunded_tax_cents"])
    fee = restocking_fee(line["unit_price_cents"], 1, fee_bps)
    total = line["unit_price_cents"] + tax - fee
    approver = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert approver.status_code == 200, approver.text
    approver_id = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {approver.json()['access_token']}"}
    ).json()["id"]
    returned = push(
        client,
        [
            event(
                str(uuid.uuid4()),
                "sale_return",
                {
                    "id": str(uuid.uuid4()),
                    "original_sale_id": body["sale_id"],
                    "store_id": WH,
                    "cashier_id": CASHIER_ID,
                    "currency": "USD",
                    "processed_at": datetime.now(UTC).isoformat(),
                    "subtotal_cents": line["unit_price_cents"],
                    "tax_refund_cents": tax,
                    "restocking_fee_cents": fee,
                    "total_refund_cents": total,
                    "reason_notes": "Customer changed their mind.",
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "sale_item_id": line["sale_item_id"],
                            "product_id": line["product_id"],
                            "quantity": 1,
                            "unit_price_cents": line["unit_price_cents"],
                            "tax_refund_cents": tax,
                            "restocking_fee_cents": fee,
                            "refund_cents": total,
                            "condition_status": condition,
                            "reason_code": "changed_mind",
                        }
                    ],
                    "tenders": [{"method": "cash", "amount_cents": total}],
                    "override": {
                        "approved_by_id": approver_id,
                        "reasons": ["no_refund_permission"],
                        "note": "Checked box.",
                    },
                },
            )
        ],
    )
    assert returned.status_code == 200, returned.text
    session.expire_all()
    layer = session.scalars(select(BatchItem).where(BatchItem.product_id == uuid.UUID(product_id))).one()
    assert layer.lot_status == "QUARANTINED"
    assert layer.quantity_remaining == 2
    blocked, _ = _sell(client, WH, [(product_id, 1)])
    assert blocked.status_code == 422
    assert _reason(blocked) == "lot_quarantined"


def test_release_requires_an_appointed_pharmacist(client) -> None:
    seed(client)
    headers = _pharmacy(client)
    incomplete = client.post(f"/api/v1/pharmacy/lots/{uuid.uuid4()}/release", headers=headers, json={})
    assert incomplete.status_code == 422
    denied = client.post(
        f"/api/v1/pharmacy/lots/{uuid.uuid4()}/release",
        headers=headers,
        json={"reason": "Ready for sale", "confirm": True},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "pharmacist_required"


def test_sale_reason_precedence_is_stable() -> None:
    """Documents the reason order. It does not change which stock can be sold."""
    from app.services.pharmacy_lots import explain_shortage

    def layer(**kwargs: object) -> SimpleNamespace:
        values: dict[str, object] = {
            "lot_status": "RELEASED",
            "quantity_remaining": 1,
            "expiry_date": date(2099, 1, 1),
            "created_at": date(2099, 1, 1),
            "id": "layer",
        }
        values.update(kwargs)
        return SimpleNamespace(**values)

    unreleased = explain_shortage([layer(lot_status="UNRELEASED", expiry_date=date(2020, 1, 15))], "Med")
    assert unreleased[0] == "lot_unreleased"
    assert explain_shortage([layer(expiry_date=date(2020, 1, 15))], "Med")[0] == "lot_expired"
    assert explain_shortage([layer(lot_status="DAMAGED")], "Med")[0] == "lot_damaged"
    supplier = explain_shortage([layer(lot_status="SUPPLIER_RETURN", quantity_remaining=2)], "Med")
    assert supplier[0] == "lot_supplier_return"
    empty_supplier = explain_shortage([layer(lot_status="SUPPLIER_RETURN", quantity_remaining=0)], "Med")
    assert empty_supplier[0] == "insufficient_released_stock"
    assert explain_shortage([layer(), layer()], "Med")[0] == "insufficient_released_stock"
