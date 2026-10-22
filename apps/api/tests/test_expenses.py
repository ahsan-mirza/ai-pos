import csv
import io
from collections import defaultdict
from datetime import date

from tests.test_payables import supplier

from test_foundations import set_tax
from wholesale_support import STORE, admin, seed


def expense(**overrides) -> dict:
    body = {
        "store_id": STORE,
        "category": "UTILITIES",
        "description": "DEWA October",
        "payee": "DEWA",
        "payee_trn": "100000000000003",
        "spent_on": str(date.today()),
        "total_cents": 105_000,
        "has_tax_invoice": True,
        "paid_from": "BANK",
    }
    body.update(overrides)
    return body


def test_expenses_feed_vat_and_the_journal(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)

    no_trn = client.post("/api/v1/expenses", headers=headers, json=expense(payee_trn=None))
    assert no_trn.status_code == 422 and "TRN" in no_trn.json()["error"]["message"]
    utilities = client.post("/api/v1/expenses", headers=headers, json=expense())
    assert utilities.status_code == 201, utilities.text
    body = utilities.json()
    assert (body["net_cents"], body["tax_cents"], body["recoverable_tax_cents"]) == (100_000, 5_000, 5_000)
    assert "EXP" in body["number"]
    taxi = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(
            category="TRANSPORT",
            description="Taxi to supplier",
            payee="",
            payee_trn=None,
            total_cents=4_200,
            has_tax_invoice=False,
            paid_from="CARD",
        ),
    ).json()
    assert taxi["tax_cents"] == 200 and taxi["recoverable_tax_cents"] == 0

    landlord = supplier(session, "Al Noor Properties")
    bill = client.post(
        "/api/v1/payables/bills",
        headers=headers,
        json={
            "supplier_id": str(landlord.id),
            "store_id": STORE,
            "number": "R-1",
            "bill_date": str(date.today()),
            "lines": [{"description": "Rent", "quantity": 1, "unit_cost_cents": 200_000}],
        },
    )
    assert bill.status_code == 201, bill.text

    today = str(date.today())
    report = client.get("/api/v1/reports/vat", headers=headers, params={"from": today, "to": today}).json()
    box9 = next(box for box in report["boxes"] if box["key"] == "9")
    assert (box9["amount_cents"], box9["vat_cents"]) == (300_000, 15_000)
    assert report["input_vat_estimated"] is False

    listing = client.get("/api/v1/expenses", headers=headers, params={"from": today, "to": today}).json()
    assert listing["total_cents"] == 109_200 and listing["recoverable_tax_cents"] == 5_000
    assert listing["by_category"][0]["category"] == "UTILITIES"

    exported = client.get("/api/v1/exports/gl.csv", headers=headers, params={"from": today, "to": today})
    rows = [row for row in csv.DictReader(io.StringIO(exported.text)) if row["journal"] == "EXPENSES"]
    balance: dict[str, float] = defaultdict(float)
    for row in rows:
        balance[row["reference"]] += float(row["debit"] or 0) - float(row["credit"] or 0)
    assert rows and all(abs(value) < 0.001 for value in balance.values())
    by_account = defaultdict(float)
    for row in rows:
        by_account[row["account"]] += float(row["debit"] or 0)
    assert by_account["6200"] == 1000.0 and by_account["1300"] == 50.0 and by_account["6400"] == 42.0


def test_petty_cash_float(client) -> None:
    seed(client)
    headers, _ = admin(client)
    short = client.post("/api/v1/expenses", headers=headers, json=expense(paid_from="PETTY_CASH", total_cents=3_000))
    assert short.status_code == 422 and "top it up" in short.json()["error"]["message"]

    topped = client.post(
        "/api/v1/expenses/petty-cash/top-up",
        headers=headers,
        json={"store_id": STORE, "amount_cents": 50_000, "source": "till"},
    )
    assert topped.status_code == 200 and topped.json()["balance_cents"] == 50_000
    tea = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(
            category="OFFICE",
            description="Tea and water",
            payee_trn=None,
            has_tax_invoice=False,
            paid_from="PETTY_CASH",
            total_cents=3_150,
        ),
    ).json()
    float_now = client.get(f"/api/v1/expenses/petty-cash/{STORE}", headers=headers).json()
    assert float_now["balance_cents"] == 46_850 and float_now["entries"][0]["expense_number"] == tea["number"]

    voided = client.post(f"/api/v1/expenses/{tea['id']}/void", headers=headers, json={"reason": "Entered twice"})
    assert voided.json()["status"] == "VOID"
    assert client.get(f"/api/v1/expenses/petty-cash/{STORE}", headers=headers).json()["balance_cents"] == 50_000

    counted = client.post(
        "/api/v1/expenses/petty-cash/count",
        headers=headers,
        json={"store_id": STORE, "counted_cents": 49_500, "note": "Month-end count"},
    ).json()
    assert counted["balance_cents"] == 49_500 and counted["entries"][0]["kind"] == "COUNT"
