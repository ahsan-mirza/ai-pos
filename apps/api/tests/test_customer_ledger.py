from datetime import UTC, datetime, timedelta

from app.models.sale import Sale
from wholesale_support import CABLE, admin, create_customer, device, event, line, push, sale, seed


def credit_sale(client, customer_id: str, key: str, quantity: int) -> dict:
    body = sale(
        [line(CABLE, quantity, 1500)],
        customer_id=customer_id,
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 1500 * quantity}],
    )
    response = push(client, [event(key, "sale", body)])
    assert response.status_code == 200, response.text
    return body


def test_payment_allocates_oldest_invoice_first(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=100_000)
    first = credit_sale(client, customer["id"], "ledger-1", 2)
    second = credit_sale(client, customer["id"], "ledger-2", 4)
    older = session.get(Sale, __import__("uuid").UUID(first["id"]))
    older.created_at = datetime.now(UTC) - timedelta(days=45)
    older.due_date = datetime.now(UTC) - timedelta(days=15)
    session.commit()

    paid = client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        headers=headers,
        json={"amount_cents": 4000, "method": "transfer", "reference": "TRX-991"},
    )
    assert paid.status_code == 201, paid.text
    body = paid.json()
    assert [item["applied_cents"] for item in body["allocations"]] == [3000, 1000]
    assert body["allocations"][0]["sale_id"] == first["id"]
    assert body["customer"]["current_balance_cents"] == 5000

    first_sale = client.get(f"/api/v1/sales/{first['id']}", headers=device()).json()
    second_sale = client.get(f"/api/v1/sales/{second['id']}", headers=device()).json()
    assert first_sale["payment_status"] == "PAID"
    assert second_sale["payment_status"] == "PARTIAL"
    assert second_sale["due_balance_cents"] == 5000


def test_statement_shows_entries_and_aging(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=100_000)
    old = credit_sale(client, customer["id"], "aging-old", 2)
    credit_sale(client, customer["id"], "aging-new", 1)
    row = session.get(Sale, __import__("uuid").UUID(old["id"]))
    row.due_date = datetime.now(UTC) - timedelta(days=40)
    session.commit()

    statement = client.get(f"/api/v1/customers/{customer['id']}/statement", headers=headers)
    assert statement.status_code == 200, statement.text
    data = statement.json()
    assert [entry["entry_type"] for entry in data["entries"]] == ["INVOICE", "INVOICE"]
    assert data["entries"][-1]["balance_after_cents"] == 4500
    assert data["aging"]["days_31_60"] == 3000
    assert data["aging"]["current"] == 1500
    assert data["customer"]["overdue_cents"] == 3000
    assert len(data["open_invoices"]) == 2


def test_retail_customer_cannot_have_credit(client) -> None:
    seed(client)
    headers, _ = admin(client)
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Walk-in Sara", "customer_type": "RETAIL", "credit_limit_cents": 1000},
    )
    assert response.status_code == 422


def test_customer_sync_is_available_to_registers(client) -> None:
    seed(client)
    headers, _ = admin(client)
    create_customer(client, headers)
    response = client.get("/api/v1/customers/sync", headers=device())
    assert response.status_code == 200, response.text
    assert response.json()[0]["price_tier"] == "TIER_1"
