"""Variant grids stay idempotent, prices respect overrides, and inventory links are not duplicated."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.test_fashion import tee_model
from tests.test_manual_adjustments import adjust, adjustment
from tests.test_returns import (
    STORE_ID,
    admin_id,
    admin_token,
    approval,
    bearer,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)

from app.models import PriceChange, Product

ROOT = Path(__file__).resolve().parents[3]


def _grid(client, token: str, model_id: str, body: dict):
    response = client.post(f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_generation_keeps_skus_and_override_prices(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    model_id = tee_model(client, token)
    body = {
        "axes": [{"key": "size", "values": ["S", "M"]}, {"key": "color", "values": ["Black", "White"]}],
        "price_cents": 4900,
        "price_by_value": {"M": 5200},
    }
    first = _grid(client, token, model_id, body)
    assert (first["created"], first["skipped"]) == (4, 0)
    by_attr = {tuple(sorted(cell["attributes"].items())): cell for cell in first["cells"]}
    medium = by_attr[(("color", "Black"), ("size", "M"))]
    small = by_attr[(("color", "Black"), ("size", "S"))]
    white = by_attr[(("color", "White"), ("size", "S"))]
    assert medium["price_cents"] == 5200 and medium["price_source"] == "rule"
    assert small["price_source"] == "default" and small["price_cents"] == 4900
    identity = {cell["product_id"]: (cell["sku"], cell["barcode"]) for cell in first["cells"]}

    again = _grid(client, token, model_id, body)
    assert (again["created"], again["skipped"]) == (0, 4)
    for cell in again["cells"]:
        assert (cell["sku"], cell["barcode"]) == identity[cell["product_id"]]

    wider = {
        **body,
        "axes": [
            {"key": "size", "values": ["S", "M", "L"]},
            {"key": "color", "values": ["Black", "White", "Navy"]},
        ],
    }
    added = _grid(client, token, model_id, wider)
    assert added["created"] == 5 and added["skipped"] == 4
    for cell in added["cells"]:
        if cell["product_id"] in identity:
            assert (cell["sku"], cell["barcode"]) == identity[cell["product_id"]]

    preview = client.post(f"/api/v1/product-models/{model_id}/matrix/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["creating"] == 0 and preview.json()["existing"] == 4

    overridden = client.patch(
        f"/api/v1/products/{small['product_id']}", headers=headers, json={"price_cents": 6000}
    )
    assert overridden.status_code == 200 and overridden.json()["price_source"] == "override"
    updated = client.patch(
        f"/api/v1/product-models/{model_id}", headers=headers, json={"default_price_cents": 5100}
    )
    assert updated.status_code == 200, updated.text
    grid = client.get(f"/api/v1/product-models/{model_id}/matrix", headers=headers).json()
    prices = {cell["product_id"]: cell["price_cents"] for cell in grid["cells"]}
    assert prices[small["product_id"]] == 6000
    assert prices[medium["product_id"]] == 5200
    assert prices[white["product_id"]] == 5100
    changes = list(session.scalars(select(PriceChange).where(PriceChange.product_id == uuid.UUID(white["product_id"]))))
    assert any(row.new_price_cents == 5100 and row.old_price_cents == 4900 for row in changes)

    original = session.get(Product, uuid.UUID(small["product_id"]))
    assert original is not None
    session.add(
        Product(
            sku="TEE-DUP",
            barcode="DUP-BARCODE-1",
            name="Duplicate",
            category=original.category,
            price_cents=100,
            currency=original.currency,
            product_model_id=original.product_model_id,
            variant_attributes=dict(original.variant_attributes or {}),
            variant_signature=original.variant_signature,
            price_source="override",
            tenant_id=original.tenant_id,
        )
    )
    with pytest.raises(IntegrityError) as caught:
        session.flush()
    message = str(caught.value)
    assert "variant_signature" in message
    assert "uq_products_model_variant" in message or "UNIQUE constraint failed" in message
    session.rollback()


def test_matrix_on_hand_is_the_store_balance(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    model_id = tee_model(client, token)
    grid = _grid(
        client,
        token,
        model_id,
        {"axes": [{"key": "size", "values": ["S"]}, {"key": "color", "values": ["Black"]}], "price_cents": 4900},
    )
    cell = grid["cells"][0]
    added = adjust(client, headers, adjustment(cell["product_id"], STORE_ID, "add", 2, "PHYSICAL_COUNT_AUDIT"))
    assert added.status_code == 201, added.text
    scoped = client.get(
        f"/api/v1/product-models/{model_id}/matrix",
        headers=headers,
        params={"store_id": STORE_ID},
    ).json()
    [row] = scoped["cells"]
    assert row["on_hand"] == 2
    assert sum(row["by_store"].values()) == 2


def test_inactive_variant_can_be_returned_but_not_sold(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    model_id = tee_model(client, token)
    grid = _grid(
        client,
        token,
        model_id,
        {"axes": [{"key": "size", "values": ["S"]}, {"key": "color", "values": ["Black"]}], "price_cents": 4900},
    )
    product_id = grid["cells"][0]["product_id"]
    stocked = adjust(client, headers, adjustment(product_id, STORE_ID, "add", 2, "PHYSICAL_COUNT_AUDIT"))
    assert stocked.status_code == 201, stocked.text
    sale = record_sale(client, product_id=product_id, price=4900, quantity=1)
    body = receipt(client, sale["id"])
    retired = client.patch(f"/api/v1/products/{product_id}", headers=headers, json={"is_active": False})
    assert retired.status_code == 200 and retired.json()["is_active"] is False
    refused_id = str(uuid.uuid4())
    refused = push(
        client,
        "sale",
        {
            "id": refused_id,
            "store_id": STORE_ID,
            "cashier_id": sale["cashier_id"],
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": 4900,
            "tax_cents": round(4900 * 5 / 100),
            "total_cents": 4900 + round(4900 * 5 / 100),
            "client_sale_id": refused_id,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "quantity": 1,
                    "unit_price_cents": 4900,
                    "tax_cents": round(4900 * 5 / 100),
                    "line_total_cents": 4900 + round(4900 * 5 / 100),
                }
            ],
        },
    )
    assert refused.status_code == 422 and "inactive" in refused.text.lower()
    returned = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert returned.status_code in (200, 201), returned.text
    assert "inactive" not in returned.text.lower()


def test_inventory_pages_stay_on_the_tab_bar() -> None:
    nav = (ROOT / "apps/web/src/components/layout/navigation.ts").read_text(encoding="utf-8")
    layout = (ROOT / "apps/web/src/features/inventory/InventoryLayout.tsx").read_text(encoding="utf-8")
    for path in (
        "/inventory/purchase-orders",
        "/inventory/transfers",
        "/inventory/serials",
        "/inventory/markdowns",
        "/inventory/size-curve",
    ):
        assert f'to: "{path}"' not in nav
        assert path in layout
    assert 'to: "/inventory"' in nav
