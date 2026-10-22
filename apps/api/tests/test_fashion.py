import uuid

from sqlalchemy.orm import Session
from tests.test_batches import import_csv
from tests.test_returns import (
    CABLE_ID,
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

from app.models import Product
from app.services import barcodes


def tee_model(client, token: str) -> str:
    headers = bearer(token)
    category = client.post("/api/v1/categories", headers=headers, json={"name": "Apparel"})
    assert category.status_code == 201, category.text
    created = client.post(
        f"/api/v1/categories/{category.json()['id']}/sub-categories", headers=headers, json={"name": "T-Shirts"}
    )
    sub = next(row for row in created.json()["sub_categories"] if row["name"] == "T-Shirts")
    brand = client.post("/api/v1/brands", headers=headers, json={"name": "Basics Co"}).json()
    model = client.post(
        "/api/v1/product-models",
        headers=headers,
        json={"brand_id": brand["id"], "sub_category_id": sub["id"], "name": "Classic Tee", "code": "TEE"},
    )
    assert model.status_code == 201, model.text
    return model.json()["id"]


def test_barcode_symbols() -> None:
    assert barcodes.ean13("590123412345") == "5901234123457"
    assert barcodes.is_ean13("5901234123457") and not barcodes.is_ean13("5901234123458")
    modules = barcodes.ean13_modules("5901234123457")
    assert len(modules) == 95 and modules.startswith("101") and modules[45:50] == "01010"
    code128 = barcodes.code128_modules("TEE-M-BLACK")
    assert code128.startswith("11010010000")  # START B
    assert code128.endswith("1100011101011")  # STOP
    assert len(code128) == 11 * (len("TEE-M-BLACK") + 2) + 13


def test_matrix_generates_variants_once_and_shows_the_grid(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    model_id = tee_model(client, token)
    body = {
        "axes": [{"key": "Size", "values": ["S", "M", "L", "XL"]}, {"key": "color", "values": ["Black", "White"]}],
        "price_cents": 4900,
        "price_by_value": {"XL": 5400},
    }
    first = client.post(f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token), json=body)
    assert first.status_code == 200, first.text
    grid = first.json()
    assert (grid["created"], grid["skipped"], len(grid["cells"])) == (8, 0, 8)
    cell = next(row for row in grid["cells"] if row["attributes"] == {"size": "XL", "color": "Black"})
    assert cell["sku"] == "TEE-XL-BLACK" and cell["price_cents"] == 5400
    assert cell["name"] == "Classic Tee XL Black" and barcodes.is_ean13(cell["barcode"])
    product = session.get(Product, uuid.UUID(cell["product_id"]))
    assert (product.category, product.brand) == ("Apparel", "Basics Co")

    body["axes"][0]["values"] = ["XS", "S", "M", "L", "XL"]
    again = client.post(f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token), json=body).json()
    assert (again["created"], again["skipped"]) == (2, 8)
    assert again["axes"][0] == {"key": "size", "values": ["XS", "S", "M", "L", "XL"]}

    too_big = {"axes": [{"key": "size", "values": [str(n) for n in range(40)]}] * 1, "price_cents": 100}
    too_big["axes"].append({"key": "color", "values": [f"C{n}" for n in range(11)]})
    assert (
        client.post(f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token), json=too_big).status_code == 422
    )

    labels = client.get(f"/api/v1/labels/models/{model_id}", headers=bearer(token))
    assert labels.status_code == 200 and labels.content.startswith(b"%PDF")


def test_matrix_is_part_of_the_variants_module(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    model_id = tee_model(client, token)
    switched = client.put("/api/v1/settings/profile", headers=bearer(token), json={"business_profile": "grocery"})
    assert switched.status_code == 200
    assert client.get(f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token)).status_code == 403


def test_consignment_is_billed_as_it_sells(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    supplier = client.post("/api/v1/inventory/suppliers", headers=headers, json={"name": "Dubai Denim Co"}).json()
    batch = import_csv(
        client,
        token,
        "Product Name,SKU,Qty,Unit Cost,Retail Price\nUSB-C Cable,ACC-CABLE-USBC,10,6.00,15.00\n",
        extra={"supplier_id": supplier["id"], "consignment": True},
    )
    assert batch["is_consignment"] is True

    refused = client.post(
        "/api/v1/payables/bills/from-receipt",
        headers=headers,
        json={"purchase_batch_id": batch["id"], "number": "DD-1", "bill_date": "2026-10-20"},
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "consignment_batch"

    valuation = client.get("/api/v1/reports/management/valuation", headers=headers).json()
    assert valuation["consignment_units"] == 10 and valuation["consignment_value_cents"] == 6000

    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=12)
    overview = client.get("/api/v1/consignment", headers=headers).json()
    [row] = overview["suppliers"]
    # FIFO draws the older owned stock first; only units beyond it come from the consignment batch.
    sold = row["units_sold"]
    assert sold >= 1 and row["unsettled_cents"] == sold * 600

    body = receipt(client, sale["id"])
    returned = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert returned.status_code == 200, returned.text

    settled = client.post("/api/v1/consignment/settlements", headers=headers, json={"supplier_id": supplier["id"]})
    assert settled.status_code == 201, settled.text
    [settlement] = settled.json()
    after = client.get("/api/v1/consignment", headers=headers).json()["suppliers"][0]
    assert settlement["units"] == after["units_sold"] and settlement["total_cents"] == after["units_sold"] * 600
    assert after["unsettled_units"] == 0 and after["settled_cents"] == settlement["total_cents"]
    bills = client.get("/api/v1/payables/bills", headers=headers).json()
    bill = next(row for row in bills if row["id"] == settlement["bill_id"])
    # The settlement is net; the bill adds the supplier's input VAT like any other bill.
    assert bill["number"] == settlement["number"] and bill["subtotal_cents"] == settlement["total_cents"]
    assert settlement["bill_total_cents"] == bill["total_cents"] >= settlement["total_cents"]
    again = client.post("/api/v1/consignment/settlements", headers=headers, json={"supplier_id": supplier["id"]})
    assert again.status_code == 422 and again.json()["error"]["code"] == "nothing_to_settle"


def test_labels_for_products_and_batches(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    sheet = client.post("/api/v1/labels", headers=headers, json={"items": [{"product_id": CABLE_ID, "copies": 30}]})
    assert sheet.status_code == 200 and sheet.headers["content-type"] == "application/pdf"
    assert sheet.content.count(b"/Type /Page\n") + sheet.content.count(b"/Type /Page ") >= 2
    roll = client.post(
        "/api/v1/labels",
        headers=headers,
        json={"items": [{"product_id": CABLE_ID, "copies": 3}], "layout": "roll_50x30", "show_price": False},
    )
    assert roll.status_code == 200 and roll.content.startswith(b"%PDF")
    batch = import_csv(
        client, token, "Product Name,SKU,Qty,Unit Cost,Retail Price\nUSB-C Cable,ACC-CABLE-USBC,4,6,15\n"
    )
    batch_labels = client.get(f"/api/v1/labels/batches/{batch['id']}", headers=headers)
    assert batch_labels.status_code == 200
    unknown = client.post("/api/v1/labels", headers=headers, json={"items": [{"product_id": str(uuid.uuid4())}]})
    assert unknown.status_code == 404
