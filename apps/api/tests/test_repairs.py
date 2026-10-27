import uuid

from sqlalchemy import func, select
from tests.test_open_price import labour_product
from tests.test_warranty import repair

from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.services.repair_service import _value_warning
from wholesale_support import CABLE, PHONE, admin, event, imeis, push, seed


def booked(client) -> tuple[dict, dict[str, str]]:
    seed(client)
    assert push(client, [event("labour-product", "product", labour_product())]).status_code == 200
    ticket = repair(imeis(1, "35391805313")[0])
    assert push(client, [event("repair-booked", "repair_ticket", ticket)]).status_code == 200
    headers, _ = admin(client)
    return ticket, headers


def test_timeline_records_register_and_portal_status_changes(client) -> None:
    ticket, headers = booked(client)
    assert push(client, [event("repair-diag", "repair_ticket", {**ticket, "status": "diagnosing"})]).status_code == 200
    moved = client.post(
        f"/api/v1/repairs/{ticket['id']}/status",
        headers=headers,
        json={"status": "in_repair", "note": "Waiting on screen part"},
    )
    assert moved.status_code == 200, moved.text
    events = moved.json()["events"]
    assert [(e["from_status"], e["to_status"], e["source"]) for e in events] == [
        (None, "intake", "register"),
        ("intake", "diagnosing", "register"),
        ("diagnosing", "in_repair", "portal"),
    ]
    assert events[-1]["note"] == "Waiting on screen part" and events[-1]["user_name"] == "Root Admin"


def test_parts_and_labour_invoice_as_a_sale_and_close_the_ticket(client, session) -> None:
    ticket, headers = booked(client)
    base = f"/api/v1/repairs/{ticket['id']}"
    part = client.post(f"{base}/lines", headers=headers, json={"kind": "PART", "product_id": CABLE, "quantity": 2})
    assert part.status_code == 201, part.text
    no_price = client.post(f"{base}/lines", headers=headers, json={"kind": "LABOUR", "description": "Port clean"})
    assert no_price.status_code == 422
    labour = client.post(
        f"{base}/lines",
        headers=headers,
        json={"kind": "LABOUR", "description": "Charging port replacement", "unit_price_cents": 8000},
    )
    assert labour.status_code == 201, labour.text
    detail = labour.json()
    assert (detail["parts_cents"], detail["labour_cents"], detail["total_cents"]) == (3000, 8000, 11000)

    on_hand = select(InventoryLevel.quantity_on_hand).where(InventoryLevel.product_id == uuid.UUID(CABLE))
    before = session.scalar(on_hand)
    invoiced = client.post(f"{base}/invoice", headers=headers, json={"payment_method": "card"})
    assert invoiced.status_code == 200, invoiced.text
    body = invoiced.json()
    assert body["status"] == "closed" and body["invoice_number"]
    assert body["events"][-1]["note"] == f"Invoiced {body['invoice_number']}"

    session.expire_all()
    sale = session.get(Sale, uuid.UUID(body["sale_id"]))
    assert sale is not None and sale.payment_method == "card"
    items = session.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)).all()
    assert sorted((item.quantity, item.description) for item in items) == [
        (1, "Charging port replacement"),
        (2, None),
    ]
    assert session.scalar(on_hand) == before - 2

    frozen = client.post(f"{base}/lines", headers=headers, json={"kind": "PART", "product_id": CABLE})
    assert frozen.status_code == 409
    assert client.post(f"{base}/invoice", headers=headers, json={}).status_code == 409


def test_customer_repair_does_not_create_or_consume_inventory(client, session) -> None:
    values = seed(client, phone_units=1)
    before = session.scalar(select(func.count()).select_from(Product))
    on_hand = select(InventoryLevel.quantity_on_hand).where(InventoryLevel.product_id == uuid.UUID(PHONE))
    stock = session.scalar(on_hand)
    ticket = repair(values[0])
    assert push(client, [event("customer-device", "repair_ticket", ticket)]).status_code == 200
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Product)) == before
    assert session.scalar(on_hand) == stock
    serial = session.scalar(select(SerialNumber).where(SerialNumber.product_id == uuid.UUID(PHONE)))
    assert serial is not None and serial.status == "in_stock"


def test_shop_equipment_is_a_cost_not_a_sale(client, session) -> None:
    seed(client)
    on_hand = select(InventoryLevel.quantity_on_hand).where(InventoryLevel.product_id == uuid.UUID(CABLE))
    stock = session.scalar(on_hand)
    ticket = repair(
        "SHOP-CABLE-1",
        ownership="internal",
        product_id=CABLE,
        customer_name="",
        customer_phone="",
        device_model="USB-C Cable",
        identifier_kind="serial",
    )
    booked_response = push(client, [event("shop-device", "repair_ticket", ticket)])
    assert booked_response.status_code == 200, booked_response.text
    session.expire_all()
    assert session.scalar(on_hand) == stock
    headers, _ = admin(client)
    found = client.get("/api/v1/repairs/devices", headers=headers, params={"q": "USB-C"})
    assert found.status_code == 200, found.text
    hit = found.json()[0]
    assert hit["sku"] == "ACC-CABLE-USBC" and hit["selling_price_cents"] == 1500
    assert hit["market_value"] == "Market value not configured"
    invoiced = client.post(f"/api/v1/repairs/{ticket['id']}/invoice", headers=headers, json={})
    assert invoiced.status_code == 422
    assert invoiced.json()["error"]["code"] == "internal_repair"
    assert session.scalar(select(func.count()).select_from(Sale)) == 0


def test_a_serialized_shop_device_needs_its_own_serial(client) -> None:
    seed(client, phone_units=1)
    ticket = repair(
        "not-stocked",
        ownership="internal",
        product_id=PHONE,
        customer_name="",
        customer_phone="",
        identifier_kind="serial",
    )
    refused = push(client, [event("missing-serial", "repair_ticket", ticket)])
    assert refused.status_code == 422
    assert "serial number" in refused.json()["error"]["message"]


def test_repair_cost_warning_uses_purchase_cost() -> None:
    assert _value_warning(6_000, 10_000) == "The estimate is 60% of the purchase cost. This is a warning only."
    assert _value_warning(4_000, 10_000) is None
    assert _value_warning(6_000, None) is None


def test_invoicing_needs_lines(client) -> None:
    ticket, headers = booked(client)
    empty = client.post(f"/api/v1/repairs/{ticket['id']}/invoice", headers=headers, json={})
    assert empty.status_code == 422 and "parts and labour" in empty.json()["error"]["message"]
