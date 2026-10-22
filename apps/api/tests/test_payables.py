import csv
import io
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from app.models.batch import Supplier
from wholesale_support import CABLE, STORE, admin, seed


def utc_today() -> date:
    """The API dates bills and journal periods in UTC, which differs from local time around midnight."""
    return datetime.now(UTC).date()


def received_order(client, headers, supplier_name: str = "Volt Trading", quantity: int = 10, cost: int = 600) -> dict:
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": supplier_name,
            "destination_store_id": STORE,
            "lines": [{"product_id": CABLE, "quantity_ordered": quantity, "unit_cost_cents": cost}],
        },
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": order["lines"][0]["id"], "quantity": quantity}]},
    )
    assert received.status_code == 200, received.text
    return received.json()


def supplier(session, name: str = "Volt Trading", terms: int = 30) -> Supplier:
    row = Supplier(name=name, code=name[:4].upper(), payment_terms_days=terms)
    session.add(row)
    session.commit()
    return row


def test_receipt_becomes_a_bill_paid_in_cash_then_by_cheque(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    volt = supplier(session)
    order = received_order(client, headers)

    unbilled = client.get("/api/v1/payables/receipts/unbilled", headers=headers).json()
    assert len(unbilled) == 1 and unbilled[0]["value_cents"] == 6000
    today = utc_today()
    bill = client.post(
        "/api/v1/payables/bills/from-receipt",
        headers=headers,
        json={"goods_receipt_id": unbilled[0]["goods_receipt_id"], "number": "VT-2291", "bill_date": str(today)},
    )
    assert bill.status_code == 201, bill.text
    body = bill.json()
    assert (body["subtotal_cents"], body["tax_cents"], body["total_cents"]) == (6000, 300, 6300)
    assert body["due_date"] == str(today + timedelta(days=30)) and body["purchase_order_number"] == order["number"]
    again = client.post(
        "/api/v1/payables/bills/from-receipt",
        headers=headers,
        json={"goods_receipt_id": unbilled[0]["goods_receipt_id"], "number": "VT-2292", "bill_date": str(today)},
    )
    assert again.status_code == 409

    cash = client.post(
        "/api/v1/payables/payments",
        headers=headers,
        json={"supplier_id": str(volt.id), "amount_cents": 2000, "method": "cash", "paid_on": str(today)},
    )
    assert cash.status_code == 201, cash.text
    assert cash.json()["allocations"][0]["amount_cents"] == 2000
    cheque = client.post(
        "/api/v1/payables/payments",
        headers=headers,
        json={
            "supplier_id": str(volt.id),
            "amount_cents": 4300,
            "method": "cheque",
            "paid_on": str(today),
            "cheque": {"number": "000771", "bank": "Emirates NBD", "cheque_date": str(today + timedelta(days=20))},
        },
    ).json()
    assert cheque["status"] == "ISSUED"
    summary = client.get("/api/v1/payables/summary", headers=headers).json()
    assert summary["outstanding_cents"] == 0 and summary["cheques_issued_cents"] == 4300
    paid = client.get("/api/v1/payables/bills", headers=headers, params={"status": "PAID"}).json()
    assert [row["number"] for row in paid] == ["VT-2291"]

    voided = client.post(f"/api/v1/payables/payments/{cheque['id']}/void", headers=headers, json={"note": "Lost"})
    assert voided.json()["status"] == "VOID"
    reopened = client.get("/api/v1/payables/bills", headers=headers, params={"status": "UNPAID"}).json()
    assert reopened[0]["balance_cents"] == 4300 and reopened[0]["status"] == "PARTIAL"

    statement = client.get(f"/api/v1/payables/suppliers/{volt.id}/statement", headers=headers).json()
    assert [row["kind"] for row in statement["rows"]] == ["BILL", "PAYMENT"]
    assert statement["rows"][-1]["balance_cents"] == 4300 and statement["aging"]["current"] == 4300

    exported = client.get("/api/v1/exports/gl.csv", headers=headers, params={"from": str(today), "to": str(today)})
    rows = [
        row
        for row in csv.DictReader(io.StringIO(exported.text))
        if row["journal"] in ("STOCK", "PURCHASES", "PAYMENTS")
    ]
    balance: dict[str, float] = defaultdict(float)
    by_account: dict[str, float] = defaultdict(float)
    for row in rows:
        balance[row["reference"]] += float(row["debit"] or 0) - float(row["credit"] or 0)
        by_account[row["account"]] += float(row["debit"] or 0) - float(row["credit"] or 0)
    assert rows and all(abs(value) < 0.001 for value in balance.values())
    assert {"1200", "2050", "1300", "2000", "1000"} <= {row["account"] for row in rows}
    # The receipt put the stock on the books; the bill cleared "stock received, not billed".
    assert abs(by_account["2050"]) < 0.001 and by_account["1200"] > 0


def test_manual_bill_rules(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    landlord = supplier(session, "Al Noor Properties", terms=0)
    body = {
        "supplier_id": str(landlord.id),
        "store_id": STORE,
        "number": "RENT-OCT",
        "bill_date": str(utc_today() - timedelta(days=40)),
        "lines": [
            {"description": "Shop rent October", "quantity": 1, "unit_cost_cents": 500000, "tax_category": "STANDARD"},
            {"description": "Service charge", "quantity": 1, "unit_cost_cents": 20000, "tax_category": "EXEMPT"},
        ],
    }
    created = client.post("/api/v1/payables/bills", headers=headers, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["tax_cents"] == 25000 and created.json()["overdue_days"] == 40
    assert client.post("/api/v1/payables/bills", headers=headers, json=body).status_code == 409
    summary = client.get("/api/v1/payables/summary", headers=headers).json()
    assert summary["overdue_cents"] == 545000

    too_much = client.post(
        "/api/v1/payables/payments",
        headers=headers,
        json={
            "supplier_id": str(landlord.id),
            "amount_cents": 1000,
            "method": "transfer",
            "paid_on": str(utc_today()),
            "allocations": [{"bill_id": created.json()["id"], "amount_cents": 2000}],
        },
    )
    assert too_much.status_code == 422
    advance = client.post(
        "/api/v1/payables/payments",
        headers=headers,
        json={
            "supplier_id": str(landlord.id),
            "amount_cents": 600000,
            "method": "transfer",
            "paid_on": str(utc_today()),
        },
    ).json()
    assert advance["unallocated_cents"] == 55000
    assert client.post(f"/api/v1/payables/bills/{created.json()['id']}/void", headers=headers).status_code == 409
