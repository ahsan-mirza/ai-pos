import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from tests.test_costing import add_batch

from app.models.inventory import InventoryLevel, StockMovement
from app.models.markdown import PriceChange
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.user import User
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, event, line, push, sale, seed


def scenario(client, session) -> dict[str, str]:
    seed(client)
    headers, _ = admin(client)
    add_batch(session, quantity=10, cost=600)
    assert push(client, [event("mgmt-sale", "sale", sale([line(CABLE, 4, 1500)]))]).status_code == 200
    expense = client.post(
        "/api/v1/expenses",
        headers=headers,
        json={
            "store_id": STORE,
            "category": "OFFICE",
            "description": "Printer paper",
            "spent_on": str(date.today()),
            "total_cents": 10_500,
            "paid_from": "CARD",
        },
    )
    assert expense.status_code == 201, expense.text
    written_off = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": CABLE,
            "store_id": STORE,
            "mode": "remove",
            "quantity": 1,
            "reason_code": "STOLEN_SHRINKAGE",
            "note": "Missing from the display at closing",
        },
    )
    assert written_off.status_code == 201, written_off.text
    return headers


def test_pnl_by_branch_and_month(client, session) -> None:
    headers = scenario(client, session)
    period = {"from": "2026-10-01", "to": str(date.today())}
    report = client.get("/api/v1/reports/management/pnl", headers=headers, params=period).json()
    total = report["total"]
    assert (total["net_sales_cents"], total["cogs_cents"], total["gross_profit_cents"]) == (6000, 2400, 3600)
    assert total["gross_margin_bps"] == 6000
    assert total["expenses"] == {"OFFICE": 10_500} and total["shrinkage_cents"] == 600
    assert total["operating_profit_cents"] == 3600 - 10_500 - 600
    assert [row["month"] for row in report["rows"]] == ["2026-10"] and report["by_store"][0]["store_code"] == "DT-01"

    exported = client.get("/api/v1/reports/management/pnl.csv", headers=headers, params=period)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert rows[-1]["branch"] == "ALL" and rows[-1]["operating_profit"] == "-75.00"


def test_valuation_and_aged_stock(client, session) -> None:
    headers = scenario(client, session)
    valuation = client.get("/api/v1/reports/management/valuation", headers=headers).json()
    cable = next(row for row in valuation["rows"] if row["product_id"] == CABLE)
    # 5 units left in the 6.00 batch; the other 490 opening units are estimated at the latest cost, 6.00.
    assert (cable["on_hand"], cable["cost_value_cents"], cable["estimated"]) == (495, 495 * 600, True)
    assert valuation["estimated_units"] == 490 and valuation["by_category"][0]["key"] == "Accessories"

    aged = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    slow = next(row for row in aged["rows"] if row["product_id"] == CABLE)
    assert slow["status"] == "SLOW" and slow["units_sold_90d"] == 4 and slow["cover_days"] > 180
    # 25% a year on 2,970.00 of stock is 61.88 a month; slow stock is marked down 10% from 15.00 (cost is 6.00).
    assert slow["holding_cost_month_cents"] == 6188
    assert (slow["price_cents"], slow["suggested_price_cents"], slow["markdown_pct"]) == (1500, 1350, 10)
    assert "13.50" in slow["suggestion"]
    assert aged["carrying_rate_bps"] == 2500 and aged["holding_cost_month_cents"] >= 6188
    cheaper = client.get(
        "/api/v1/reports/management/aged-stock", headers=headers, params={"carrying_rate_pct": 12}
    ).json()
    assert next(row for row in cheaper["rows"] if row["product_id"] == CABLE)["holding_cost_month_cents"] == 2970
    bad = client.get(
        "/api/v1/reports/management/aged-stock", headers=headers, params={"slow_days": 90, "dead_days": 30}
    )
    assert bad.status_code == 422


def _on_hand(session, quantity: int) -> None:
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(CABLE)))
    assert level is not None
    level.quantity_on_hand = quantity
    session.commit()


def _backdate_receipts(session, days: int) -> None:
    moment = datetime.now(UTC) - timedelta(days=days)
    movements = session.scalars(
        select(StockMovement).where(StockMovement.product_id == uuid.UUID(CABLE), StockMovement.quantity > 0)
    ).all()
    assert movements
    for movement in movements:
        movement.created_at = moment
    session.commit()


def _refund_sale(session, sold: Sale) -> None:
    item = session.scalar(select(SaleItem).where(SaleItem.sale_id == sold.id))
    assert item is not None
    returned = SaleReturn(
        original_sale_id=sold.id,
        store_id=sold.store_id,
        cashier_id=sold.cashier_id,
        currency="USD",
        subtotal_cents=item.line_total_cents,
        tax_refund_cents=0,
        restocking_fee_cents=0,
        total_refund_cents=item.line_total_cents,
        refund_method="cash",
        reason_notes="",
    )
    session.add(returned)
    session.flush()
    session.add(
        ReturnItem(
            return_id=returned.id,
            sale_item_id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price_cents=item.unit_price_cents,
            tax_refund_cents=0,
            restocking_fee_cents=0,
            refund_cents=item.line_total_cents,
            condition_status="unopened_resealable",
            reason_code="changed_mind",
        )
    )
    session.commit()


def test_never_sold_stock_is_aged_from_the_receipt_and_a_refund_does_not_reset_it(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    add_batch(session, quantity=10, cost=600)
    _backdate_receipts(session, 200)
    aged = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    row = next(item for item in aged["rows"] if item["product_id"] == CABLE)
    assert row["status"] == "DEAD" and row["last_sold_at"] is None and row["days_since_sale"] is None
    assert row["days_in_stock"] >= 200 and row["review_required"] is False
    assert row["suggested_price_cents"] == 1100 and row["target_markdown_pct"] == 25
    assert "Dead after 180" in row["reason"]

    assert push(client, [event("dead-sale", "sale", sale([line(CABLE, 4, 1500)]))]).status_code == 200
    sold = session.scalar(select(Sale).where(Sale.client_sale_id.is_not(None)).order_by(Sale.created_at.desc()))
    assert sold is not None
    _refund_sale(session, sold)
    _backdate_receipts(session, 200)
    again = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    row = next(item for item in again["rows"] if item["product_id"] == CABLE)
    assert row["status"] == "DEAD" and row["days_since_sale"] is None and row["units_sold_90d"] <= 0


def test_idle_slow_cover_boundary_zero_stock_and_a_return_that_lengthens_cover(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    add_batch(session, quantity=10, cost=600)
    assert push(client, [event("slow-sale", "sale", sale([line(CABLE, 4, 1500)]))]).status_code == 200
    sold = session.scalar(select(Sale))
    assert sold is not None
    sold.created_at = datetime.now(UTC) - timedelta(days=70)
    session.commit()
    _on_hand(session, 2)
    slow = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    row = next(item for item in slow["rows"] if item["product_id"] == CABLE)
    assert row["status"] == "SLOW" and 69 <= row["days_since_sale"] <= 71
    assert row["cover_days"] is not None and row["cover_days"] <= 180
    assert "No qualifying sale" in row["reason"]

    _on_hand(session, 180)
    sold.created_at = datetime.now(UTC) - timedelta(days=2)
    item = session.scalar(select(SaleItem).where(SaleItem.sale_id == sold.id))
    assert item is not None
    item.quantity = 90
    session.commit()
    boundary = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    assert all(entry["product_id"] != CABLE for entry in boundary["rows"])

    _on_hand(session, 0)
    empty = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    assert all(entry["product_id"] != CABLE for entry in empty["rows"])

    _on_hand(session, 20)
    item.quantity = 20
    sold.created_at = datetime.now(UTC) - timedelta(days=2)
    session.commit()
    _refund_sale(session, sold)
    returned = session.scalar(select(ReturnItem))
    assert returned is not None
    returned.quantity = 15
    session.commit()
    covered = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    row = next(item for item in covered["rows"] if item["product_id"] == CABLE)
    assert row["status"] == "SLOW" and row["units_sold_90d"] == 5 and row["cover_days"] > 180


def test_missing_cost_is_not_a_clearance_price_and_reads_do_not_change_the_price(client, session) -> None:
    seed(client)
    headers, user_id = admin(client)
    _backdate_receipts(session, 200)
    aged = client.get("/api/v1/reports/management/aged-stock", headers=headers).json()
    row = next(item for item in aged["rows"] if item["product_id"] == CABLE)
    assert row["status"] == "DEAD" and row["review_required"] is True and row["suggested_price_cents"] is None
    assert "Cost is missing" in row["suggestion"]
    before = client.get(f"/api/v1/products/{CABLE}", headers=headers).json()["price_cents"]
    assert client.get("/api/v1/reports/management/aged-stock", headers=headers).status_code == 200
    assert client.get(f"/api/v1/products/{CABLE}", headers=headers).json()["price_cents"] == before

    changed = client.patch(f"/api/v1/products/{CABLE}", headers=headers, json={"price_cents": 1600})
    assert changed.status_code == 200, changed.text
    recorded = session.scalar(select(PriceChange).where(PriceChange.product_id == uuid.UUID(CABLE)))
    assert recorded is not None and recorded.user_id == uuid.UUID(user_id) and recorded.reason == "MANUAL"


def test_aged_stock_filters_and_a_pinned_branch_cannot_read_another_store(client, session) -> None:
    headers = scenario(client, session)
    named = client.get(
        "/api/v1/reports/management/aged-stock", headers=headers, params={"q": "cable", "limit": 1}
    ).json()
    assert named["total"] >= 1 and len(named["rows"]) == 1 and named["rows"][0]["sku"] == "ACC-CABLE-USBC"
    missed = client.get("/api/v1/reports/management/aged-stock", headers=headers, params={"q": "zzzz"}).json()
    assert missed["rows"] == []
    dead_only = client.get("/api/v1/reports/management/aged-stock", headers=headers, params={"status": "DEAD"}).json()
    assert all(row["status"] == "DEAD" for row in dead_only["rows"])

    user = session.scalar(select(User).where(User.username == "admin"))
    assert user is not None
    user.store_id = uuid.UUID(STORE)
    session.commit()
    headers, _ = admin(client)
    other = str(uuid.uuid4())
    scoped = client.get("/api/v1/reports/management/aged-stock", headers=headers, params={"store_id": other}).json()
    assert scoped["rows"] and all(row["store_id"] == STORE for row in scoped["rows"])
    denied = client.get("/api/v1/insights/pricing", headers=headers, params={"store_id": other})
    assert denied.status_code == 403


def test_sales_by_staff(client, session) -> None:
    headers = scenario(client, session)
    report = client.get(
        "/api/v1/reports/management/staff", headers=headers, params={"from": "2026-10-01", "to": str(date.today())}
    ).json()
    row = report["rows"][0]
    assert row["user_id"] == CASHIER_ID and (row["sales"], row["units"], row["revenue_cents"]) == (1, 4, 6000)
    assert row["gross_profit_cents"] == 3600 and row["average_basket_cents"] == 6000
