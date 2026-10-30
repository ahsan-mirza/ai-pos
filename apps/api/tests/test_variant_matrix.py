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
    CABLE_ID,
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

from app.models import InventoryLevel, PriceChange, Product, SaleItem
from app.tenancy.context import TenantRef, use_tenant

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


def _cell(grid: dict, size: str, color: str) -> dict:
    return next(row for row in grid["cells"] if row["attributes"] == {"size": size, "color": color})


def _stock(client, headers: dict, sku: str, store_id: str = STORE_ID) -> dict:
    body = client.get("/api/v1/inventory/stock", headers=headers, params={"store_id": store_id, "limit": 100})
    assert body.status_code == 200, body.text
    return next(row for row in body.json()["rows"] if row["sku"] == sku)


def test_selected_size_color_variants_stock_sell_and_stay_isolated(client, session: Session) -> None:
    """A fashion style stocks, sells, receives, counts, and transfers each size/color on its own."""
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    model_id = tee_model(client, token)
    axes = [{"key": "size", "values": ["S", "M"]}, {"key": "color", "values": ["Black", "White"]}]
    chosen = [
        {
            "attributes": {"size": "S", "color": "Black"},
            "sku": "TROUSER-S-BLACK",
            "opening_quantity": 5,
            "min_reorder_level": 2,
            "cost_cents": 2000,
        },
        {"attributes": {"size": "S", "color": "White"}, "price_cents": 5100, "opening_quantity": 0},
        {"attributes": {"size": "M", "color": "Black"}, "opening_quantity": 1},
    ]
    body = {
        "axes": axes,
        "price_cents": 4900,
        "sku_prefix": "TROUSER",
        "opening_store_id": STORE_ID,
        "specifications": {"fabric": "Cotton"},
        "variants": chosen,
    }
    preview = client.post(f"/api/v1/product-models/{model_id}/matrix/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["creating"] == 3 and preview.json()["existing"] == 0

    first = _grid(client, token, model_id, body)
    assert (first["created"], first["skipped"], len(first["cells"])) == (3, 0, 3)
    assert all(row["attributes"] != {"size": "M", "color": "White"} for row in first["cells"])
    black = _cell(first, "S", "Black")
    white = _cell(first, "S", "White")
    medium = _cell(first, "M", "Black")
    assert black["sku"] == "TROUSER-S-BLACK"
    assert black["price_cents"] == 4900 and black["cost_cents"] == 2000
    assert white["price_cents"] == 5100 and white["price_source"] == "override"
    assert len({row["sku"] for row in first["cells"]}) == 3
    assert len({row["barcode"] for row in first["cells"]}) == 3
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 5
    assert _stock(client, headers, black["sku"])["min_reorder_level"] == 2
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 0
    assert _stock(client, headers, medium["sku"])["quantity_on_hand"] == 1
    stored = session.get(Product, uuid.UUID(black["product_id"]))
    assert stored is not None and stored.specifications.get("fabric") == "Cotton"
    found = client.get("/api/v1/products/search", headers=headers, params={"q": black["barcode"], "limit": 5})
    assert found.status_code == 200
    assert any(hit["product"]["id"] == black["product_id"] for hit in found.json())

    again = _grid(client, token, model_id, body)
    assert (again["created"], again["skipped"]) == (0, 3)
    assert _cell(again, "S", "Black")["product_id"] == black["product_id"]
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 5

    duplicate = client.post(
        f"/api/v1/product-models/{model_id}/matrix",
        headers=headers,
        json={**body, "variants": [chosen[0], chosen[0]]},
    )
    assert duplicate.status_code == 422

    sale = record_sale(client, product_id=black["product_id"], price=4900, quantity=2)
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 3
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 0
    assert _stock(client, headers, medium["sku"])["quantity_on_hand"] == 1
    session.expire_all()
    line = session.scalar(select(SaleItem).where(SaleItem.sale_id == uuid.UUID(sale["id"])))
    assert line is not None and line.variant_attributes == {"size": "S", "color": "Black"}
    assert line.product_id == uuid.UUID(black["product_id"])
    printed = receipt(client, sale["id"])
    assert printed["items"][0]["variant"]
    assert "S" in printed["items"][0]["variant"] and "Black" in printed["items"][0]["variant"]

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
            "subtotal_cents": 5100,
            "tax_cents": 255,
            "total_cents": 5355,
            "client_sale_id": refused_id,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": white["product_id"],
                    "quantity": 1,
                    "unit_price_cents": 5100,
                    "tax_cents": 255,
                    "line_total_cents": 5355,
                }
            ],
        },
    )
    assert refused.status_code == 422
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 0

    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Mill Cloth",
            "destination_store_id": STORE_ID,
            "lines": [{"product_id": white["product_id"], "quantity_ordered": 4, "unit_cost_cents": 1800}],
        },
    )
    assert order.status_code == 201, order.text
    purchase = order.json()
    assert client.post(f"/api/v1/inventory/purchase-orders/{purchase['id']}/order", headers=headers).status_code == 200
    received = client.post(
        f"/api/v1/inventory/purchase-orders/{purchase['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": purchase["lines"][0]["id"], "quantity": 4}]},
    )
    assert received.status_code == 200, received.text
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 4
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 3

    counted = adjust(client, headers, adjustment(black["product_id"], STORE_ID, "set", 2, "PHYSICAL_COUNT_AUDIT"))
    assert counted.status_code == 201, counted.text
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 2
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 4

    mall = "00000000-0000-4000-8000-0000000000b2"
    assert push(client, "store", {"id": mall, "code": "ML-01", "name": "Mall", "currency": "USD"}).status_code == 200
    transfer = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "source_store_id": STORE_ID,
            "destination_store_id": mall,
            "lines": [{"product_id": medium["product_id"], "quantity": 1}],
        },
    )
    assert transfer.status_code == 201, transfer.text
    transfer_id = transfer.json()["id"]
    shipped = client.post(f"/api/v1/inventory/transfers/{transfer_id}/ship", headers=headers, json={})
    assert shipped.status_code == 200, shipped.text
    received_transfer = client.post(f"/api/v1/inventory/transfers/{transfer_id}/receive", headers=headers)
    assert received_transfer.status_code == 200, received_transfer.text
    assert _stock(client, headers, medium["sku"])["quantity_on_hand"] == 0
    assert _stock(client, headers, medium["sku"], mall)["quantity_on_hand"] == 1
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 2

    curve = client.get(
        "/api/v1/reports/size-curve",
        headers=headers,
        params={"model_id": model_id, "from": "2026-10-01", "to": "2026-10-31"},
    )
    assert curve.status_code == 200, curve.text
    sold = next(row for row in curve.json()["cells"] if row["product_id"] == black["product_id"])
    assert sold["size"] == "S" and sold["color"] == "Black" and sold["sold"] == 2
    assert all(row["color"] != "White" or row["size"] != "M" for row in curve.json()["cells"])

    bulk = client.post(
        f"/api/v1/product-models/{model_id}/matrix/bulk",
        headers=headers,
        json={
            "product_ids": [black["product_id"], white["product_id"], medium["product_id"]],
            "price_cents": 4700,
            "only_unset": True,
        },
    )
    assert bulk.status_code == 200, bulk.text
    priced = client.get(f"/api/v1/product-models/{model_id}/matrix", headers=headers).json()
    assert _cell(priced, "S", "White")["price_cents"] == 5100
    assert _cell(priced, "S", "Black")["price_cents"] == 4700
    assert _cell(priced, "M", "Black")["price_cents"] == 4700

    added = _grid(
        client,
        token,
        model_id,
        {**body, "variants": [*chosen, {"attributes": {"size": "M", "color": "White"}, "opening_quantity": 0}]},
    )
    assert added["created"] == 1 and added["skipped"] == 3
    assert _cell(added, "M", "White")["product_id"] != black["product_id"]
    assert _stock(client, headers, black["sku"])["quantity_on_hand"] == 2
    assert _stock(client, headers, white["sku"])["quantity_on_hand"] == 4

    cable = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    assert cable["id"]
    session.expire_all()
    cable_level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(CABLE_ID),
            InventoryLevel.store_id == uuid.UUID(STORE_ID),
        )
    )
    assert cable_level is not None and cable_level.quantity_on_hand == 9


def test_variant_rows_stay_inside_the_tenant(session: Session) -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    with use_tenant(TenantRef(id=str(first), slug="one", name="One", database_url="sqlite://")):
        session.add(
            Product(
                sku="TEE-S-BLK",
                barcode="2001111111118",
                name="Tee S Black",
                category="Apparel",
                price_cents=1000,
                currency="USD",
                variant_attributes={"size": "S", "color": "Black"},
            )
        )
        session.commit()
    with use_tenant(TenantRef(id=str(second), slug="two", name="Two", database_url="sqlite://")):
        assert list(session.scalars(select(Product).where(Product.sku == "TEE-S-BLK"))) == []
        session.add(
            Product(
                sku="TEE-S-BLK",
                barcode="2001111111118",
                name="Other Tee",
                category="Apparel",
                price_cents=1000,
                currency="USD",
                variant_attributes={"size": "S", "color": "Black"},
            )
        )
        session.commit()
    with use_tenant(TenantRef(id=str(first), slug="one", name="One", database_url="sqlite://")):
        rows = list(session.scalars(select(Product).where(Product.sku == "TEE-S-BLK")))
        assert len(rows) == 1 and rows[0].name == "Tee S Black"


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
