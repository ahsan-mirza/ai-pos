from datetime import date, timedelta

from wholesale_support import CABLE, admin, create_customer, event, line, push, sale, seed


def test_cheque_tender_bounce_reopens_the_invoice_and_holds_credit(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=1_000_000)
    dated = date.today() + timedelta(days=30)
    body = sale(
        [line(CABLE, 2, 1500)],
        customer_id=customer["id"],
        sale_type="WHOLESALE",
        payment_method="cheque",
        tenders=[
            {
                "method": "cheque",
                "amount_cents": 3000,
                "reference": "000123",
                "cheque": {"cheque_number": "000123", "bank": "Emirates NBD", "cheque_date": dated.isoformat()},
            }
        ],
    )
    assert push(client, [event("cheque-sale-key", "sale", body)]).status_code == 200, "sale"

    listing = client.get("/api/v1/cheques", headers=headers).json()
    assert listing["stats"]["in_hand_cents"] == 3000
    cheque = listing["cheques"][0]
    assert (cheque["status"], cheque["customer_name"]) == ("RECEIVED", "Ali Traders LLC")
    detail = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert detail["cheque_exposure_cents"] == 3000

    early = client.post(f"/api/v1/cheques/{cheque['id']}/deposit", headers=headers, json={})
    assert early.status_code == 422 and "dated" in early.json()["error"]["message"]

    bounced = client.post(
        f"/api/v1/cheques/{cheque['id']}/bounce",
        headers=headers,
        json={"note": "Insufficient funds", "fee_cents": 5000},
    )
    assert bounced.status_code == 200, bounced.text
    assert [row["to_status"] for row in bounced.json()["events"]] == ["RECEIVED", "BOUNCED"]

    after = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert after["current_balance_cents"] == 3000 + 5000
    assert after["credit_hold"] is True
    assert after["cheque_exposure_cents"] == 0
    sold = client.get(f"/api/v1/sales/{body['id']}", headers=headers).json()
    assert sold["payment_status"] == "ON_ACCOUNT_UNPAID"


def test_account_payment_by_cheque_is_tracked(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers)
    paid = client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        headers=headers,
        json={
            "amount_cents": 2500,
            "method": "cheque",
            "cheque": {"cheque_number": "555", "bank": "ADCB", "cheque_date": date.today().isoformat()},
        },
    )
    assert paid.status_code == 201, paid.text
    cheque = client.get("/api/v1/cheques", headers=headers).json()["cheques"][0]
    assert cheque["source"] == "LEDGER"
    deposited = client.post(f"/api/v1/cheques/{cheque['id']}/deposit", headers=headers, json={})
    assert deposited.json()["status"] == "DEPOSITED"
    cleared = client.post(f"/api/v1/cheques/{cheque['id']}/clear", headers=headers, json={})
    assert cleared.json()["status"] == "CLEARED"
    again = client.post(f"/api/v1/cheques/{cheque['id']}/bounce", headers=headers, json={})
    assert again.status_code == 422
