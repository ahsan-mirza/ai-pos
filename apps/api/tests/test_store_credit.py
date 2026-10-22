import uuid

from tests.test_returns import (
    CABLE_ID,
    CASHIER_ID,
    STORE_ID,
    TAX_BPS,
    admin_id,
    admin_token,
    approval,
    bearer,
    device,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)

CODE = "SC-AB12-CD34-EF56"


def issue_credit(client) -> int:
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2, payment="card")
    body = receipt(client, sale["id"])
    credit = return_payload(
        body, quantity=2, tender="store_credit", credit_code=CODE, override=approval(admin_id(client))
    )
    assert push(client, "sale_return", credit).status_code == 200
    return credit["total_refund_cents"]


def spend(client, amount: int, *, code: str | None = CODE, key: str | None = None):
    tax = round(1500 * TAX_BPS / 10_000)
    total = 1500 + tax
    sale_id = str(uuid.uuid4())
    tenders = [{"method": "store_credit", "amount_cents": amount, "reference": code or "", "store_credit_code": code}]
    if total > amount:
        tenders.append({"method": "cash", "amount_cents": total - amount})
    payload = {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "store_credit",
        "subtotal_cents": 1500,
        "tax_cents": tax,
        "total_cents": total,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": CABLE_ID,
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_cents": tax,
                "line_total_cents": total,
            }
        ],
        "tenders": tenders,
    }
    return push(client, "sale", payload, key=key)


def test_voucher_pays_part_of_a_sale_and_keeps_the_rest(client) -> None:
    seed_catalog(client)
    issued = issue_credit(client)
    looked_up = client.get(f"/api/v1/store-credits/{CODE.lower()}", headers=device())
    assert looked_up.status_code == 200 and looked_up.json()["balance_cents"] == issued

    assert spend(client, 1000).status_code == 200
    after = client.get(f"/api/v1/store-credits/{CODE}", headers=device()).json()
    assert after["balance_cents"] == issued - 1000
    assert [use["amount_cents"] for use in after["uses"]] == [1000]

    portal = client.get("/api/v1/store-credits", headers=bearer(admin_token(client))).json()
    assert portal["outstanding_cents"] == issued - 1000 and portal["open_count"] == 1


def test_voucher_cannot_be_overspent(client) -> None:
    seed_catalog(client)
    issued = issue_credit(client)
    assert spend(client, 1575).status_code == 200
    assert spend(client, issued - 1575 - 75).status_code == 200
    overdrawn = spend(client, 100)
    assert overdrawn.status_code == 422
    assert "only 0.75" in overdrawn.json()["error"]["message"]
    balance = client.get(f"/api/v1/store-credits/{CODE}", headers=device()).json()["balance_cents"]
    assert balance == 75


def test_store_credit_tender_needs_a_known_code(client) -> None:
    seed_catalog(client)
    missing = spend(client, 500, code="SC-ZZZZ-ZZZZ-ZZZZ")
    assert missing.status_code == 422 and "does not exist" in missing.json()["error"]["message"]
    no_code = spend(client, 500, code=None)
    assert no_code.status_code == 422 and "voucher code" in no_code.json()["error"]["message"]
    assert client.get("/api/v1/store-credits/SC-ZZZZ-ZZZZ-ZZZZ", headers=device()).status_code == 404
