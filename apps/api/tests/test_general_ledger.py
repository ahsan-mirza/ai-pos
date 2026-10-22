import uuid
from datetime import UTC, datetime, timedelta

from app.models.accounting import JournalEntry
from app.models.batch import BatchItem, PurchaseBatch
from wholesale_support import CABLE, STORE, admin, device, event, line, push, sale, seed

TODAY = datetime.now(UTC).date()
SPAN = {"from": "2026-10-01", "to": str(TODAY)}


def _accounts(client, headers) -> dict[str, dict]:
    response = client.get("/api/v1/accounting/accounts", headers=headers)
    assert response.status_code == 200, response.text
    return {row["code"]: row for row in response.json()}


def _post(client, headers, span=SPAN) -> dict:
    response = client.post("/api/v1/accounting/post", headers=headers, json=span)
    assert response.status_code == 200, response.text
    return response.json()


def _journal(client, headers, account: str, amount: int, other: str, *, day: str, memo: str = "Test") -> dict:
    accounts = _accounts(client, headers)
    response = client.post(
        "/api/v1/accounting/journals",
        headers=headers,
        json={
            "entry_date": day,
            "memo": memo,
            "lines": [
                {"account_id": accounts[account]["id"], "debit_cents": amount},
                {"account_id": accounts[other]["id"], "credit_cents": amount},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_documents_post_once_and_follow_their_changes(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    card = sale([line(CABLE, 10, 1500)], payment_method="card", tenders=[{"method": "card", "amount_cents": 15_000}])
    assert (
        push(
            client, [event("gl-card-sale", "sale", card), event("gl-cash-sale", "sale", sale([line(CABLE, 2, 1500)]))]
        ).status_code
        == 200
    )
    expense = client.post(
        "/api/v1/expenses",
        headers=headers,
        json={
            "store_id": STORE,
            "category": "RENT",
            "description": "Shop rent October",
            "spent_on": str(TODAY),
            "total_cents": 50_000,
            "tax_cents": 0,
            "paid_from": "BANK",
        },
    ).json()

    first = _post(client, headers)
    assert first["posted"] == 3 and first["unbalanced"] == []
    assert _post(client, headers) == {"posted": 0, "reversed": 0, "unchanged": 3, "unbalanced": []}

    trial = client.get("/api/v1/accounting/trial-balance", headers=headers, params=SPAN).json()
    assert trial["total_debit_cents"] == trial["total_credit_cents"] > 0
    closing = {row["code"]: row["closing_cents"] for row in trial["rows"]}
    assert closing["1010"] == 15_000 and closing["1000"] == 3_000
    assert closing["4000"] == -18_000 and closing["6100"] == 50_000 and closing["1020"] == -50_000

    statement = client.get("/api/v1/accounting/income-statement", headers=headers, params=SPAN).json()
    assert statement["sections"][0]["total_cents"] == 18_000
    assert statement["net_profit_cents"] == 18_000 - 50_000 - statement["sections"][1]["total_cents"]
    sheet = client.get("/api/v1/accounting/balance-sheet", headers=headers).json()
    assert sheet["balanced"] is True
    assert {check["key"] for check in sheet["checks"]} == {"inventory", "receivables", "payables"}

    client.post(f"/api/v1/expenses/{expense['id']}/void", headers=headers, json={"reason": "Entered twice"})
    after = _post(client, headers)
    assert after["reversed"] == 1 and after["posted"] == 0
    reversal = session.query(JournalEntry).filter(JournalEntry.journal == "REVERSAL").one()
    assert reversal.reference == expense["number"]
    closing = {
        row["code"]: row["closing_cents"]
        for row in client.get("/api/v1/accounting/trial-balance", headers=headers, params=SPAN).json()["rows"]
    }
    assert closing["6100"] == 0

    ledger = client.get(
        f"/api/v1/accounting/accounts/{_accounts(client, headers)['1010']['id']}/ledger", headers=headers, params=SPAN
    ).json()
    assert ledger["closing_cents"] == 15_000 and ledger["rows"][-1]["balance_cents"] == 15_000

    auto = session.query(JournalEntry).filter(JournalEntry.source_ref.like("sale:%")).first()
    refused = client.post(f"/api/v1/accounting/journals/{auto.id}/reverse", headers=headers, json={})
    assert refused.status_code == 409


def test_manual_journals_and_locked_periods(client) -> None:
    seed(client)
    headers, _ = admin(client)
    accounts = _accounts(client, headers)
    unbalanced = client.post(
        "/api/v1/accounting/journals",
        headers=headers,
        json={
            "entry_date": str(TODAY),
            "memo": "Opening capital",
            "lines": [
                {"account_id": accounts["1020"]["id"], "debit_cents": 100_000},
                {"account_id": accounts["3000"]["id"], "credit_cents": 90_000},
            ],
        },
    )
    assert unbalanced.status_code == 422 and unbalanced.json()["error"]["code"] == "unbalanced"
    opening = _journal(client, headers, "1020", 100_000, "3000", day=str(TODAY), memo="Opening capital")
    assert opening["reversible"] is True and opening["total_cents"] == 100_000
    reversed_entry = client.post(f"/api/v1/accounting/journals/{opening['id']}/reverse", headers=headers, json={})
    assert reversed_entry.status_code == 200 and reversed_entry.json()["journal"] == "REVERSAL"
    again = client.post(f"/api/v1/accounting/journals/{opening['id']}/reverse", headers=headers, json={})
    assert again.status_code == 409

    locked = client.post("/api/v1/accounting/lock", headers=headers, json={"locked_until": "2026-10-19"})
    assert locked.json()["locked_until"] == "2026-10-19"
    blocked = client.post(
        "/api/v1/accounting/journals",
        headers=headers,
        json={
            "entry_date": "2026-10-19",
            "memo": "Back-dated",
            "lines": [
                {"account_id": accounts["1020"]["id"], "debit_cents": 100},
                {"account_id": accounts["3000"]["id"], "credit_cents": 100},
            ],
        },
    )
    assert blocked.status_code == 409
    # A sale synced late for the locked day posts into the first open day.
    assert push(client, [event("gl-late-sale", "sale", sale([line(CABLE, 1, 1500)]))]).status_code == 200
    _post(client, headers)
    late = client.get("/api/v1/accounting/journals", headers=headers, params={"journal": "SALES"}).json()[0]
    assert late["entry_date"] == "2026-10-20" and late["original_date"] == "2026-10-19"
    assert client.post("/api/v1/accounting/lock", headers=headers, json={"locked_until": str(TODAY)}).status_code == 422


def test_year_end_close_and_corporate_tax(client) -> None:
    seed(client)
    headers, _ = admin(client)
    _journal(client, headers, "1020", 50_000_000, "4300", day="2025-06-01", memo="Consulting income")
    _journal(client, headers, "6100", 1_000_000, "1020", day="2025-07-01", memo="Rent")

    estimate = client.get("/api/v1/accounting/corporate-tax", headers=headers, params={"year": 2025}).json()
    assert estimate["revenue_cents"] == 50_000_000 and estimate["profit_before_tax_cents"] == 49_000_000
    # 9% of the AED 115,000 above the AED 375,000 threshold.
    assert estimate["tax_cents"] == 1_035_000 and estimate["small_business_relief_eligible"] is True
    adjusted = client.get(
        "/api/v1/accounting/corporate-tax",
        headers=headers,
        params={"year": 2025, "add_backs_cents": 1_000_000},
    ).json()
    assert adjusted["tax_cents"] == 1_125_000
    provision = client.post(
        "/api/v1/accounting/corporate-tax/provision",
        headers=headers,
        json={"fiscal_year": 2025, "amount_cents": 1_035_000},
    )
    assert provision.status_code == 201, provision.text
    assert provision.json()["entry_date"] == "2025-12-31"

    bad_end = client.post("/api/v1/accounting/close-year", headers=headers, json={"year_end": "2025-11-30"})
    assert bad_end.status_code == 422
    closed = client.post("/api/v1/accounting/close-year", headers=headers, json={"year_end": "2025-12-31"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["journal"] == "CLOSING"
    assert (
        client.post("/api/v1/accounting/close-year", headers=headers, json={"year_end": "2025-12-31"}).status_code
        == 409
    )
    assert client.get("/api/v1/accounting/settings", headers=headers).json()["locked_until"] == "2025-12-31"

    year = {"from": "2025-01-01", "to": "2025-12-31"}
    statement = client.get("/api/v1/accounting/income-statement", headers=headers, params=year).json()
    assert statement["net_profit_cents"] == 49_000_000 - 1_035_000
    sheet = client.get("/api/v1/accounting/balance-sheet", headers=headers, params={"as_of": "2025-12-31"}).json()
    equity = {row["name"]: row["amount_cents"] for row in sheet["sections"][2]["rows"]}
    assert equity["Retained earnings"] == 49_000_000 - 1_035_000
    assert "Current earnings (not yet closed)" not in equity
    assert sheet["balanced"] is True


def test_imported_batch_is_billed_and_clears_stock_received(client, session) -> None:
    seed(client)
    headers, admin_id = admin(client)
    supplier = client.post("/api/v1/payables/suppliers", headers=headers, json={"name": "Gulf Accessories FZE"}).json()
    batch = PurchaseBatch(
        batch_number="BATCH-GL-1",
        supplier_id=uuid.UUID(supplier["id"]),
        store_id=uuid.UUID(STORE),
        import_source="CSV",
        currency="USD",
        total_cost_amount=8_000,
        total_items_count=10,
        created_by_id=uuid.UUID(admin_id),
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    session.add(batch)
    session.flush()
    session.add(
        BatchItem(
            batch_id=batch.id,
            product_id=uuid.UUID(CABLE),
            store_id=uuid.UUID(STORE),
            quantity_imported=10,
            quantity_remaining=10,
            purchase_cost_per_unit=800,
            selling_price_per_unit=1500,
        )
    )
    session.commit()

    unbilled = client.get("/api/v1/payables/receipts/unbilled", headers=headers).json()
    row = next(item for item in unbilled if item["purchase_batch_id"] == str(batch.id))
    assert row["value_cents"] == 8_000 and row["supplier_name"] == "Gulf Accessories FZE"
    bill = client.post(
        "/api/v1/payables/bills/from-receipt",
        headers=headers,
        json={"purchase_batch_id": str(batch.id), "number": "GA-1001", "bill_date": str(TODAY)},
    )
    assert bill.status_code == 201, bill.text
    assert bill.json()["goods_receipt_number"] == "BATCH-GL-1" and bill.json()["subtotal_cents"] == 8_000
    twice = client.post(
        "/api/v1/payables/bills/from-receipt",
        headers=headers,
        json={"purchase_batch_id": str(batch.id), "number": "GA-1002", "bill_date": str(TODAY)},
    )
    assert twice.status_code == 409
    assert all(
        item["purchase_batch_id"] != str(batch.id)
        for item in client.get("/api/v1/payables/receipts/unbilled", headers=headers).json()
    )

    _post(client, headers)
    closing = {
        row["code"]: row["closing_cents"]
        for row in client.get("/api/v1/accounting/trial-balance", headers=headers, params=SPAN).json()["rows"]
    }
    assert closing["1200"] == 8_000 and closing.get("2050", 0) == 0 and closing["2000"] < 0


def test_accounting_needs_the_accounting_permission(client) -> None:
    seed(client)
    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    ).json()["access_token"]
    assert client.get("/api/v1/accounting/accounts", headers={"Authorization": f"Bearer {cashier}"}).status_code == 403
    assert client.get("/api/v1/accounting/accounts").status_code == 401
