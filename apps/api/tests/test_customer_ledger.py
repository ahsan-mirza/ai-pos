import uuid
from datetime import UTC, datetime, timedelta

from tests.test_capabilities import change_profile

from app.models.customer import CustomerLedgerEntry
from app.models.loyalty import LoyaltyEntry
from app.models.product import Product
from app.models.sale import Sale
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, create_customer, device, event, line, push, sale, seed


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


def test_on_account_is_refused_when_credit_is_off(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert change_profile(client, headers, "retail_fashion").status_code == 200
    customer = create_customer(client, headers, credit_limit_cents=0, payment_terms="DUE_ON_RECEIPT")
    body = sale(
        [line(CABLE, 1, 1500)],
        customer_id=customer["id"],
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 1500}],
    )
    refused = push(client, [event("no-credit", "sale", body)])
    assert refused.status_code == 422
    assert session.query(CustomerLedgerEntry).count() == 0
    blocked = client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        headers=headers,
        json={"amount_cents": 100, "method": "cash"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "capability_disabled"


def test_cash_sale_keeps_history_and_points_off_the_debt_ledger(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert change_profile(client, headers, "grocery").status_code == 200
    turned_on = client.put(
        "/api/v1/loyalty/settings",
        headers=headers,
        json={"enabled": True, "earn_per_unit": 1, "redeem_cents": 1, "min_redeem": 50},
    )
    assert turned_on.status_code == 200, turned_on.text
    customer = create_customer(
        client, headers, customer_type="RETAIL", credit_limit_cents=0, payment_terms="DUE_ON_RECEIPT"
    )
    product = session.get(Product, uuid.UUID(CABLE))
    product.variant_attributes = {"size": "M", "color": "Blue"}
    session.commit()
    body = sale([line(CABLE, 1, 1500)], customer_id=customer["id"], tenders=[{"method": "cash", "amount_cents": 1500}])
    assert push(client, [event("cash-history", "sale", body)]).status_code == 200
    walk_in = sale([line(CABLE, 1, 1500)], tenders=[{"method": "cash", "amount_cents": 1500}])
    walked = push(client, [event("walk-in-sale", "sale", walk_in)])
    assert walked.status_code == 200, walked.text

    assert session.query(CustomerLedgerEntry).count() == 0
    assert session.query(LoyaltyEntry).count() == 1
    history = client.get(f"/api/v1/customers/{customer['id']}/history", headers=device())
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["name"] == product.name
    assert rows[0]["size"] == "M"
    assert rows[0]["unit_price_cents"] == 1500
    assert rows[0]["invoice"]


def test_return_reduces_an_unpaid_balance_once(client, session) -> None:
    seed(client)
    headers, user_id = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=100_000)
    body = credit_sale(client, customer["id"], "credit-return", 2)
    payload = {
        "id": str(uuid.uuid4()),
        "original_sale_id": body["id"],
        "store_id": STORE,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "processed_at": datetime.now(UTC).isoformat(),
        "subtotal_cents": 1500,
        "tax_refund_cents": 0,
        "restocking_fee_cents": 0,
        "total_refund_cents": 1500,
        "reason_notes": "One cable came back.",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "sale_item_id": body["items"][0]["id"],
                "product_id": CABLE,
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_refund_cents": 0,
                "restocking_fee_cents": 0,
                "refund_cents": 1500,
                "condition_status": "unopened_resealable",
                "reason_code": "changed_mind",
            }
        ],
        "tenders": [{"method": "store_credit", "amount_cents": 1500, "store_credit_code": "SC-LEDG-RET1-0001"}],
        "override": {"approved_by_id": user_id, "reasons": ["no_refund_permission"], "note": "Checked."},
    }
    returned = push(client, [event("credit-return-1", "sale_return", payload)])
    assert returned.status_code == 200, returned.text
    session.expire_all()
    sale_row = session.get(Sale, uuid.UUID(body["id"]))
    assert sale_row.due_balance_cents == 1500
    assert session.query(CustomerLedgerEntry).filter_by(entry_type="ADJUSTMENT").count() == 1

    from app.models.customer import Customer
    from app.services import ledger_service

    owner = session.get(Customer, uuid.UUID(customer["id"]))
    ledger_service.credit_return(
        session, owner, sale_row, return_id=uuid.UUID(payload["id"]), refund_cents=1500, user_id=None
    )
    session.commit()
    assert session.query(CustomerLedgerEntry).filter_by(entry_type="ADJUSTMENT").count() == 1
    assert owner.current_balance_cents == 1500

    history = client.get(f"/api/v1/customers/{customer['id']}/history", headers=device()).json()
    assert history[0]["quantity_refunded"] == 1
    assert history[0]["sale_status"] == "partially_refunded"


def test_customer_sync_is_available_to_registers(client) -> None:
    seed(client)
    headers, _ = admin(client)
    create_customer(client, headers)
    response = client.get("/api/v1/customers/sync", headers=device())
    assert response.status_code == 200, response.text
    assert response.json()[0]["price_tier"] == "TIER_1"
