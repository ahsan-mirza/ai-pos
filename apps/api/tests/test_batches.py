import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_returns import (
    CABLE_ID,
    STORE_ID,
    admin_id,
    admin_token,
    approval,
    bearer,
    imei,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)

from app.models import AuditLog, BatchAllocation, BatchItem, InventoryLevel, PurchaseBatch, SaleItem, SerialNumber
from app.services import barcodes, import_batch_service, import_parser

MAPPING = {"name": "Product Name", "code": "SKU", "quantity": "Qty", "cost": "Unit Cost", "price": "Retail Price"}


@pytest.fixture(autouse=True)
def import_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(import_batch_service, "STORAGE_ROOT", tmp_path)


def on_hand(session: Session, product_id: str) -> int:
    session.expire_all()
    level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(product_id), InventoryLevel.store_id == uuid.UUID(STORE_ID)
        )
    )
    return level.quantity_on_hand if level is not None else 0


def upload(client, token: str, body: str, name: str = "invoice.csv") -> dict:
    response = client.post(
        "/api/v1/inventory/import/upload",
        headers=bearer(token),
        files={"file": (name, body.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def import_csv(
    client,
    token: str,
    body: str,
    *,
    mapping: dict | None = None,
    options: dict | None = None,
    extra: dict | None = None,
) -> dict:
    uploaded = upload(client, token, body)
    request = {
        "upload_id": uploaded["upload_id"],
        "store_id": STORE_ID,
        "mapping": mapping or MAPPING,
        "options": options or {},
    }
    preview = client.post("/api/v1/inventory/import/preview", headers=bearer(token), json=request)
    assert preview.status_code == 200, preview.text
    rows = [
        {
            key: row[key]
            for key in (
                "row_number",
                "include",
                "name",
                "code",
                "quantity",
                "cost_cents",
                "price_cents",
                "model_number",
                "category",
                "sub_category",
                "serials",
                "expiry_date",
            )
        }
        for row in preview.json()["rows"]
    ]
    committed = client.post(
        "/api/v1/inventory/import/commit", headers=bearer(token), json={**request, **(extra or {}), "rows": rows}
    )
    assert committed.status_code == 201, committed.text
    return committed.json()


def cable_batch(client, token: str, quantity: int, cost: str) -> dict:
    return import_csv(
        client,
        token,
        f"Product Name,SKU,Qty,Unit Cost,Retail Price\nUSB-C Cable,ACC-CABLE-USBC,{quantity},{cost},15.00\n",
    )


def test_upload_detects_header_and_preview_marks_new_and_existing(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    first = cable_batch(client, token, 2, "5.00")
    body = (
        "Supplier invoice INV-77\n"
        "Product Name,SKU,Qty,Unit Cost,Retail Price\n"
        'USB-C Cable,acc-cable-usbc,5,"AED 5.80",15.00\n'
        'Galaxy Buds,NEW-BUDS-1,3,"1,200.50",1500\n'
        "Mystery,,1,1,\n"
    )
    uploaded = upload(client, token, body)
    assert uploaded["headers"] == ["Product Name", "SKU", "Qty", "Unit Cost", "Retail Price"]
    assert uploaded["total_rows"] == 3
    assert uploaded["suggested_mapping"] == MAPPING
    assert "Skipped 1 line(s) above the header row." in uploaded["warnings"]

    response = client.post(
        "/api/v1/inventory/import/preview",
        headers=bearer(token),
        json={"upload_id": uploaded["upload_id"], "store_id": STORE_ID, "mapping": MAPPING},
    )
    assert response.status_code == 200, response.text
    existing, new, broken = response.json()["rows"]
    assert existing["status"] == "EXISTING"
    assert existing["product_id"] == CABLE_ID
    assert (existing["existing_cost_cents"], existing["cost_cents"]) == (500, 580)
    assert new["status"] == "NEW" and new["cost_cents"] == 120050 and new["price_cents"] == 150000
    assert broken["status"] == "ERROR"
    assert any("SKU / barcode is missing" in error for error in broken["errors"])
    assert any("Selling price is missing" in error for error in broken["errors"])
    assert first["batch_number"].startswith("BATCH-") and first["batch_number"].endswith("-001")


def test_commit_rejects_rows_with_errors(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    uploaded = upload(client, token, "Product Name,SKU,Qty,Unit Cost,Retail Price\nThing,T-1,0,1,2\n")
    request = {"upload_id": uploaded["upload_id"], "store_id": STORE_ID, "mapping": MAPPING}
    rows = [{"row_number": 1, "name": "Thing", "code": "T-1", "quantity": 0, "cost_cents": 100, "price_cents": 200}]
    response = client.post("/api/v1/inventory/import/commit", headers=bearer(token), json={**request, "rows": rows})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_rows_invalid"


def test_fifo_sales_draw_oldest_batch_and_book_profit(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    start = on_hand(session, CABLE_ID)
    older = cable_batch(client, token, 5, "5.00")
    newer = cable_batch(client, token, 5, "7.00")
    assert on_hand(session, CABLE_ID) == start + 10

    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=7)
    session.expire_all()
    item = session.get(SaleItem, uuid.UUID(sale["items"][0]["id"]))
    allocations = session.scalars(select(BatchAllocation).where(BatchAllocation.sale_item_id == item.id)).all()
    assert sorted((a.quantity, a.unit_cost_cents) for a in allocations) == [(2, 700), (5, 500)]
    assert item.batch_item_id == uuid.UUID(older["items"][0]["id"])

    first = client.get(f"/api/v1/inventory/batches/{older['id']}", headers=bearer(token)).json()
    second = client.get(f"/api/v1/inventory/batches/{newer['id']}", headers=bearer(token)).json()
    assert (first["status"], first["units_remaining"], first["sold_percent"]) == ("EXHAUSTED", 0, 100.0)
    assert first["realized_profit_cents"] == (1500 - 500) * 5
    assert (second["status"], second["units_remaining"]) == ("PARTIALLY_SOLD", 3)
    assert second["realized_profit_cents"] == (1500 - 700) * 2

    ledger = client.get("/api/v1/inventory/batches", headers=bearer(token)).json()
    assert ledger["total"] == 2
    assert ledger["totals"]["realized_profit_cents"] == 5000 + 1600

    body = receipt(client, sale["id"])
    returned = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert returned.status_code == 200, returned.text
    second = client.get(f"/api/v1/inventory/batches/{newer['id']}", headers=bearer(token)).json()
    assert second["units_remaining"] == 4
    assert second["units_sold"] == 1


def test_cost_correction_recosts_sold_units_and_quantity_respects_consumed(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    batch = cable_batch(client, token, 4, "5.00")
    record_sale(client, product_id=CABLE_ID, price=1500, quantity=3)
    line = batch["items"][0]["id"]

    corrected = client.patch(
        f"/api/v1/inventory/batches/{batch['id']}",
        headers=bearer(token),
        json={
            "items": [{"id": line, "purchase_cost_per_unit": 600, "selling_price_per_unit": 1700}],
            "apply_price_to_master": True,
            "reason": "Supplier credit note",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["realized_profit_cents"] == (1500 - 600) * 3
    assert corrected.json()["total_cost_amount"] == 2400
    assert corrected.json()["items"][0]["master_price_cents"] == 1700

    too_low = client.patch(
        f"/api/v1/inventory/batches/{batch['id']}",
        headers=bearer(token),
        json={"items": [{"id": line, "quantity_imported": 2}]},
    )
    assert too_low.status_code == 422
    assert too_low.json()["error"]["code"] == "quantity_below_consumed"

    grown = client.patch(
        f"/api/v1/inventory/batches/{batch['id']}",
        headers=bearer(token),
        json={"items": [{"id": line, "quantity_imported": 6}]},
    )
    assert grown.status_code == 200, grown.text
    assert (grown.json()["total_items_count"], grown.json()["units_remaining"]) == (6, 3)


def test_rollback_of_untouched_batch_deletes_it(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    start = on_hand(session, CABLE_ID)
    batch = cable_batch(client, token, 4, "5.00")

    preview = client.get(f"/api/v1/inventory/batches/{batch['id']}/rollback-preview", headers=bearer(token)).json()
    assert (preview["mode"], preview["units_to_remove"], preview["conflicts"]) == ("DELETE", 4, [])

    missing = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/rollback", headers=bearer(token), json={"reason": ""}
    )
    assert missing.status_code == 422
    done = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/rollback", headers=bearer(token), json={"reason": "Wrong invoice"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "DELETED"
    assert on_hand(session, CABLE_ID) == start
    assert session.get(PurchaseBatch, uuid.UUID(batch["id"])) is None
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "inventory.batch_rollback"))
    assert entry is not None and entry.action_type == "DELETE" and entry.reason_notes == "Wrong invoice"


def test_rollback_after_sales_reverses_remaining_and_locks(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    start = on_hand(session, CABLE_ID)
    batch = cable_batch(client, token, 5, "5.00")
    record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)

    preview = client.get(f"/api/v1/inventory/batches/{batch['id']}/rollback-preview", headers=bearer(token)).json()
    assert preview["mode"] == "REVERSE"
    assert (preview["units_to_remove"], preview["units_sold"]) == (3, 2)
    assert preview["conflicts"][0]["sold"] == 2

    done = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/rollback", headers=bearer(token), json={"reason": "Supplier recall"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "REVERSED"
    assert on_hand(session, CABLE_ID) == start
    detail = client.get(f"/api/v1/inventory/batches/{batch['id']}", headers=bearer(token)).json()
    assert (
        detail["status"] == "REVERSED" and detail["units_sold"] == 2 and detail["reversal_reason"] == "Supplier recall"
    )
    locked = client.patch(f"/api/v1/inventory/batches/{batch['id']}", headers=bearer(token), json={"notes": "x"})
    assert locked.status_code == 409


def test_serialized_import_tracks_imeis_per_batch_and_can_be_reimported(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    units = [imei("35693803564380"), imei("49015420323751"), imei("35209900176148")]
    mapping = {**MAPPING, "serials": "IMEI", "category": "Category"}
    body = (
        "Product Name,SKU,Qty,Unit Cost,Retail Price,Category,IMEI\n"
        f'Nova Phone,NOVA-1,3,900,1200,Phones,"{units[0]} {units[1]}, {units[2]}"\n'
    )
    batch = import_csv(client, token, body, mapping=mapping)
    product_id = batch["items"][0]["product_id"]
    assert batch["items"][0]["is_serialized"] is True
    assert batch["items"][0]["serial_count"] == 3
    serials = session.scalars(select(SerialNumber).where(SerialNumber.product_id == uuid.UUID(product_id))).all()
    assert {serial.batch_item_id for serial in serials} == {uuid.UUID(batch["items"][0]["id"])}
    assert on_hand(session, product_id) == 3

    sale = record_sale(client, product_id=product_id, price=120000, serial=units[0])
    assert sale
    item = session.scalars(select(BatchItem).where(BatchItem.id == uuid.UUID(batch["items"][0]["id"]))).one()
    session.refresh(item)
    assert item.quantity_remaining == 2

    done = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/rollback", headers=bearer(token), json={"reason": "Wrong model"}
    )
    assert done.json()["units_removed"] == 2
    assert on_hand(session, product_id) == 0
    statuses = sorted(serial.status for serial in session.scalars(select(SerialNumber)).all())
    assert statuses == ["reversed", "reversed", "sold"]

    again = import_csv(
        client,
        token,
        f"Product Name,SKU,Qty,Unit Cost,Retail Price,IMEI\nNova Phone,NOVA-1,2,900,1200,{units[1]};{units[2]}\n",
        mapping={**MAPPING, "serials": "IMEI"},
    )
    assert again["items"][0]["quantity_remaining"] == 2
    assert on_hand(session, product_id) == 2


def test_auto_generated_codes_and_supplier_templates(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    supplier = client.post("/api/v1/inventory/suppliers", headers=bearer(token), json={"name": "Gulf Mobile Trading"})
    assert supplier.status_code == 201, supplier.text
    supplier_id = supplier.json()["id"]

    mapping = {"name": "Item", "quantity": "Qty", "cost": "Cost", "price": "Retail"}
    uploaded = upload(client, token, "Item,Qty,Cost,Retail\nScreen Guard,10,2,9\n")
    request = {
        "upload_id": uploaded["upload_id"],
        "store_id": STORE_ID,
        "supplier_id": supplier_id,
        "mapping": mapping,
        "options": {"auto_generate_codes": True},
        "save_template_as": "Gulf invoice",
        "rows": [
            {"row_number": 1, "name": "Screen Guard", "code": "", "quantity": 10, "cost_cents": 200, "price_cents": 900}
        ],
    }
    committed = client.post("/api/v1/inventory/import/commit", headers=bearer(token), json=request)
    assert committed.status_code == 201, committed.text
    line = committed.json()["items"][0]
    assert line["sku"].startswith("SCRE-GUAR-")
    assert line["barcode"].startswith("200") and len(line["barcode"]) == 13
    assert committed.json()["supplier_name"] == "Gulf Mobile Trading"

    templates = client.get(
        "/api/v1/inventory/import/templates", headers=bearer(token), params={"supplier_id": supplier_id}
    ).json()
    assert [(row["name"], row["mapping"]["name"], row["options"]["auto_generate_codes"]) for row in templates] == [
        ("Gulf invoice", "Item", True)
    ]
    original = client.get(f"/api/v1/inventory/batches/{committed.json()['id']}/file", headers=bearer(token))
    assert original.status_code == 200 and original.content.startswith(b"Item,Qty")


def test_cashier_cannot_import(client) -> None:
    seed_catalog(client)
    response = client.post("/api/v1/inventory/import/upload", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert response.status_code == 401


def test_value_parsing_rules() -> None:
    assert import_parser.parse_money("AED 1,234.50") == 123450
    assert import_parser.parse_money("1.234,50") == 123450
    assert import_parser.parse_money("58") == 5800
    assert import_parser.parse_money("12,5") == 1250
    assert import_parser.parse_money("") is None
    with pytest.raises(ValueError):
        import_parser.parse_quantity("2.5")
    assert import_parser.parse_serials("a, b;c  d|e") == ["a", "b", "c", "d", "e"]
    assert barcodes.ean13("200000000000")[-1].isdigit()
    with pytest.raises(Exception, match="Upload an Excel"):
        import_parser.source_for("photo.png")
