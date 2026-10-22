import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.inventory import InventoryLevel
from app.models.purchasing import PurchaseOrder
from app.models.sale import Sale
from app.services.replenishment_service import daily_rate, days_to_order, order_quantity
from wholesale_support import CABLE, STORE, admin, event, line, push, sale, seed

WAREHOUSE = "00000000-0000-4000-8000-0000000000f1"


def test_daily_rate_weighs_recent_weeks() -> None:
    quiet = [0] * 83 + [7] * 7
    assert round(daily_rate(quiet), 3) == round(0.5 * 7 + 0.3 * 49 / 28 + 0.2 * 49 / 90, 3)


def test_supplier_terms_round_quantities_and_wait_for_order_days() -> None:
    assert order_quantity(7, 1, 1) == 7
    assert order_quantity(7, 20, 1) == 20
    assert order_quantity(25, 1, 12) == 36
    assert order_quantity(7, 50, 12) == 60
    monday = date(2026, 10, 19)
    assert days_to_order([], monday) == 0
    assert days_to_order(["MON"], monday) == 0
    assert days_to_order(["WED", "SUN"], monday) == 2
    assert days_to_order(["SUN"], monday) == 6


def test_run_applies_supplier_terms(client, session) -> None:
    from app.models.batch import Supplier

    seed(client)
    headers, _ = admin(client)
    for day in range(14):
        body = sale([line(CABLE, 3, 1500)])
        assert push(client, [event(f"terms-sale-{day:02d}", "sale", body)]).status_code == 200
        session.get(Sale, uuid.UUID(body["id"])).created_at = datetime.now(UTC) - timedelta(days=day + 1)
    branch = session.query(InventoryLevel).filter_by(product_id=uuid.UUID(CABLE), store_id=uuid.UUID(STORE)).one()
    branch.quantity_on_hand = 5
    session.add(Supplier(name="Volt Trading", code="VOLT", lead_time_days=3))
    session.commit()
    supplier = session.query(Supplier).filter_by(code="VOLT").one()
    tomorrow = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][(date.today().weekday() + 1) % 7]
    saved = client.put(
        f"/api/v1/replenishment/suppliers/{supplier.id}/terms",
        headers=headers,
        json={"lead_time_days": 3, "moq": 200, "pack_size": 12, "order_days": [tomorrow]},
    )
    assert saved.status_code == 200, saved.text
    assert next(row for row in saved.json() if row["code"] == "VOLT")["order_days"] == [tomorrow]
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Volt Trading",
            "destination_store_id": STORE,
            "lines": [{"product_id": CABLE, "quantity_ordered": 1, "unit_cost_cents": 600}],
        },
    )
    assert order.status_code == 201, order.text

    run = client.post("/api/v1/replenishment/runs", headers=headers, json={"store_id": STORE, "review_days": 7})
    assert run.status_code == 201, run.text
    purchase = next(row for row in run.json()["suggestions"] if row["source"] == "PURCHASE")
    assert purchase["suggested_qty"] == 204
    assert "MOQ 200" in purchase["terms_note"] and "cases of 12" in purchase["terms_note"]
    assert "next order day" in purchase["terms_note"]


def test_run_suggests_transfer_from_surplus_then_purchase(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    for day in range(14):
        body = sale([line(CABLE, 3, 1500)])
        assert push(client, [event(f"demand-sale-{day:02d}", "sale", body)]).status_code == 200
        row = session.get(Sale, uuid.UUID(body["id"]))
        row.created_at = datetime.now(UTC) - timedelta(days=day + 1)
    session.commit()

    assert (
        push(
            client,
            [
                event(
                    "warehouse-store",
                    "store",
                    {"id": WAREHOUSE, "code": "WH-9", "name": "Warehouse", "currency": "USD", "is_warehouse": True},
                )
            ],
        ).status_code
        == 200
    )
    session.add(
        InventoryLevel(
            product_id=uuid.UUID(CABLE), store_id=uuid.UUID(WAREHOUSE), quantity_on_hand=20, quantity_reserved=0
        )
    )
    branch = session.query(InventoryLevel).filter_by(product_id=uuid.UUID(CABLE), store_id=uuid.UUID(STORE)).one()
    branch.quantity_on_hand = 5
    session.commit()

    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Volt Trading",
            "destination_store_id": STORE,
            "lines": [{"product_id": CABLE, "quantity_ordered": 1, "unit_cost_cents": 600}],
        },
    )
    assert order.status_code == 201, order.text

    ramadan = client.post(
        "/api/v1/replenishment/events",
        headers=headers,
        json={
            "name": "Ramadan",
            "starts_on": str(date.today()),
            "ends_on": str(date.today() + timedelta(days=30)),
            "uplift_bps": 15000,
        },
    )
    assert ramadan.status_code == 201, ramadan.text

    run = client.post("/api/v1/replenishment/runs", headers=headers, json={"store_id": STORE, "review_days": 7})
    assert run.status_code == 201, run.text
    rows = {row["source"]: row for row in run.json()["suggestions"] if row["product_id"] == CABLE}
    assert rows["TRANSFER"]["from_store_code"] == "WH-9" and rows["TRANSFER"]["suggested_qty"] == 20
    assert rows["PURCHASE"]["suggested_qty"] > 0
    assert "Ramadan" in (rows["PURCHASE"]["seasonal_note"] or "")

    accepted = client.post(
        f"/api/v1/replenishment/runs/{run.json()['id']}/accept",
        headers=headers,
        json={"lines": [{"id": row["id"], "quantity": row["suggested_qty"]} for row in rows.values()]},
    )
    assert accepted.status_code == 200, accepted.text
    result = accepted.json()
    assert len(result["purchase_order_ids"]) == 1 and len(result["transfer_ids"]) == 1
    drafted = session.get(PurchaseOrder, uuid.UUID(result["purchase_order_ids"][0]))
    assert drafted.status == "draft" and drafted.supplier_name == "Volt Trading"
    assert {row["status"] for row in result["run"]["suggestions"] if row["product_id"] == CABLE} == {"ACCEPTED"}
