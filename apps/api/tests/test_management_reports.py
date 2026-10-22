import csv
import io
import uuid
from datetime import date

from tests.test_costing import add_batch

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


def test_sales_by_staff(client, session) -> None:
    headers = scenario(client, session)
    report = client.get(
        "/api/v1/reports/management/staff", headers=headers, params={"from": "2026-10-01", "to": str(date.today())}
    ).json()
    row = report["rows"][0]
    assert row["user_id"] == CASHIER_ID and (row["sales"], row["units"], row["revenue_cents"]) == (1, 4, 6000)
    assert row["gross_profit_cents"] == 3600 and row["average_basket_cents"] == 6000
