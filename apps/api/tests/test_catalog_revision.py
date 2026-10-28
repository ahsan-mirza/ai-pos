"""Registers can see that the catalog moved without downloading every product."""

import uuid

from app.models.product import Product


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
