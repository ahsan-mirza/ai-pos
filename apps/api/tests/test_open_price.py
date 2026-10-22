import uuid

from sqlalchemy import select

from app.core.permissions import CASHIER_ROLE_ID
from app.models.role import RolePermission
from app.models.sale_item import SaleItem
from wholesale_support import STORE, event, line, push, sale, seed

LABOUR = "00000000-0000-4000-8000-000000000099"


def labour_product() -> dict:
    return {
        "id": LABOUR,
        "store_id": STORE,
        "sku": "SRV-LABOUR",
        "barcode": "990000000001",
        "name": "Repair labour",
        "category": "Services",
        "price_cents": 0,
        "currency": "USD",
        "is_serialized": False,
        "is_open_price": True,
        "stock_quantity": 0,
    }


def test_open_price_lines_need_permission_and_description(client, session) -> None:
    seed(client)
    assert push(client, [event("labour-product", "product", labour_product())]).status_code == 200

    item = line(LABOUR, 1, 12_000)
    blocked = push(client, [event("labour-no-perm", "sale", sale([{**item, "description": "Screen swap"}]))])
    assert blocked.status_code == 422
    assert "cannot sell open-price" in blocked.json()["error"]["message"]

    session.add(RolePermission(role_id=uuid.UUID(CASHIER_ROLE_ID), permission="pos:open_price"))
    session.commit()
    undescribed = push(client, [event("labour-no-desc", "sale", sale([line(LABOUR, 1, 12_000)]))])
    assert undescribed.status_code == 422
    assert "description" in undescribed.json()["error"]["message"]

    body = sale([{**line(LABOUR, 1, 12_000), "description": "Screen swap, iPhone 13"}])
    sold = push(client, [event("labour-sold", "sale", body)])
    assert sold.status_code == 200, sold.text
    stored = session.scalar(select(SaleItem).where(SaleItem.sale_id == uuid.UUID(body["id"])))
    assert stored.description == "Screen swap, iPhone 13"
