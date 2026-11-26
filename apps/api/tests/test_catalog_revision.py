"""Registers can see that the catalog moved without downloading every product."""

import uuid

from app.models.product import Product
from app.models.store import Store
from app.tenancy.scoping import DEFAULT_TENANT_ID


def test_a_product_edit_is_announced_and_a_rollback_is_not(session):
    from app.websockets.rooms import QUEUE

    session.add(Store(code="A", name="Shop A", currency="AED", tenant_id=DEFAULT_TENANT_ID))
    product = Product(
        id=uuid.uuid4(),
        sku="DAL-1",
        barcode="1000000000099",
        name="Daal",
        category="Mains",
        price_cents=1500,
        currency="AED",
    )
    session.add(product)
    session.commit()
    assert not session.info.get(QUEUE)

    product.name = "Daal Channa"
    product.price_cents = 1800
    session.flush()
    queued = session.info[QUEUE]
    assert queued
    assert {payload["type"] for _, payload in queued} == {"catalogue.changed"}
    assert all(isinstance(payload["seq"], int) for _, payload in queued)

    session.rollback()
    assert not session.info.get(QUEUE)


def test_revision_moves_when_a_product_is_saved(client, session):
    headers = {"Authorization": f"Bearer {_token(client)}"}
    before = client.get("/api/v1/products/revision", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["count"] == 0

    session.add(
        Product(
            id=uuid.uuid4(),
            sku="NEW-1",
            barcode="1000000000001",
            name="New cable",
            category="Cables",
            price_cents=1000,
            currency="AED",
        )
    )
    session.commit()

    after = client.get("/api/v1/products/revision", headers=headers)
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["count"] == 1
    assert body["updated_at"]
    assert body["updated_at"] != before.json()["updated_at"] or before.json()["updated_at"] is None


def _token(client) -> str:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": "root-password-123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
