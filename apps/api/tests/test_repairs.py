import uuid

from sqlalchemy import select
from tests.test_open_price import labour_product
from tests.test_warranty import repair

from app.models.inventory import InventoryLevel
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from wholesale_support import CABLE, admin, event, imeis, push, seed


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


def test_invoicing_needs_lines(client) -> None:
    ticket, headers = booked(client)
    empty = client.post(f"/api/v1/repairs/{ticket['id']}/invoice", headers=headers, json={})
    assert empty.status_code == 422 and "parts and labour" in empty.json()["error"]["message"]
