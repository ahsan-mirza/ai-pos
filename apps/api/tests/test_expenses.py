import base64
import csv
import io
from collections import defaultdict
from datetime import date

from PIL import Image

from tests.test_payables import supplier

from test_foundations import set_tax
from wholesale_support import STORE, admin, device, seed


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


def test_register_pin_can_read_expenses(client) -> None:
    """A till token keeps the expenses permission. Cashiers stay closed."""
    seed(client)
    today = str(date.today())
    pin = client.post("/api/v1/auth/login-pin", json={"username": "admin", "pin": "2468"}, headers=device())
    assert pin.status_code == 200, pin.text
    headers = {"Authorization": f"Bearer {pin.json()['access_token']}"}
    listing = client.get("/api/v1/expenses", headers=headers, params={"from": today, "to": today})
    assert listing.status_code == 200, listing.text
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    denied = client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {cashier.json()['access_token']}"},
        params={"from": today, "to": today},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["message"] == "You do not have permission for this action."


def test_expense_records_the_supplier_without_opening_a_bill(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    row = supplier(session, "DEWA")
    row.trn = "100000000000003"
    row.phone = "0501234567"
    session.commit()
    created = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(supplier_id=str(row.id), payee="", payee_trn=None),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["supplier_id"] == str(row.id)
    assert body["supplier_name"] == "DEWA"
    assert body["payee"] == "DEWA"
    assert body["payee_trn"] == "100000000000003"
    bills = client.get("/api/v1/payables/bills", headers=headers)
    assert bills.status_code == 200 and bills.json() == []
    found = client.get("/api/v1/expenses/suppliers", headers=headers, params={"q": "0501234567"})
    assert found.status_code == 200 and found.json()[0]["name"] == "DEWA"
    missing = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(supplier_id="00000000-0000-4000-8000-000000009999"),
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "supplier_invalid"


def _png() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_custom_category_and_compressed_bill(client) -> None:
    seed(client)
    headers, _ = admin(client)
    created = client.post("/api/v1/expenses/categories", headers=headers, json={"name": "  Fuel and gas  "})
    assert created.status_code == 201, created.text
    category = created.json()
    again = client.post("/api/v1/expenses/categories", headers=headers, json={"name": "Fuel and gas"})
    assert again.status_code == 201 and again.json()["id"] == category["id"]
    blank = client.post("/api/v1/expenses/categories", headers=headers, json={"name": " "})
    assert blank.status_code == 422
    recorded = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(
            category_id=category["id"],
            category=None,
            bill={"file_name": "bill.png", "content_type": "image/png", "data_base64": _png()},
        ),
    )
    assert recorded.status_code == 201, recorded.text
    body = recorded.json()
    assert body["category_name"] == "Fuel and gas" and body["has_bill"] is True
    image = client.get(f"/api/v1/expenses/{body['id']}/bill", headers=headers)
    assert image.status_code == 200 and image.json()["content_type"] == "image/webp"
    assert image.json()["size_bytes"] > 0
    rejected = client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense(bill={"file_name": "note.txt", "content_type": "text/plain", "data_base64": base64.b64encode(b"hello").decode()}),
    )
    assert rejected.status_code == 415
    stopped = client.post(f"/api/v1/expenses/categories/{category['id']}/deactivate", headers=headers)
    assert stopped.status_code == 200 and stopped.json()["is_active"] is False
    offered = client.get("/api/v1/expenses/categories", headers=headers).json()
    assert category["id"] not in {row["id"] for row in offered}
    blocked = client.post("/api/v1/expenses", headers=headers, json=expense(category_id=category["id"], category=None))
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "category_inactive"
    listed = client.get("/api/v1/expenses", headers=headers, params={"from": str(date.today()), "to": str(date.today())}).json()
    kept = next(row for row in listed["items"] if row["id"] == body["id"])
    assert kept["category_name"] == "Fuel and gas"


def test_offline_client_key_posts_once(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    first = client.post("/api/v1/expenses", headers=headers, json=expense(client_key="offline-key-1", paid_from="BANK"))
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/expenses", headers=headers, json=expense(client_key="offline-key-1", description="Different text", paid_from="BANK"))
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["description"] == first.json()["description"]
    today = str(date.today())
    listing = client.get("/api/v1/expenses", headers=headers, params={"from": today, "to": today}).json()
    assert sum(1 for row in listing["items"] if row["id"] == first.json()["id"]) == 1
