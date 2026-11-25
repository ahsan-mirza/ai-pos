"""Round-trip Excel import and export for products and restaurant menu items."""

import io
import uuid
import zipfile

from sqlalchemy import func, select
from tests.test_returns import CABLE_ID, CASHIER_PIN, admin_token, bearer, device, seed_catalog

from app.models import InventoryLevel, Product, StockMovement
from app.services.catalogue_xlsx import (
    FORMAT_VERSION,
    MENU_COLUMNS,
    OPTION_COLUMNS,
    PRODUCT_COLUMNS,
    SHEET_MENU,
    SHEET_META,
    SHEET_OPTIONS,
    SHEET_PRODUCTS,
    read_workbook,
    write_workbook,
)

MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _pack(sheets: dict[str, list[list[str]]]) -> bytes:
    order = ["Guide", SHEET_PRODUCTS, SHEET_MENU, SHEET_OPTIONS, "Modifiers", SHEET_META]
    payload = [(name, sheets[name]) for name in order if name in sheets]
    return write_workbook(payload, hidden={SHEET_META})


def _line(columns: tuple[str, ...], **values: object) -> list[str]:
    return ["" if values.get(name) is None else str(values.get(name, "")) for name in columns]


def _template(client, token: str) -> dict[str, list[list[str]]]:
    response = client.get("/api/v1/catalogue/workbook/template", headers=bearer(token))
    assert response.status_code == 200, response.text
    assert "AxizPOS_Product_Menu_Import_Template.xlsx" in response.headers["content-disposition"]
    return read_workbook(response.content, "AxizPOS_Product_Menu_Import_Template.xlsx")


def _category(client, token: str, name: str) -> None:
    response = client.post("/api/v1/categories", headers=bearer(token), json={"name": name})
    assert response.status_code in (200, 201), response.text


def _switch(client, token: str, profile: str) -> None:
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": profile, "capabilities": None},
    )
    assert response.status_code == 200, response.text


def _preview(client, token: str, payload: bytes, mode: str = "upsert"):
    return client.post(
        "/api/v1/catalogue/workbook/preview",
        headers=bearer(token),
        data={"mode": mode},
        files={"file": ("book.xlsx", payload, MEDIA)},
    )


def _commit(client, token: str, payload: bytes, job_id: str, mode: str = "upsert", key: str | None = None):
    return client.post(
        "/api/v1/catalogue/workbook/commit",
        headers={**bearer(token), "Idempotency-Key": key or str(uuid.uuid4())},
        data={"mode": mode, "job_id": job_id, "confirm": "true"},
        files={"file": ("book.xlsx", payload, MEDIA)},
    )


def _menu_book(client, token: str) -> bytes:
    sheets = _template(client, token)
    sheets[SHEET_MENU].append(
        _line(
            MENU_COLUMNS,
            **{
                "Menu Item Name": "Daal Channa",
                "Barcode": "281000000301",
                "Category": "Mains",
                "Base Price": "3.00",
                "Currency": "USD",
                "Tax Category": "STANDARD",
                "Price Includes Tax": "No",
                "Prepared Without Recipe": "Yes",
                "Active": "Yes",
                "Open Price": "No",
            },
        )
    )
    for position, (name, price) in enumerate((("Small Plate", "3.00"), ("Medium Plate", "5.00"),
        ("Full Plate", "9.00"))):
        sheets[SHEET_OPTIONS].append(
            _line(
                OPTION_COLUMNS,
                **{
                    "Product Name": "Daal Channa",
                    "Option Name": name,
                    "Price": price,
                    "Currency": "USD",
                    "Active": "Yes",
                    "Position": position,
                },
            )
        )
    return _pack(sheets)


def test_template_and_export_include_the_workbook_version(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    sheets = _template(client, token)
    meta = {row[0]: row[1] for row in sheets[SHEET_META] if row and row[0] != "Key"}
    assert meta["format_version"] == FORMAT_VERSION
    assert sheets[SHEET_PRODUCTS][0] == list(PRODUCT_COLUMNS)
    exported = client.get("/api/v1/catalogue/workbook/export", headers=bearer(token))
    assert exported.status_code == 200, exported.text
    book = read_workbook(exported.content, "export.xlsx")
    names = {row[1] for row in book[SHEET_PRODUCTS][1:] if len(row) > 1}
    assert "USB-C Cable" in names
    assert book[SHEET_META]


def test_reimport_does_not_duplicate_and_updates_by_id(client, session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    before = session.scalar(select(func.count()).select_from(Product))
    exported = client.get("/api/v1/catalogue/workbook/export", headers=bearer(token))
    first = _preview(client, token, exported.content)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] == 0
    assert body["failed"] == 0
    committed = _commit(client, token, exported.content, body["job_id"])
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == 0
    assert session.scalar(select(func.count()).select_from(Product)) == before
    sheets = read_workbook(exported.content, "export.xlsx")
    for row in sheets[SHEET_PRODUCTS][1:]:
        if row[0] == CABLE_ID:
            row[1] = "USB-C Cable Braided"
    payload = _pack(sheets)
    reviewed = _preview(client, token, payload, "update_only")
    assert reviewed.status_code == 200, reviewed.text
    saved = _commit(client, token, payload, reviewed.json()["job_id"], "update_only")
    assert saved.status_code == 200, saved.text
    assert saved.json()["updated"] == 1
    assert session.get(Product, uuid.UUID(CABLE_ID)).name == "USB-C Cable Braided"
    assert session.scalar(select(func.count()).select_from(Product)) == before


def test_restaurant_menu_import_keeps_portions_and_blank_sku(client, session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _switch(client, token, "restaurant")
    _category(client, token, "Mains")
    payload = _menu_book(client, token)
    reviewed = _preview(client, token, payload)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["created"] == 1
    assert reviewed.json()["pricing_created"] == 3
    assert reviewed.json()["failed"] == 0
    saved = _commit(client, token, payload, reviewed.json()["job_id"])
    assert saved.status_code == 200, saved.text
    item = session.scalar(select(Product).where(Product.name == "Daal Channa"))
    assert item is not None
    assert item.sku is None
    assert item.sell_without_recipe is True
    assert item.item_type == "MADE_TO_ORDER"
    again = client.get("/api/v1/catalogue/workbook/export", headers=bearer(token))
    second = _preview(client, token, again.content)
    assert second.json()["created"] == 0
    assert second.json()["pricing_created"] == 0
    assert second.json()["failed"] == 0
    replay = _commit(client, token, again.content, second.json()["job_id"])
    assert replay.status_code == 200, replay.text
    assert session.scalar(select(func.count()).select_from(Product).where(Product.name == "Daal Channa")) == 1


def test_invalid_rows_name_the_cell_and_write_nothing(client, session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _category(client, token, "Grocery")
    before = session.scalar(select(func.count()).select_from(Product))
    sheets = _template(client, token)
    sheets[SHEET_PRODUCTS].append(
        _line(
            PRODUCT_COLUMNS,
            **{
                "Product Name": "Rice 1kg",
                "SKU": "RICE-1",
                "Barcode": "281000000401",
                "Product Type": "PRE_PACKAGED",
                "Category": "Grocery",
                "Unit": "PIECE",
                "Base Price": "2.50",
                "Currency": "USD",
                "Tax Category": "STANDARD",
                "Price Includes Tax": "No",
                "Active": "Yes",
                "Open Price": "No",
                "Sold By Weight": "No",
                "Ingredient": "No",
                "Serialized": "No",
            },
        )
    )
    sheets[SHEET_PRODUCTS].append(
        _line(
            PRODUCT_COLUMNS,
            **{
                "Product Name": "Beans",
                "SKU": "RICE-1",
                "Barcode": "281000000402",
                "Product Type": "PRE_PACKAGED",
                "Category": "Grocery",
                "Unit": "PIECE",
                "Base Price": "1.00",
                "Currency": "USD",
                "Tax Category": "STANDARD",
                "Price Includes Tax": "No",
                "Active": "Yes",
                "Open Price": "No",
                "Sold By Weight": "No",
                "Ingredient": "No",
                "Serialized": "No",
            },
        )
    )
    sheets[SHEET_PRODUCTS].append(
        _line(
            PRODUCT_COLUMNS,
            **{
                "Product Name": "Missing",
                "SKU": "MISS-1",
                "Barcode": "281000000403",
                "Product Type": "PRE_PACKAGED",
                "Category": "Missing aisle",
                "Unit": "PIECE",
                "Base Price": "1.00",
                "Currency": "USD",
                "Tax Category": "STANDARD",
                "Price Includes Tax": "No",
                "Active": "Yes",
                "Open Price": "No",
                "Sold By Weight": "No",
                "Ingredient": "No",
                "Serialized": "No",
            },
        )
    )
    payload = _pack(sheets)
    reviewed = _preview(client, token, payload)
    assert reviewed.status_code == 200, reviewed.text
    errors = reviewed.json()["errors"]
    assert any(item["field"] == "Category" and item["row"] == 4 for item in errors)
    assert any(item["field"] == "SKU" and item["sheet"] == SHEET_PRODUCTS for item in errors)
    saved = _commit(client, token, payload, reviewed.json()["job_id"])
    assert saved.status_code == 422
    assert session.scalar(select(func.count()).select_from(Product)) == before
    report = client.post(
        "/api/v1/catalogue/workbook/error-report",
        headers=bearer(token),
        data={"mode": "upsert"},
        files={"file": ("book.xlsx", payload, MEDIA)},
    )
    assert report.status_code == 200
    assert read_workbook(report.content, "errors.xlsx")["Errors"][1][0]


def test_missing_parent_invalid_file_and_version_are_rejected(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _switch(client, token, "restaurant")
    sheets = _template(client, token)
    sheets[SHEET_OPTIONS].append(
        _line(OPTION_COLUMNS, **{"Option Name": "Small Plate", "Price": "3.00", "Currency": "USD", "Active": "Yes"})
    )
    reviewed = _preview(client, token, _pack(sheets))
    assert any(item["field"] == "Product ID" for item in reviewed.json()["errors"])
    refused = client.post(
        "/api/v1/catalogue/workbook/preview",
        headers=bearer(token),
        data={"mode": "upsert"},
        files={"file": ("notes.txt", b"not a workbook", "text/plain")},
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "unsupported_file"
    broken = _template(client, token)
    for row in broken[SHEET_META]:
        if row and row[0] == "format_version":
            row[1] = "99"
    version = _preview(client, token, _pack(broken))
    assert version.status_code == 422
    assert version.json()["error"]["code"] == "unsupported_workbook"


def test_formulas_are_rejected(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    original = client.get("/api/v1/catalogue/workbook/template", headers=bearer(token)).content
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(buffer, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.endswith("sheet2.xml"):
                payload = payload.replace(b"</sheetData>", b'<f>1+1</f></sheetData>')
            target.writestr(info.filename, payload)
    reviewed = _preview(client, token, buffer.getvalue())
    assert reviewed.status_code == 422
    assert reviewed.json()["error"]["code"] == "unsupported_file"


def test_cashier_cannot_import_or_export(client) -> None:
    seed_catalog(client)
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": CASHIER_PIN}, headers=device())
    assert cashier.status_code == 200, cashier.text
    token = cashier.json()["access_token"]
    exported = client.get("/api/v1/catalogue/workbook/export", headers=bearer(token))
    assert exported.status_code == 403
    preview = _preview(client, token, b"PK")
    assert preview.status_code == 403


def test_import_does_not_change_stock_and_retries_are_idempotent(client, session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _category(client, token, "Grocery")
    stock = session.scalar(select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)))
    movements = session.scalar(select(func.count()).select_from(StockMovement))
    sheets = _template(client, token)
    sheets[SHEET_PRODUCTS].append(
        _line(
            PRODUCT_COLUMNS,
            **{
                "Product Name": "Rice 1kg",
                "SKU": "RICE-1",
                "Barcode": "281000000401",
                "Product Type": "PRE_PACKAGED",
                "Category": "Grocery",
                "Unit": "PIECE",
                "Base Price": "2.50",
                "Currency": "USD",
                "Tax Category": "STANDARD",
                "Price Includes Tax": "No",
                "Active": "Yes",
                "Open Price": "No",
                "Sold By Weight": "No",
                "Ingredient": "No",
                "Serialized": "No",
            },
        )
    )
    payload = _pack(sheets)
    reviewed = _preview(client, token, payload)
    assert reviewed.json()["failed"] == 0, reviewed.text
    key = str(uuid.uuid4())
    saved = _commit(client, token, payload, reviewed.json()["job_id"], key=key)
    assert saved.status_code == 200, saved.text
    again = _commit(client, token, payload, reviewed.json()["job_id"], key=key)
    assert again.status_code == 200, again.text
    assert again.json()["replayed"] is True
    assert session.scalar(select(func.count()).select_from(Product).where(Product.sku == "RICE-1")) == 1
    assert session.scalar(select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0))) == stock
    assert session.scalar(select(func.count()).select_from(StockMovement)) == movements

