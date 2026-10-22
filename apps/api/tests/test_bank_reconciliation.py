from app.models.expense import Expense
from app.services.bank_statement_parser import parse, parse_amount
from wholesale_support import CABLE, STORE, admin, device, event, line, push, sale, seed

MT940 = """{1:F01EBILAEADAXXX0000000000}{4:
:20:STMT261020
:25:AE070260001015555555501
:28C:00001/001
:60F:C261018AED10000,00
:61:2610201020C14650,00NTRFNONREF//CARD261019
:86:MERCHANT SETTLEMENT DT-01 19OCT
:61:2610201020D500,00NCHGEXP-TRANSPORT
:86:ENOC FUEL CARD
:62F:C261020AED24150,00
-}"""


def _account(client, headers) -> str:
    response = client.post(
        "/api/v1/bank/accounts",
        headers=headers,
        json={"name": "Operating account", "bank": "Emirates NBD", "iban": "AE07 0260 0010 1555 5555 501"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["iban"] == "AE070260001015555555501"
    return response.json()["id"]


def _upload(client, headers, account: str, name: str, content: str):
    return client.post(
        f"/api/v1/bank/accounts/{account}/statements",
        headers=headers,
        files={"file": (name, content.encode(), "text/plain")},
    )


def test_parse_amounts_and_layouts() -> None:
    assert parse_amount("1,234.50") == 123_450
    assert parse_amount("(20.00)") == -2_000
    assert parse_amount("75.25 DR") == -7_525
    assert parse_amount("1500,00") == 150_000
    assert parse_amount("") is None
    fmt, lines = parse(
        b"Account statement\nPeriod: October\nValue Date,Narrative,Debit Amount,Credit Amount,Balance\n"
        b"19/10/2026,POS SETTLEMENT,,146.50,1146.50\n20/10/2026,DEWA BILL,300.00,,846.50\n",
        "enbd.csv",
    )
    assert fmt == "CSV"
    assert [(row.booked_on.isoformat(), row.amount_cents, row.balance_cents) for row in lines] == [
        ("2026-10-19", 14_650, 114_650),
        ("2026-10-20", -30_000, 84_650),
    ]
    fmt, lines = parse(MT940.encode(), "statement.sta")
    assert fmt == "MT940"
    assert [row.amount_cents for row in lines] == [1_465_000, -50_000]
    assert lines[0].description == "MERCHANT SETTLEMENT DT-01 19OCT"
    assert lines[1].balance_cents == 2_415_000


def test_card_settlement_net_of_fee_transfer_and_expense_auto_match(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    card_sale = sale(
        [line(CABLE, 10, 1500)], payment_method="card", tenders=[{"method": "card", "amount_cents": 15_000}]
    )
    transfer_sale = sale(
        [line(CABLE, 2, 1500)],
        payment_method="transfer",
        tenders=[{"method": "transfer", "amount_cents": 3_000, "reference": "TRX99881"}],
    )
    pushed = push(client, [event("bank-card", "sale", card_sale), event("bank-transfer", "sale", transfer_sale)])
    assert pushed.status_code == 200, pushed.text
    expense = client.post(
        "/api/v1/expenses",
        headers=headers,
        json={
            "store_id": STORE,
            "category": "UTILITIES",
            "description": "DEWA October",
            "payee": "DEWA",
            "spent_on": "2026-10-20",
            "total_cents": 30_000,
            "tax_cents": 0,
            "paid_from": "BANK",
        },
    )
    assert expense.status_code == 201, expense.text
    account = _account(client, headers)

    csv_body = (
        "Date,Description,Reference,Amount,Balance\n"
        "20/10/2026,CARD SETTLEMENT DT-01,,146.50,1146.50\n"
        "20/10/2026,INWARD TT ALI TRADERS TRX99881,,30.00,1176.50\n"
        "21/10/2026,DEWA DIRECT DEBIT,,-300.00,876.50\n"
        "22/10/2026,UNKNOWN DEPOSIT,,999.00,1875.50\n"
    )
    imported = _upload(client, headers, account, "october.csv", csv_body)
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["statement"]["lines_imported"] == 4
    assert body["auto_matched"] == 3

    again = _upload(client, headers, account, "october.csv", csv_body)
    assert again.json()["statement"]["lines_imported"] == 0
    assert again.json()["statement"]["lines_skipped"] == 4

    lines = {
        row["description"]: row for row in client.get(f"/api/v1/bank/accounts/{account}/lines", headers=headers).json()
    }
    settlement = lines["CARD SETTLEMENT DT-01"]
    assert settlement["status"] == "MATCHED" and settlement["auto_matched"]
    assert settlement["fee_cents"] == 350
    assert settlement["matched_key"].startswith("card:")
    assert lines["INWARD TT ALI TRADERS TRX99881"]["matched_key"].startswith("tender:")
    assert lines["DEWA DIRECT DEBIT"]["matched_key"].startswith("expense:")
    assert lines["UNKNOWN DEPOSIT"]["status"] == "UNMATCHED"

    fee = session.query(Expense).filter(Expense.category == "BANK_FEES").one()
    assert fee.total_cents == 350 and fee.paid_from == "BANK" and fee.status == "RECORDED"

    summary = client.get(f"/api/v1/bank/accounts/{account}/summary", headers=headers).json()
    assert summary["matched"] == 3 and summary["unmatched"] == 1
    assert summary["unmatched_in_cents"] == 99_900
    assert summary["fees_cents"] == 350
    assert summary["statement_balance_cents"] == 187_550

    unknown = lines["UNKNOWN DEPOSIT"]["id"]
    assert client.get(f"/api/v1/bank/lines/{unknown}/candidates", headers=headers).json() == []
    ignored = client.post(f"/api/v1/bank/lines/{unknown}/ignore", headers=headers, json={"note": "Owner top-up"})
    assert ignored.json()["status"] == "IGNORED"

    undone = client.post(f"/api/v1/bank/lines/{settlement['id']}/unmatch", headers=headers)
    assert undone.json()["status"] == "UNMATCHED"
    session.refresh(fee)
    assert fee.status == "VOID"
    options = client.get(f"/api/v1/bank/lines/{settlement['id']}/candidates", headers=headers).json()
    assert options[0]["kind"] == "CARD_SETTLEMENT" and options[0]["fee_cents"] == 350
    rematched = client.post(
        f"/api/v1/bank/lines/{settlement['id']}/match", headers=headers, json={"key": options[0]["key"]}
    )
    assert rematched.status_code == 200, rematched.text
    assert rematched.json()["auto_matched"] is False

    taken = client.post(
        f"/api/v1/bank/lines/{lines['DEWA DIRECT DEBIT']['id']}/match",
        headers=headers,
        json={"key": options[0]["key"]},
    )
    assert taken.status_code == 409


def test_bank_charge_booked_from_the_statement(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    account = _account(client, headers)
    _upload(client, headers, account, "c.csv", "Date,Description,Amount\n21/10/2026,MONTHLY ACCOUNT FEE,-26.25\n")
    line_id = client.get(f"/api/v1/bank/accounts/{account}/lines", headers=headers).json()[0]["id"]
    booked = client.post(f"/api/v1/bank/lines/{line_id}/book-charge", headers=headers, json={})
    assert booked.status_code == 200, booked.text
    assert booked.json()["status"] == "MATCHED" and booked.json()["matched_key"].startswith("expense:")
    charge = session.query(Expense).filter(Expense.category == "BANK_FEES").one()
    assert charge.total_cents == 2_625 and charge.paid_from == "BANK"
    client.post(f"/api/v1/bank/lines/{line_id}/unmatch", headers=headers)
    session.refresh(charge)
    assert charge.status == "VOID"


def test_ambiguous_amounts_are_left_for_a_person(client) -> None:
    seed(client)
    headers, _ = admin(client)
    first = sale(
        [line(CABLE, 1, 1500)], payment_method="transfer", tenders=[{"method": "transfer", "amount_cents": 1500}]
    )
    second = sale(
        [line(CABLE, 1, 1500)], payment_method="transfer", tenders=[{"method": "transfer", "amount_cents": 1500}]
    )
    pushed = push(client, [event("ambiguous-1", "sale", first), event("ambiguous-2", "sale", second)])
    assert pushed.status_code == 200, pushed.text
    account = _account(client, headers)
    imported = _upload(client, headers, account, "s.csv", "Date,Description,Amount\n19/10/2026,TRANSFER IN,15.00\n")
    assert imported.json()["auto_matched"] == 0
    line_id = client.get(f"/api/v1/bank/accounts/{account}/lines", headers=headers).json()[0]["id"]
    assert len(client.get(f"/api/v1/bank/lines/{line_id}/candidates", headers=headers).json()) == 2


def test_banking_needs_permission_and_rejects_unknown_layouts(client) -> None:
    seed(client)
    headers, _ = admin(client)
    account = _account(client, headers)
    bad = _upload(client, headers, account, "x.csv", "foo,bar\n1,2\n")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "unknown_statement_layout"
    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    ).json()["access_token"]
    denied = client.get("/api/v1/bank/accounts", headers={"Authorization": f"Bearer {cashier}"})
    assert denied.status_code == 403
