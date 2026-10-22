import uuid

from sqlalchemy import select

from app.models.product import Product
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from wholesale_support import CABLE, CASHIER_ID, PHONE, STORE, admin, device, event, imeis, line, push, sale, seed

CHECKLIST = {"powers_on": True, "screen_ok": True, "body_ok": True, "account_removed": True, "battery_pct": 88}


def trade_in(cashier_id: str, imei: str, **overrides) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "store_id": STORE,
        "cashier_id": cashier_id,
        "product_id": PHONE,
        "identifier_kind": "imei",
        "identifier_value": imei,
        "grade": "B",
        "checklist": CHECKLIST,
        "seller_name": "Omar Khalid",
        "seller_phone": "+971501112233",
        "seller_id_number": "784-1990-1234567-1",
        "offer_cents": 30_000,
        "resale_price_cents": 45_000,
        "payout": "SALE_CREDIT",
    }
    body.update(overrides)
    return body


def test_sale_credit_trade_in_is_spent_once_and_resells_at_cost(client, session) -> None:
    seed(client)
    _, admin_id = admin(client)
    imei = imeis(1, "35693803777")[0]
    checked = client.post("/api/v1/trade-ins/check", headers=device(), json={"kind": "imei", "value": imei}).json()
    assert checked["ok"] is True

    created = client.post("/api/v1/trade-ins", headers=device(), json=trade_in(admin_id, imei))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "ACCEPTED" and body["resale_sku"] == "PO-PHN-PIXEL-9-B"
    assert body["identifier_tail"] == f"…{imei[-4:]}" and body["seller_id_last4"] == "67-1"
    retried = client.post("/api/v1/trade-ins", headers=device(), json={**trade_in(admin_id, imei), "id": body["id"]})
    assert retried.json()["number"] == body["number"]
    again = client.post("/api/v1/trade-ins/check", headers=device(), json={"kind": "imei", "value": imei}).json()
    assert again["ok"] is False and "in stock" in again["message"]

    purchase = sale(
        [line(CABLE, 30, 1500)],
        payment_method="cash",
        tenders=[
            {"method": "trade_in", "amount_cents": 30_000, "trade_in_id": body["id"]},
            {"method": "cash", "amount_cents": 15_000},
        ],
    )
    applied = push(client, [event("trade-in-sale-1", "sale", purchase)])
    assert applied.status_code == 200, applied.text
    twice = sale(
        [line(CABLE, 20, 1500)],
        tenders=[{"method": "trade_in", "amount_cents": 30_000, "trade_in_id": body["id"]}],
        payment_method="trade_in",
    )
    rejected = push(client, [event("trade-in-sale-2", "sale", twice)])
    assert rejected.status_code == 422 and "already applied" in rejected.json()["error"]["message"]

    resale = session.scalar(select(Product).where(Product.sku == "PO-PHN-PIXEL-9-B"))
    assert resale.price_cents == 45_000 and resale.category == "Pre-owned"
    resold = sale([line(str(resale.id), 1, 45_000, serial=imei)])
    assert push(client, [event("trade-in-resale", "sale", resold)]).status_code == 200
    item = session.scalar(select(SaleItem).where(SaleItem.sale_id == uuid.UUID(resold["id"])))
    assert item.cost_cents == 30_000


def test_store_credit_payout_and_guards(client, session) -> None:
    seed(client, phone_units=1)
    _, admin_id = admin(client)
    stocked = session.scalar(select(SerialNumber).where(SerialNumber.status == "in_stock"))
    assert stocked is not None
    fresh = imeis(1, "35391805399")[0]

    locked = client.post(
        "/api/v1/trade-ins",
        headers=device(),
        json=trade_in(admin_id, fresh, checklist={**CHECKLIST, "account_removed": False}),
    )
    assert locked.status_code == 422 and "iCloud" in locked.json()["error"]["message"]
    no_permission = client.post("/api/v1/trade-ins", headers=device(), json=trade_in(CASHIER_ID, fresh))
    assert no_permission.status_code == 403

    credit = client.post(
        "/api/v1/trade-ins", headers=device(), json=trade_in(admin_id, fresh, payout="STORE_CREDIT", grade="D")
    ).json()
    assert credit["status"] == "APPLIED" and credit["store_credit_code"].startswith("SC-")
    voucher = client.get(f"/api/v1/store-credits/{credit['store_credit_code']}", headers=device()).json()
    assert voucher["balance_cents"] == 30_000 and voucher["return_id"] is None
    faulty = session.scalar(select(SerialNumber).where(SerialNumber.id == uuid.UUID(_serial_id(session, credit))))
    assert faulty.status == "repair"
    assert client.post(f"/api/v1/trade-ins/{credit['id']}/cancel", headers=device()).status_code == 409


def test_unspent_sale_credit_can_be_cancelled(client, session) -> None:
    seed(client)
    _, admin_id = admin(client)
    imei = imeis(1, "35693803888")[0]
    body = client.post("/api/v1/trade-ins", headers=device(), json=trade_in(admin_id, imei)).json()
    cancelled = client.post(f"/api/v1/trade-ins/{body['id']}/cancel", headers=device())
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    serial = session.get(SerialNumber, uuid.UUID(_serial_id(session, body)))
    session.refresh(serial)
    assert serial.status == "reversed"


def _serial_id(session, body: dict) -> str:
    from app.models.trade_in import TradeIn

    return str(session.get(TradeIn, uuid.UUID(body["id"])).serial_number_id)
