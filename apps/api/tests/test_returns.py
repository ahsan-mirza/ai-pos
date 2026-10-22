import uuid
from datetime import UTC, datetime, timedelta
from typing import get_args

from sqlalchemy.orm import Session

from app.models import AuditLog, ReturnItem, Sale, SerialNumber
from app.schemas.payloads import SaleStatus, SerialStatus
from app.services.identifiers import is_valid_imei
from app.services.returns_service import prorated_tax, restocking_fee

API_KEY = "test-api-key-value"
ADMIN_PASSWORD = "root-password-123"
CASHIER_PIN = "1357"
STORE_ID = "00000000-0000-4000-8000-000000000001"
CABLE_ID = "00000000-0000-4000-8000-000000000010"
PHONE_ID = "00000000-0000-4000-8000-000000000012"
CASHIER_ID = "00000000-0000-4000-8000-000000000002"
STORE_MANAGER_ROLE = "00000000-0000-4000-8000-0000000000a2"
TAX_BPS = 500


def test_status_columns_fit_every_value() -> None:
    # SQLite ignores VARCHAR lengths, so Postgres-only truncation errors would otherwise slip through.
    columns = [
        (Sale.__table__.c.status, SaleStatus),
        (SerialNumber.__table__.c.status, SerialStatus),
    ]
    for column, literal in columns:
        longest = max(get_args(literal), key=len)
        assert len(longest) <= column.type.length, f"{column} cannot store {longest!r}"
    # Condition and reason keys come from the returns policy: up to 32 characters (pos_policy.KEY_PATTERN).
    for column in (ReturnItem.__table__.c.condition_status, ReturnItem.__table__.c.reason_code):
        assert column.type.length >= 32


def device() -> dict[str, str]:
    return {"X-Api-Key": API_KEY}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def imei(seed: str = "49015420323751") -> str:
    return next(f"{seed}{digit}" for digit in range(10) if is_valid_imei(f"{seed}{digit}"))


def push(client, entity: str, payload: dict, key: str | None = None):
    event = {
        "idempotency_key": key or f"{entity}-{uuid.uuid4()}",
        "entity_type": entity,
        "operation": "upsert",
        "payload": payload,
        "occurred_at": "2026-10-19T08:00:00Z",
    }
    return client.post("/api/v1/sync/push", headers=device(), json={"device_id": "register-1", "events": [event]})


def seed_catalog(client) -> None:
    assert (
        push(client, "store", {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "USD"}).status_code
        == 200
    )
    for product in (
        {
            "id": CABLE_ID,
            "sku": "ACC-CABLE-USBC",
            "barcode": "100000000001",
            "name": "USB-C Cable",
            "category": "Accessories",
            "price_cents": 1500,
            "is_serialized": False,
            "stock_quantity": 10,
        },
        {
            "id": PHONE_ID,
            "sku": "PHN-PIXEL-9",
            "barcode": "100000000003",
            "name": "Pixel 9",
            "category": "Phones",
            "price_cents": 79900,
            "is_serialized": True,
            "stock_quantity": 0,
        },
    ):
        response = push(client, "product", {**product, "store_id": STORE_ID, "currency": "USD"})
        assert response.status_code == 200, response.text


def record_sale(
    client, *, product_id: str, price: int, quantity: int = 1, serial: str | None = None, payment: str = "cash"
) -> dict:
    tax = round(price * quantity * TAX_BPS / 10_000)
    sale_id = str(uuid.uuid4())
    payload = {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": payment,
        "subtotal_cents": price * quantity,
        "tax_cents": tax,
        "total_cents": price * quantity + tax,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": quantity,
                "unit_price_cents": price,
                "tax_cents": tax,
                "line_total_cents": price * quantity + tax,
                "serial_value": serial,
                "serial_kind": "imei" if serial else None,
            }
        ],
    }
    response = push(client, "sale", payload)
    assert response.status_code == 200, response.text
    return payload


def receipt(client, code: str) -> dict:
    response = client.get(f"/api/v1/returns/receipts/{code}", headers=device())
    assert response.status_code == 200, response.text
    return response.json()


def return_payload(
    receipt_body: dict,
    *,
    quantity: int = 1,
    condition: str = "unopened_resealable",
    serial: str | None = None,
    tender: str = "cash",
    waive_fee: bool = False,
    cashier_id: str = CASHIER_ID,
    override: dict | None = None,
    credit_code: str | None = None,
) -> dict:
    line = receipt_body["items"][0]
    tax = prorated_tax(
        line["tax_cents"], line["quantity"], quantity, line["returned_quantity"], line["refunded_tax_cents"]
    )
    fee_bps = next(row["fee_bps"] for row in receipt_body["policy"]["conditions"] if row["key"] == condition)
    fee = 0 if waive_fee else restocking_fee(line["unit_price_cents"], quantity, fee_bps)
    subtotal = line["unit_price_cents"] * quantity
    total = subtotal + tax - fee
    return {
        "id": str(uuid.uuid4()),
        "original_sale_id": receipt_body["sale_id"],
        "store_id": STORE_ID,
        "cashier_id": cashier_id,
        "currency": "USD",
        "processed_at": datetime.now(UTC).isoformat(),
        "subtotal_cents": subtotal,
        "tax_refund_cents": tax,
        "restocking_fee_cents": fee,
        "total_refund_cents": total,
        "reason_notes": "Customer changed their mind.",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "sale_item_id": line["sale_item_id"],
                "product_id": line["product_id"],
                "quantity": quantity,
                "unit_price_cents": line["unit_price_cents"],
                "tax_refund_cents": tax,
                "restocking_fee_cents": fee,
                "refund_cents": total,
                "condition_status": condition,
                "reason_code": "defective" if condition == "defective_doa" else "changed_mind",
                "serial_value": serial,
                "serial_kind": "imei" if serial else None,
            }
        ],
        "tenders": [{"method": tender, "amount_cents": total, "store_credit_code": credit_code}],
        "override": override,
    }


def admin_token(client) -> str:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def admin_id(client) -> str:
    return client.get("/api/v1/auth/me", headers=bearer(admin_token(client))).json()["id"]


def approval(approver_id: str, *reasons: str) -> dict:
    return {"approved_by_id": approver_id, "reasons": list(reasons) or ["no_refund_permission"], "note": "Checked box."}


def test_pricing_rules_do_not_drift() -> None:
    assert restocking_fee(79900, 1, 1500) == 11985
    assert restocking_fee(79900, 1, 0) == 0
    refunded = 0
    for returned in range(4):
        share = prorated_tax(2, 4, 1, returned, refunded)
        refunded += share
        assert share >= 0
    assert refunded == 2


def test_receipt_lookup_by_invoice_number(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    body = receipt(client, sale["id"][:8].upper())
    assert body["sale_id"] == sale["id"]
    assert body["invoice"].startswith("DT-01-S-")
    assert body["items"][0]["returned_quantity"] == 0
    assert body["policy"]["window_days"] == 30
    assert client.get("/api/v1/returns/receipts/ffffffff", headers=device()).status_code == 404


def test_cashier_without_refund_permission_needs_manager(client, session: Session) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    body = receipt(client, sale["id"])

    blocked = push(client, "sale_return", return_payload(body))
    assert blocked.status_code == 422
    assert "Manager approval is required" in blocked.json()["error"]["message"]

    self_approved = push(client, "sale_return", return_payload(body, override=approval(CASHIER_ID)))
    assert self_approved.status_code == 422
    assert self_approved.json()["error"]["message"] == "A cashier cannot approve their own return."

    approved = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert approved.status_code == 200, approved.text

    product = client.get(f"/api/v1/products/{CABLE_ID}", headers=device()).json()
    assert product["stock_quantity"] == 10 - 2 + 1
    assert session.get(Sale, uuid.UUID(sale["id"])).status == "partially_refunded"
    logs = session.query(AuditLog).filter(AuditLog.action_type == "REFUND_PROCESSED").all()
    assert len(logs) == 1
    assert logs[0].details["required"] == ["no_refund_permission"]
    assert logs[0].approver_id is not None and logs[0].reason_notes


def test_serialized_return_needs_matching_imei_and_routes_to_repair(client, session: Session) -> None:
    seed_catalog(client)
    sold = imei()
    sale = record_sale(client, product_id=PHONE_ID, price=79900, serial=sold)
    body = receipt(client, sale["id"])
    assert body["items"][0]["serial_last4"] == sold[-4:]
    manager = approval(admin_id(client))

    missing = push(client, "sale_return", return_payload(body, condition="defective_doa", override=manager))
    assert missing.status_code == 422
    other = imei("35693803564380")
    wrong = push(client, "sale_return", return_payload(body, condition="defective_doa", serial=other, override=manager))
    assert wrong.status_code == 422
    assert wrong.json()["error"]["message"] == "IMEI or serial number does not match the unit that was sold."

    ok = push(client, "sale_return", return_payload(body, condition="defective_doa", serial=sold, override=manager))
    assert ok.status_code == 200, ok.text
    serial = session.query(SerialNumber).one()
    assert serial.status == "repair"
    assert session.get(Sale, uuid.UUID(sale["id"])).status == "refunded"

    again = push(client, "sale_return", return_payload(body, condition="defective_doa", serial=sold, override=manager))
    assert again.status_code == 422
    assert again.json()["error"]["message"] == "Every item on this sale was already returned."


def test_returned_units_in_repair_cannot_be_resold(client) -> None:
    seed_catalog(client)
    sold = imei()
    sale = record_sale(client, product_id=PHONE_ID, price=79900, serial=sold)
    body = receipt(client, sale["id"])
    returned = push(
        client,
        "sale_return",
        return_payload(body, condition="open_box", serial=sold, override=approval(admin_id(client))),
    )
    assert returned.status_code == 200, returned.text

    tax = round(79900 * TAX_BPS / 10_000)
    resale_id = str(uuid.uuid4())
    resale = {
        "id": resale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": 79900,
        "tax_cents": tax,
        "total_cents": 79900 + tax,
        "client_sale_id": resale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": PHONE_ID,
                "quantity": 1,
                "unit_price_cents": 79900,
                "tax_cents": tax,
                "line_total_cents": 79900 + tax,
                "serial_value": sold,
                "serial_kind": "imei",
            }
        ],
    }
    rejected = push(client, "sale", resale)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["message"] == "Identifier is in quarantine."


def test_quantity_cannot_exceed_what_was_sold(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    body = receipt(client, sale["id"])
    payload = return_payload(body, override=approval(admin_id(client)))
    payload["items"][0]["quantity"] = 2
    response = push(client, "sale_return", payload)
    assert response.status_code == 422


def test_open_box_fee_waiver_needs_a_different_approver(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    manager = client.post(
        "/api/v1/users",
        headers=bearer(token),
        json={
            "username": "manager.dt",
            "email": "manager@example.com",
            "full_name": "Store Manager",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": STORE_ID,
            "password": "manager-password-1",
            "pin": "8642",
            "has_portal_access": True,
            "has_pos_access": True,
        },
    ).json()
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    body = receipt(client, sale["id"])

    as_manager = return_payload(body, condition="open_box", waive_fee=True, cashier_id=manager["id"])
    blocked = push(client, "sale_return", as_manager)
    assert blocked.status_code == 422
    assert "restocking fee is waived" in blocked.json()["error"]["message"]

    charged = return_payload(body, condition="open_box", cashier_id=manager["id"])
    assert charged["restocking_fee_cents"] == 225
    assert push(client, "sale_return", charged).status_code == 200


def test_card_sale_refunds_to_card_or_credit_only(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1, payment="card")
    body = receipt(client, sale["id"])
    manager = approval(admin_id(client))

    cash = push(client, "sale_return", return_payload(body, tender="cash", override=manager))
    assert cash.status_code == 422
    assert "refund to Card or Store credit" in cash.json()["error"]["message"]

    credit = return_payload(body, tender="store_credit", credit_code="SC-AB12-CD34-EF56", override=manager)
    assert push(client, "sale_return", credit).status_code == 200
    stored = client.get(f"/api/v1/returns/{credit['id']}", headers=device()).json()
    assert stored["tenders"] == [
        {
            "method": "store_credit",
            "amount_cents": credit["total_refund_cents"],
            "store_credit_code": "SC-AB12-CD34-EF56",
        }
    ]
    invoice = client.get(f"/api/v1/sales/{sale['id']}/invoice.pdf", headers=device())
    assert invoice.status_code == 200
    assert invoice.content.startswith(b"%PDF")
    note = client.get(f"/api/v1/returns/{credit['id']}/credit-note.pdf", headers=device())
    assert note.status_code == 200
    assert note.content.startswith(b"%PDF")


def test_outside_window_requires_override(client, session: Session) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    row = session.get(Sale, uuid.UUID(sale["id"]))
    row.created_at = datetime.now(UTC) - timedelta(days=45)
    session.commit()
    body = receipt(client, sale["id"])
    approver = admin_id(client)

    partial = push(client, "sale_return", return_payload(body, override=approval(approver, "no_refund_permission")))
    assert partial.status_code == 422
    assert "older than the 30-day return window" in partial.json()["error"]["message"]

    full = return_payload(body, override=approval(approver, "no_refund_permission", "outside_window"))
    assert push(client, "sale_return", full).status_code == 200


def test_direct_endpoint_requires_approver_token(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    body = receipt(client, sale["id"])
    cashier_token = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": CASHIER_PIN},
        headers=device(),
    ).json()["access_token"]
    headers = {**bearer(cashier_token), "X-Device-Id": "register-1", "Idempotency-Key": "return-direct-0001"}
    payload = return_payload(body, override=approval(admin_id(client)))

    missing = client.post("/api/v1/returns", headers=headers, json=payload)
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "approval_required"

    manager_token = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "admin", "pin": "2468"},
        headers=device(),
    ).json()["access_token"]
    created = client.post("/api/v1/returns", headers={**headers, "X-Approver-Token": manager_token}, json=payload)
    assert created.status_code == 201, created.text
    replay = client.post("/api/v1/returns", headers={**headers, "X-Approver-Token": manager_token}, json=payload)
    assert replay.status_code == 200


def test_returns_analytics_and_net_revenue(client) -> None:
    seed_catalog(client)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    body = receipt(client, sale["id"])
    approver = admin_id(client)
    for _ in range(3):
        body = receipt(client, sale["id"])
        if body["items"][0]["returned_quantity"] >= 2:
            break
        assert push(client, "sale_return", return_payload(body, override=approval(approver))).status_code == 200

    token = admin_token(client)
    analytics = client.get("/api/v1/returns/analytics", headers=bearer(token)).json()
    assert analytics["return_count"] == 2
    assert analytics["units_returned"] == 2
    assert analytics["override_count"] == 2
    assert analytics["top_products"][0]["sku"] == "ACC-CABLE-USBC"
    assert analytics["cashiers"][0]["override_count"] == 2
    assert analytics["cashiers"][0]["flagged"] is False

    summary = client.get("/api/v1/analytics/summary", headers=bearer(token)).json()
    assert summary["net_revenue_cents"] == 0
