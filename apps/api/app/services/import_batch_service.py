"""Purchase import wizard and the batch hub.

Upload stores the original file and its parsed rows; preview maps them onto catalog fields and matches existing
products by SKU or barcode; commit creates the purchase batch, any new products, registers IMEIs, and books
PURCHASE_IN stock against the batch. Edits re-cost or re-price lines (re-costing past allocations so batch P&L
stays true), and quantity corrections only touch units that never left the batch.

Rollback reverses whatever is still on the shelf with PURCHASE_REVERSAL movements. A batch nothing was ever drawn
from is deleted outright; a batch with sales is kept, marked REVERSED, and its sold allocations stay as history."""

import json
import re
import secrets
import shutil
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.security import decrypt_value, encrypt_value
from app.models.batch import BatchAllocation, BatchItem, ImportMappingTemplate, PurchaseBatch, Supplier
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.batches import (
    REQUIRED_FIELDS,
    BatchDetail,
    BatchItemOut,
    BatchLedgerTotals,
    BatchPage,
    BatchRow,
    BatchSaleOut,
    BatchUpdate,
    CommitRequest,
    ImportOptions,
    ImportRow,
    PreviewOut,
    PreviewRequest,
    PreviewRow,
    PreviewTotals,
    RollbackConflict,
    RollbackPreview,
    RollbackRequest,
    RollbackResult,
    SupplierCreate,
    SupplierOut,
    TemplateOut,
    TemplateWrite,
    UploadOut,
)
from app.services import audit, barcodes, batch_ledger, category_service, import_parser, weighed
from app.services.identifiers import identifier_hash, identifier_suffix, normalize_identifier
from app.services.inventory import (
    _actor,
    _require_store_access,
    _scope,
    _store,
    find_serial,
    level_for,
    move_stock,
    portal_errors,
    transition_serial,
)
from app.services.settings_service import business_currency

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"
SALE_MOVEMENTS = frozenset({"SALE_OUT"})
MAX_DETAIL_SALES = 200
FIELD_LABELS = {
    "name": "Product name",
    "code": "SKU / barcode",
    "quantity": "Quantity",
    "cost": "Purchase cost",
    "price": "Selling price",
}


# --- Storage -------------------------------------------------------------------------------------


def _folder(name: str) -> Path:
    path = STORAGE_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_meta(upload_id: str) -> dict:
    if re.fullmatch(r"[0-9a-f]{32}", upload_id) is None:
        raise ApiError(422, "invalid_upload", "Upload id is invalid.")
    path = _folder("imports") / f"{upload_id}.json"
    if not path.exists():
        raise ApiError(404, "upload_expired", "The uploaded file was not found. Upload it again.")
    return json.loads(path.read_text(encoding="utf-8"))


def upload(principal: Principal, file_name: str, data: bytes) -> UploadOut:
    _actor(principal)
    name = Path(file_name or "purchases").name[:255] or "purchases"
    parsed = import_parser.parse(name, data)
    upload_id = uuid.uuid4().hex
    suffix = Path(name).suffix.lower()
    folder = _folder("imports")
    (folder / f"{upload_id}{suffix}").write_bytes(data)
    meta = {
        "file_name": name,
        "suffix": suffix,
        "source": parsed.source,
        "headers": parsed.headers,
        "rows": parsed.rows,
        "warnings": parsed.warnings,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    (folder / f"{upload_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    return UploadOut(
        upload_id=upload_id,
        file_name=name,
        import_source=parsed.source,  # type: ignore[arg-type]
        headers=parsed.headers,
        sample_rows=parsed.rows[:8],
        total_rows=len(parsed.rows),
        suggested_mapping=import_parser.suggest_mapping(parsed.headers),
        warnings=parsed.warnings,
    )


# --- Mapping and validation ----------------------------------------------------------------------


def _check_mapping(mapping: dict[str, str], headers: list[str], options: ImportOptions) -> None:
    required = [name for name in REQUIRED_FIELDS if not (name == "code" and options.auto_generate_codes)]
    missing = [FIELD_LABELS[name] for name in required if not mapping.get(name)]
    if missing:
        raise ApiError(422, "mapping_incomplete", f"Map a column for: {', '.join(missing)}.")
    unknown = sorted({header for header in mapping.values() if header and header not in headers})
    if unknown:
        raise ApiError(422, "mapping_unknown_column", f"Column not found in the file: {', '.join(unknown)}.")


def _map_rows(meta: dict, mapping: dict[str, str]) -> tuple[list[ImportRow], dict[int, list[str]]]:
    headers: list[str] = meta["headers"]
    index = {name: headers.index(header) for name, header in mapping.items() if header in headers}
    rows: list[ImportRow] = []
    problems: dict[int, list[str]] = defaultdict(list)
    for offset, raw in enumerate(meta["rows"]):
        number = offset + 1

        def value(name: str, raw: list[str] = raw) -> str:
            position = index.get(name)
            return raw[position].strip() if position is not None and position < len(raw) else ""

        def parsed(name: str, parser, label: str, number: int = number):  # type: ignore[no-untyped-def]
            text = value(name)
            try:
                return parser(text)
            except ValueError:
                problems[number].append(f"{label} “{text}” is not a valid value.")
                return None

        serials = import_parser.parse_serials(value("serials"))
        quantity = parsed("quantity", import_parser.parse_quantity, "Quantity")
        if quantity is None and serials and not value("quantity"):
            quantity = len(serials)
        rows.append(
            ImportRow(
                row_number=number,
                name=value("name")[:160],
                code=value("code")[:64],
                quantity=min(quantity, 1_000_000) if quantity is not None else None,
                cost_cents=parsed("cost", import_parser.parse_money, "Purchase cost"),
                price_cents=parsed("price", import_parser.parse_money, "Selling price"),
                model_number=value("model_number")[:80],
                category=value("category")[:80],
                sub_category=value("sub_category")[:80],
                serials=serials,
                expiry_date=parsed("expiry_date", import_parser.parse_date, "Expiry date"),
            )
        )
    return rows, problems


def _products_by_code(db: Session, codes: set[str]) -> dict[str, Product]:
    if not codes:
        return {}
    found: dict[str, Product] = {}
    rows = db.scalars(
        select(Product).where(or_(func.lower(Product.sku).in_(codes), func.lower(Product.barcode).in_(codes)))
    ).all()
    for product in rows:
        for code in (product.sku.lower(), product.barcode.lower()):
            if code in codes:
                found.setdefault(code, product)
    return found


def latest_costs(db: Session, product_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Most recent purchase cost per product: the newest live batch line, else the newest goods receipt."""
    if not product_ids:
        return {}
    costs: dict[uuid.UUID, int] = {}
    for product_id, cost in db.execute(
        select(BatchItem.product_id, BatchItem.purchase_cost_per_unit)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(BatchItem.product_id.in_(product_ids), PurchaseBatch.status != "REVERSED")
        .order_by(BatchItem.created_at.desc())
    ):
        costs.setdefault(product_id, cost)
    missing = product_ids - costs.keys()
    if missing:
        for product_id, cost in db.execute(
            select(GoodsReceiptLine.product_id, PurchaseOrderLine.unit_cost_cents)
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .join(PurchaseOrderLine, PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id)
            .where(GoodsReceiptLine.product_id.in_(missing))
            .order_by(GoodsReceipt.created_at.desc())
        ):
            costs.setdefault(product_id, cost)
    return costs


def _serial_kind(value: str) -> str:
    return "imei" if re.fullmatch(r"\d{15}", value.strip()) else "serial"


def _mask(value: str) -> str:
    return f"•••• {value[-4:]}" if len(value) > 4 else value


def _evaluate(
    db: Session,
    rows: list[ImportRow],
    options: ImportOptions,
    problems: dict[int, list[str]],
) -> list[PreviewRow]:
    codes = {row.code.strip().lower() for row in rows if row.code.strip()}
    products = _products_by_code(db, codes)
    costs = latest_costs(db, {product.id for product in products.values()})
    serial_rows: dict[str, int] = {}
    first_new: dict[str, int] = {}
    out: list[PreviewRow] = []
    for row in rows:
        errors = list(problems.get(row.row_number, []))
        warnings: list[str] = []
        code = row.code.strip()
        product = products.get(code.lower()) if code else None
        generated = not code and options.auto_generate_codes
        if not code and not generated:
            errors.append("SKU / barcode is missing. Map the column or turn on auto-generate.")

        serials: list[str] = []
        for raw in row.serials:
            kind = _serial_kind(raw)
            try:
                normalized = normalize_identifier(kind, raw)
            except SyncRejected as exc:
                errors.append(f"{_mask(raw)}: {exc.message}")
                continue
            if normalized in serial_rows and row.include:
                errors.append(f"{_mask(normalized)} is listed twice (row {serial_rows[normalized]}).")
                continue
            if row.include:
                serial_rows[normalized] = row.row_number
            existing = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == identifier_hash(normalized)))
            if existing is not None and existing.status != "reversed":
                errors.append(f"{_mask(normalized)} is already registered ({existing.status.replace('_', ' ')}).")
            serials.append(normalized)

        is_serialized = product.is_serialized if product is not None else bool(row.serials)
        if product is not None and product.is_serialized and not row.serials:
            errors.append(f"{product.name} tracks IMEIs: list one IMEI / serial per unit.")
        if product is not None and not product.is_serialized and row.serials:
            errors.append(f"{product.name} does not track IMEIs, but serials were listed.")
        if row.quantity is None or row.quantity < 1:
            if not any(error.startswith("Quantity") for error in errors):
                errors.append("Quantity must be at least 1.")
        elif row.serials and row.quantity != len(row.serials):
            errors.append(f"Quantity is {row.quantity} but {len(row.serials)} IMEIs / serials are listed.")
        if row.cost_cents is None and not any(error.startswith("Purchase cost") for error in errors):
            errors.append("Purchase cost is missing.")
        price = row.price_cents
        if price is None and not any(error.startswith("Selling price") for error in errors):
            if product is not None:
                price = product.price_cents
                warnings.append("Selling price is blank, so the current master price is used.")
            else:
                errors.append("Selling price is missing.")
        if product is None and not row.name.strip():
            errors.append("Product name is missing for a new product.")
        if price is not None and row.cost_cents is not None and price < row.cost_cents:
            warnings.append("Selling price is below the purchase cost.")
        if product is not None and row.name.strip() and row.name.strip().lower() != product.name.lower():
            warnings.append(f"Matched existing product “{product.name}” by its code.")
        if product is None and code and row.include:
            if code.lower() in first_new:
                warnings.append(f"Same new product as row {first_new[code.lower()]}.")
            else:
                first_new[code.lower()] = row.row_number

        out.append(
            PreviewRow(
                **{**row.model_dump(), "serials": serials or row.serials, "price_cents": price},
                status="ERROR" if errors else ("EXISTING" if product is not None else "NEW"),
                product_id=product.id if product is not None else None,
                existing_name=product.name if product is not None else None,
                existing_cost_cents=costs.get(product.id) if product is not None else None,
                existing_price_cents=product.price_cents if product is not None else None,
                is_serialized=is_serialized,
                generated_code=generated,
                errors=errors,
                warnings=warnings,
            )
        )
    return out


def _totals(rows: list[PreviewRow]) -> PreviewTotals:
    included = [row for row in rows if row.include]
    return PreviewTotals(
        rows=len(rows),
        included=len(included),
        new_products=sum(1 for row in included if row.status == "NEW"),
        existing_products=sum(1 for row in included if row.status == "EXISTING"),
        errors=sum(1 for row in included if row.status == "ERROR"),
        units=sum(row.quantity or 0 for row in included),
        cost_cents=sum((row.quantity or 0) * (row.cost_cents or 0) for row in included),
        retail_cents=sum((row.quantity or 0) * (row.price_cents or 0) for row in included),
    )


def preview(db: Session, principal: Principal, data: PreviewRequest) -> PreviewOut:
    _require_store_access(principal, data.store_id)
    _store(db, data.store_id)
    meta = _upload_meta(data.upload_id)
    _check_mapping(data.mapping, meta["headers"], data.options)
    if data.rows is not None:
        rows, problems = data.rows, {}
    else:
        rows, problems = _map_rows(meta, data.mapping)
    evaluated = _evaluate(db, rows, data.options, problems)
    return PreviewOut(
        upload_id=data.upload_id, currency=business_currency(db), rows=evaluated, totals=_totals(evaluated)
    )


# --- Commit --------------------------------------------------------------------------------------


def _batch_number(db: Session) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    prefix = f"BATCH-{stamp}-"
    count = db.scalar(select(func.count()).where(PurchaseBatch.batch_number.like(f"{prefix}%"))) or 0
    for sequence in range(count + 1, count + 50):
        candidate = f"{prefix}{sequence:03d}"
        if db.scalar(select(PurchaseBatch.id).where(PurchaseBatch.batch_number == candidate)) is None:
            return candidate
    raise ApiError(409, "conflict", "Could not allocate a batch number. Try again.")


def _code_taken(db: Session, code: str, reserved: set[str]) -> bool:
    lowered = code.lower()
    if lowered in reserved:
        return True
    clash = db.scalar(
        select(Product.id).where(or_(func.lower(Product.sku) == lowered, func.lower(Product.barcode) == lowered))
    )
    return clash is not None


def _generate_sku(db: Session, name: str, reserved: set[str]) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name.upper())[:3] or ["ITEM"]
    stem = "-".join(word[:4] for word in words)[:40]
    for _ in range(20):
        candidate = f"{stem}-{secrets.token_hex(2).upper()}"
        if not _code_taken(db, candidate, reserved):
            reserved.add(candidate.lower())
            return candidate
    raise ApiError(409, "conflict", "Could not generate a unique SKU. Try again.")


def _generate_barcode(db: Session, reserved: set[str]) -> str:
    return barcodes.in_store_ean13(db, reserved)


def _create_product(db: Session, row: PreviewRow, currency: str, reserved: set[str]) -> Product:
    code = row.code.strip()
    if code:
        sku = barcode = code
        reserved.add(code.lower())
    else:
        sku = _generate_sku(db, row.name, reserved)
        barcode = _generate_barcode(db, reserved)
    category, sub = category_service.resolve_by_name(
        db, row.category.strip() or "General", row.sub_category.strip() or None
    )
    product = Product(
        sku=sku,
        barcode=barcode,
        name=row.name.strip(),
        model_number=row.model_number.strip() or None,
        category=category.name,
        category_id=category.id,
        sub_category_id=sub.id if sub is not None else None,
        price_cents=row.price_cents or 0,
        currency=currency,
        is_serialized=bool(row.serials),
    )
    db.add(product)
    db.flush()
    return product


def _receive_serial(
    db: Session,
    settings: Settings,
    *,
    product: Product,
    item: BatchItem,
    batch: PurchaseBatch,
    value: str,
    user_id: uuid.UUID,
) -> SerialNumber:
    kind = _serial_kind(value)
    normalized, existing = find_serial(db, kind, value)
    if existing is None:
        serial = SerialNumber(
            product_id=product.id,
            store_id=item.store_id,
            kind=kind,
            value_hash=identifier_hash(normalized),
            value_encrypted=encrypt_value(normalized, settings),
            value_suffix=identifier_suffix(normalized),
            status="received",
            batch_item_id=item.id,
        )
        db.add(serial)
        db.flush()
    elif existing.status == "reversed":
        # A unit pulled back by a reversed import may be imported again, e.g. after correcting the invoice.
        serial = existing
        serial.product_id = product.id
        serial.kind = kind
        serial.batch_item_id = item.id
    else:
        raise SyncRejected(f"{_mask(normalized)} is already registered.")
    transition_serial(
        db,
        serial,
        status="in_stock",
        store_id=item.store_id,
        movement_type="PURCHASE_IN",
        reference_type="purchase_batch",
        reference_id=batch.id,
        user_id=user_id,
        note=batch.batch_number,
    )
    return serial


@portal_errors
def commit(db: Session, settings: Settings, principal: Principal, data: CommitRequest) -> BatchDetail:
    actor = _actor(principal)
    store_id = _scope(principal, data.store_id) or data.store_id
    store = _store(db, store_id)
    supplier = None
    if data.supplier_id is not None:
        supplier = db.get(Supplier, data.supplier_id)
        if supplier is None:
            raise ApiError(404, "not_found", "Supplier was not found.")
    if data.consignment and supplier is None:
        raise ApiError(422, "consignment_supplier", "Consignment stock belongs to a supplier: choose one.")
    meta = _upload_meta(data.upload_id)
    _check_mapping(data.mapping, meta["headers"], data.options)
    rows = [row for row in data.rows if row.include]
    if not rows:
        raise ApiError(422, "nothing_to_import", "Include at least one row to import.")
    evaluated = _evaluate(db, rows, data.options, {})
    invalid = [row for row in evaluated if row.errors]
    if invalid:
        numbers = ", ".join(str(row.row_number) for row in invalid[:10])
        raise ApiError(
            422,
            "import_rows_invalid",
            f"{len(invalid)} row(s) still have errors (rows {numbers}). Fix or exclude them, then commit again.",
            details={"rows": [{"row_number": row.row_number, "errors": row.errors} for row in invalid[:100]]},
        )

    currency = business_currency(db)
    batch = PurchaseBatch(
        id=uuid.uuid4(),
        batch_number=_batch_number(db),
        supplier_id=supplier.id if supplier is not None else None,
        store_id=store.id,
        import_source=meta["source"],
        file_name=meta["file_name"],
        mapping_template_used={
            "mapping": dict(data.mapping),
            "options": data.options.model_dump(),
            "template_name": data.save_template_as,
        },
        total_cost_amount=0,
        total_items_count=0,
        currency=currency,
        status="ACTIVE",
        is_consignment=data.consignment,
        notes=data.notes.strip(),
        created_by_id=actor.id,
    )
    db.add(batch)
    db.flush()

    created: dict[str, Product] = {}
    reserved: set[str] = set()
    new_products = master_updates = 0
    for position, row in enumerate(evaluated):
        product = db.get(Product, row.product_id) if row.product_id is not None else None
        if product is None and row.code.strip():
            product = created.get(row.code.strip().lower())
        if product is None:
            product = _create_product(db, row, currency, reserved)
            new_products += 1
            if row.code.strip():
                created[row.code.strip().lower()] = product
        elif (
            row.product_id is not None
            and data.options.update_master_price
            and row.price_cents is not None
            and product.price_cents != row.price_cents
        ):
            product.price_cents = row.price_cents
            master_updates += 1
        quantity = row.quantity or 0
        item = BatchItem(
            id=uuid.uuid4(),
            batch_id=batch.id,
            position=position,
            product_id=product.id,
            store_id=store.id,
            quantity_imported=quantity,
            quantity_remaining=quantity,
            purchase_cost_per_unit=row.cost_cents or 0,
            selling_price_per_unit=row.price_cents if row.price_cents is not None else product.price_cents,
            expiry_date=row.expiry_date,
            imported_serials=[],
            source_row=row.row_number,
        )
        db.add(item)
        db.flush()
        if product.is_serialized:
            item.imported_serials = [
                str(
                    _receive_serial(
                        db, settings, product=product, item=item, batch=batch, value=value, user_id=actor.id
                    ).id
                )
                for value in row.serials
            ]
        else:
            move_stock(
                db,
                product_id=product.id,
                store_id=store.id,
                quantity=quantity,
                movement_type="PURCHASE_IN",
                reference_type="purchase_batch",
                reference_id=batch.id,
                user_id=actor.id,
                note=f"{batch.batch_number} · row {row.row_number}",
            )
        batch.total_items_count += quantity
        batch.total_cost_amount += quantity * item.purchase_cost_per_unit

    batch.file_url = f"/api/v1/inventory/batches/{batch.id}/file"
    if data.save_template_as:
        _save_template(
            db,
            actor,
            TemplateWrite(
                name=data.save_template_as,
                supplier_id=batch.supplier_id,
                mapping=data.mapping,
                options=data.options,
            ),
        )
    audit.record(
        db,
        action_type="CREATE",
        action="inventory.batch_import",
        target_entity="PurchaseBatch",
        target_entity_id=batch.id,
        user=actor,
        store_id=store.id,
        new_values={
            "batch_number": batch.batch_number,
            "store": store.code,
            "supplier": supplier.name if supplier is not None else None,
            "import_source": batch.import_source,
            "file_name": batch.file_name,
            "lines": len(evaluated),
            "units": batch.total_items_count,
            "total_cost_cents": batch.total_cost_amount,
        },
        details={
            "new_products": new_products,
            "existing_products": len(evaluated) - new_products,
            "master_prices_updated": master_updates,
            "update_master_price": data.options.update_master_price,
        },
    )
    db.commit()

    folder = _folder("imports")
    original = folder / f"{data.upload_id}{meta['suffix']}"
    if original.exists():
        shutil.move(str(original), str(_folder("batches") / f"{batch.id}{meta['suffix']}"))
    (folder / f"{data.upload_id}.json").unlink(missing_ok=True)
    return get_batch(db, settings, principal, batch.id)


# --- Economics -----------------------------------------------------------------------------------


@dataclass
class ItemEconomics:
    sold: int = 0
    removed: int = 0
    revenue: int = 0
    cogs: int = 0
    sales: list[tuple[BatchAllocation, SaleItem | None]] = field(default_factory=list)


def _economics(db: Session, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, ItemEconomics]:
    """Per batch item: units sold and otherwise removed (net of returns), revenue at the sale price, and COGS."""
    if not batch_ids:
        return {}
    out: dict[uuid.UUID, ItemEconomics] = defaultdict(ItemEconomics)
    rows = db.execute(
        select(BatchAllocation, SaleItem, BatchItem.selling_price_per_unit, Product.sold_by_weight)
        .join(BatchItem, BatchItem.id == BatchAllocation.batch_item_id)
        .join(Product, Product.id == BatchItem.product_id)
        .outerjoin(SaleItem, SaleItem.id == BatchAllocation.sale_item_id)
        .where(BatchItem.batch_id.in_(batch_ids))
    ).all()
    for allocation, sale_item, list_price, sold_by_weight in rows:
        net = allocation.quantity - allocation.quantity_returned
        economics = out[allocation.batch_item_id]
        if allocation.movement_type in SALE_MOVEMENTS:
            unit_sale = sale_item.unit_price_cents if sale_item is not None else list_price
            scale = weighed.GRAMS_PER_KG if sold_by_weight else 1
            economics.sold += net
            economics.revenue += weighed.amount(net, unit_sale, scale)
            economics.cogs += weighed.amount(net, allocation.unit_cost_cents, scale)
            economics.sales.append((allocation, sale_item))
        else:
            economics.removed += net
    return out


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {value for value in ids if value is not None}
    if not wanted:
        return {}
    return {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(wanted))).unique().all()}


def _row(
    batch: PurchaseBatch,
    store: Store,
    supplier: Supplier | None,
    economics: dict[uuid.UUID, ItemEconomics],
    creator: str | None,
) -> BatchRow:
    items = batch.items
    sold = sum(economics[item.id].sold for item in items if item.id in economics)
    revenue = sum(economics[item.id].revenue for item in items if item.id in economics)
    cogs = sum(economics[item.id].cogs for item in items if item.id in economics)
    total = batch.total_items_count
    return BatchRow(
        id=batch.id,
        batch_number=batch.batch_number,
        store_id=store.id,
        store_code=store.code,
        store_name=store.name,
        supplier_id=batch.supplier_id,
        supplier_name=supplier.name if supplier is not None else None,
        import_source=batch.import_source,  # type: ignore[arg-type]
        file_name=batch.file_name,
        status=batch.status,  # type: ignore[arg-type]
        currency=batch.currency,
        line_count=len(items),
        total_items_count=total,
        total_cost_amount=batch.total_cost_amount,
        units_remaining=sum(item.quantity_remaining for item in items),
        units_sold=sold,
        sold_percent=round(sold * 100 / total, 1) if total else 0.0,
        revenue_cents=revenue,
        realized_profit_cents=revenue - cogs,
        created_by_name=creator,
        created_at=batch.created_at,
        is_consignment=batch.is_consignment,
    )


def _filtered(
    principal: Principal,
    *,
    store_id: uuid.UUID | None,
    status: str | None,
    supplier_id: uuid.UUID | None,
    query: str | None,
):  # type: ignore[no-untyped-def]
    statement = select(PurchaseBatch)
    scope = _scope(principal, store_id)
    if scope is not None:
        statement = statement.where(PurchaseBatch.store_id == scope)
    if status:
        statement = statement.where(PurchaseBatch.status == status)
    if supplier_id is not None:
        statement = statement.where(PurchaseBatch.supplier_id == supplier_id)
    if query and query.strip():
        like = f"%{query.strip().lower()}%"
        statement = statement.where(
            or_(func.lower(PurchaseBatch.batch_number).like(like), func.lower(PurchaseBatch.file_name).like(like))
        )
    return statement


def list_batches(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID | None = None,
    status: str | None = None,
    supplier_id: uuid.UUID | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> BatchPage:
    statement = _filtered(principal, store_id=store_id, status=status, supplier_id=supplier_id, query=query)
    every = list(db.scalars(statement.order_by(PurchaseBatch.created_at.desc(), PurchaseBatch.id)).all())
    page = every[offset : offset + limit]
    economics = _economics(db, [batch.id for batch in every])
    stores = {store.id: store for store in db.scalars(select(Store)).all()}
    suppliers = {supplier.id: supplier for supplier in db.scalars(select(Supplier)).all()}
    names = _names(db, {batch.created_by_id for batch in page})
    rows = [
        _row(
            batch,
            stores[batch.store_id],
            suppliers.get(batch.supplier_id) if batch.supplier_id else None,
            economics,
            names.get(batch.created_by_id),
        )
        for batch in page
    ]
    profit = sum(value.revenue - value.cogs for value in economics.values())
    return BatchPage(
        rows=rows,
        total=len(every),
        totals=BatchLedgerTotals(
            batches=len(every),
            units=sum(batch.total_items_count for batch in every),
            cost_cents=sum(batch.total_cost_amount for batch in every),
            remaining_cost_cents=sum(
                item.quantity_remaining * item.purchase_cost_per_unit for batch in every for item in batch.items
            ),
            realized_profit_cents=profit,
        ),
    )


def _batch(db: Session, principal: Principal, batch_id: uuid.UUID) -> PurchaseBatch:
    batch = db.get(PurchaseBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "Purchase batch was not found.")
    _require_store_access(principal, batch.store_id)
    return batch


def get_batch(db: Session, settings: Settings, principal: Principal, batch_id: uuid.UUID) -> BatchDetail:
    batch = _batch(db, principal, batch_id)
    db.refresh(batch)
    store = db.get(Store, batch.store_id)
    supplier = db.get(Supplier, batch.supplier_id) if batch.supplier_id else None
    economics = _economics(db, [batch.id])
    names = _names(db, {batch.created_by_id, batch.reversed_by_id})
    base = _row(batch, store, supplier, economics, names.get(batch.created_by_id))  # type: ignore[arg-type]
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in batch.items})))
    }
    serials_by_item: dict[uuid.UUID, list[SerialNumber]] = defaultdict(list)
    for serial in db.scalars(
        select(SerialNumber).where(SerialNumber.batch_item_id.in_([item.id for item in batch.items]))
    ):
        serials_by_item[serial.batch_item_id].append(serial)  # type: ignore[index]

    items: list[BatchItemOut] = []
    sales: list[BatchSaleOut] = []
    sale_times: dict[uuid.UUID, datetime] = {}
    sale_ids = {
        sale_item.sale_id for value in economics.values() for _, sale_item in value.sales if sale_item is not None
    }
    if sale_ids:
        sale_times = dict(db.execute(select(Sale.id, Sale.created_at).where(Sale.id.in_(sale_ids))).all())
    for item in batch.items:
        product = products[item.product_id]
        value = economics.get(item.id, ItemEconomics())
        units = serials_by_item.get(item.id, [])
        items.append(
            BatchItemOut(
                id=item.id,
                position=item.position,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                is_serialized=product.is_serialized,
                quantity_imported=item.quantity_imported,
                quantity_remaining=item.quantity_remaining,
                quantity_sold=value.sold,
                quantity_removed=value.removed,
                purchase_cost_per_unit=item.purchase_cost_per_unit,
                selling_price_per_unit=item.selling_price_per_unit,
                master_price_cents=product.price_cents,
                expiry_date=item.expiry_date,
                serial_count=len(item.imported_serials or []),
                serials_last4=[decrypt_value(serial.value_encrypted, settings)[-4:] for serial in units[:24]],
                revenue_cents=value.revenue,
                cogs_cents=value.cogs,
                realized_profit_cents=value.revenue - value.cogs,
                editable_quantity=not product.is_serialized and batch.status != "REVERSED",
            )
        )
        for allocation, sale_item in value.sales:
            if sale_item is None or len(sales) >= MAX_DETAIL_SALES:
                continue
            net = allocation.quantity - allocation.quantity_returned
            sales.append(
                BatchSaleOut(
                    sale_id=sale_item.sale_id,
                    sale_item_id=sale_item.id,
                    product_name=product.name,
                    quantity=allocation.quantity,
                    returned=allocation.quantity_returned,
                    unit_cost_cents=allocation.unit_cost_cents,
                    unit_sale_cents=sale_item.unit_price_cents,
                    profit_cents=(sale_item.unit_price_cents - allocation.unit_cost_cents) * net,
                    sold_at=sale_times.get(sale_item.sale_id, allocation.created_at),
                )
            )
    sales.sort(key=lambda row: row.sold_at, reverse=True)
    return BatchDetail(
        **base.model_dump(),
        notes=batch.notes,
        mapping_template_used=batch.mapping_template_used,
        file_url=batch.file_url,
        reversal_reason=batch.reversal_reason,
        reversed_at=batch.reversed_at,
        reversed_by_name=names.get(batch.reversed_by_id) if batch.reversed_by_id else None,
        cogs_cents=sum(value.cogs for value in economics.values()),
        items=items,
        sales=sales,
    )


def batch_file(db: Session, principal: Principal, batch_id: uuid.UUID) -> tuple[Path, str]:
    batch = _batch(db, principal, batch_id)
    suffix = Path(batch.file_name or "").suffix.lower()
    path = _folder("batches") / f"{batch.id}{suffix}"
    if not batch.file_name or not path.exists():
        raise ApiError(404, "not_found", "The original import file is not available.")
    return path, batch.file_name


# --- Editing -------------------------------------------------------------------------------------


@portal_errors
def update_batch(
    db: Session, settings: Settings, principal: Principal, batch_id: uuid.UUID, data: BatchUpdate
) -> BatchDetail:
    actor = _actor(principal)
    batch = _batch(db, principal, batch_id)
    if batch.status == "REVERSED":
        raise ApiError(409, "batch_locked", "Reversed batches are locked and cannot be edited.")
    old: dict[str, object] = {}
    new: dict[str, object] = {}
    if data.clear_supplier and batch.supplier_id is not None:
        old["supplier_id"], new["supplier_id"] = str(batch.supplier_id), None
        batch.supplier_id = None
    elif data.supplier_id is not None and data.supplier_id != batch.supplier_id:
        if db.get(Supplier, data.supplier_id) is None:
            raise ApiError(404, "not_found", "Supplier was not found.")
        old["supplier_id"] = str(batch.supplier_id) if batch.supplier_id else None
        new["supplier_id"] = str(data.supplier_id)
        batch.supplier_id = data.supplier_id
    if data.notes is not None and data.notes.strip() != batch.notes:
        old["notes"], new["notes"] = batch.notes, data.notes.strip()
        batch.notes = data.notes.strip()

    items = {item.id: item for item in batch.items}
    changes: list[dict[str, object]] = []
    for change in data.items:
        item = items.get(change.id)
        if item is None:
            raise ApiError(404, "not_found", "A batch line in the update does not belong to this batch.")
        product = db.get(Product, item.product_id)
        assert product is not None
        before = {
            "cost": item.purchase_cost_per_unit,
            "price": item.selling_price_per_unit,
            "quantity": item.quantity_imported,
            "expiry": item.expiry_date.isoformat() if item.expiry_date else None,
        }
        if change.purchase_cost_per_unit is not None and change.purchase_cost_per_unit != item.purchase_cost_per_unit:
            item.purchase_cost_per_unit = change.purchase_cost_per_unit
            for allocation in db.scalars(select(BatchAllocation).where(BatchAllocation.batch_item_id == item.id)):
                allocation.unit_cost_cents = change.purchase_cost_per_unit
        if change.selling_price_per_unit is not None and change.selling_price_per_unit != item.selling_price_per_unit:
            item.selling_price_per_unit = change.selling_price_per_unit
            if data.apply_price_to_master:
                product.price_cents = change.selling_price_per_unit
        if change.quantity_imported is not None and change.quantity_imported != item.quantity_imported:
            _correct_quantity(db, batch, item, product, change.quantity_imported, actor.id)
        if change.clear_expiry:
            item.expiry_date = None
        elif change.expiry_date is not None:
            item.expiry_date = change.expiry_date
        after = {
            "cost": item.purchase_cost_per_unit,
            "price": item.selling_price_per_unit,
            "quantity": item.quantity_imported,
            "expiry": item.expiry_date.isoformat() if item.expiry_date else None,
        }
        if after != before:
            changes.append({"line": item.position + 1, "product": product.name, "before": before, "after": after})

    if not changes and not new:
        return get_batch(db, settings, principal, batch.id)
    db.flush()
    batch.total_items_count = sum(item.quantity_imported for item in batch.items)
    batch.total_cost_amount = sum(item.quantity_imported * item.purchase_cost_per_unit for item in batch.items)
    batch_ledger.refresh_status(db, {batch.id})
    if changes:
        old["lines"] = [{"line": row["line"], **row["before"]} for row in changes]  # type: ignore[dict-item]
        new["lines"] = [{"line": row["line"], **row["after"]} for row in changes]  # type: ignore[dict-item]
    audit.record(
        db,
        action_type="UPDATE",
        action="inventory.batch_update",
        target_entity="PurchaseBatch",
        target_entity_id=batch.id,
        user=actor,
        store_id=batch.store_id,
        old_values=old,
        new_values=new,
        details={
            "batch_number": batch.batch_number,
            "lines_changed": len(changes),
            "apply_price_to_master": data.apply_price_to_master,
        },
        reason_notes=(data.reason or "").strip() or None,
    )
    db.commit()
    return get_batch(db, settings, principal, batch.id)


def _correct_quantity(
    db: Session, batch: PurchaseBatch, item: BatchItem, product: Product, quantity: int, user_id: uuid.UUID
) -> None:
    if product.is_serialized:
        raise ApiError(
            422, "serialized_quantity", f"{product.name} tracks IMEIs. Roll back and re-import to change units."
        )
    consumed = item.quantity_imported - item.quantity_remaining
    if quantity < consumed:
        raise ApiError(
            422,
            "quantity_below_consumed",
            f"{consumed} unit(s) of {product.name} already left this batch, so it cannot go below {consumed}.",
        )
    delta = quantity - item.quantity_imported
    note = f"{batch.batch_number} · quantity correction"
    if delta > 0:
        move_stock(
            db,
            product_id=product.id,
            store_id=item.store_id,
            quantity=delta,
            movement_type="PURCHASE_IN",
            reference_type="purchase_batch",
            reference_id=batch.id,
            user_id=user_id,
            note=note,
        )
    else:
        move_stock(
            db,
            product_id=product.id,
            store_id=item.store_id,
            quantity=delta,
            movement_type="PURCHASE_REVERSAL",
            reference_type="purchase_batch",
            reference_id=batch.id,
            user_id=user_id,
            note=note,
            allocate_batches=False,
        )
    item.quantity_imported += delta
    item.quantity_remaining += delta


# --- Rollback ------------------------------------------------------------------------------------


@dataclass
class _Plan:
    item: BatchItem
    product: Product
    sold: int
    removed: int
    serials: list[SerialNumber]
    reversible: int

    @property
    def blocked(self) -> int:
        return self.item.quantity_remaining - self.reversible


def _plan(db: Session, batch: PurchaseBatch) -> tuple[list[_Plan], bool]:
    economics = _economics(db, [batch.id])
    plans: list[_Plan] = []
    for item in batch.items:
        product = db.get(Product, item.product_id)
        assert product is not None
        value = economics.get(item.id, ItemEconomics())
        serials: list[SerialNumber] = []
        if product.is_serialized:
            serials = list(
                db.scalars(
                    select(SerialNumber).where(
                        SerialNumber.batch_item_id == item.id,
                        SerialNumber.status == "in_stock",
                        SerialNumber.store_id == item.store_id,
                    )
                ).all()
            )
            reversible = min(len(serials), item.quantity_remaining)
            serials = serials[:reversible]
        else:
            available = level_for(db, product.id, item.store_id).available
            reversible = max(0, min(item.quantity_remaining, available))
        plans.append(
            _Plan(
                item=item,
                product=product,
                sold=value.sold,
                removed=value.removed,
                serials=serials,
                reversible=reversible,
            )
        )
    untouched = not db.scalar(
        select(func.count())
        .select_from(BatchAllocation)
        .join(BatchItem, BatchItem.id == BatchAllocation.batch_item_id)
        .where(BatchItem.batch_id == batch.id)
    )
    return plans, untouched


def _conflict_text(plan: _Plan) -> str:
    parts = []
    if plan.sold:
        parts.append(f"{plan.sold} sold, kept as history")
    if plan.removed:
        parts.append(f"{plan.removed} already moved out (transfers or write-offs)")
    if plan.blocked:
        what = (
            "not in stock (repair, reserved or defective)" if plan.product.is_serialized else "reserved for transfers"
        )
        parts.append(f"{plan.blocked} {what}, left on hand")
    return "; ".join(parts)


def rollback_preview(db: Session, principal: Principal, batch_id: uuid.UUID) -> RollbackPreview:
    batch = _batch(db, principal, batch_id)
    plans, untouched = _plan(db, batch)
    return RollbackPreview(
        batch_id=batch.id,
        batch_number=batch.batch_number,
        mode="DELETE" if untouched else "REVERSE",
        units_to_remove=sum(plan.reversible for plan in plans),
        units_sold=sum(plan.sold for plan in plans),
        units_blocked=sum(plan.blocked for plan in plans),
        cost_written_back_cents=sum(plan.reversible * plan.item.purchase_cost_per_unit for plan in plans),
        conflicts=[
            RollbackConflict(
                product_name=plan.product.name,
                sku=plan.product.sku,
                imported=plan.item.quantity_imported,
                sold=plan.sold,
                removed=plan.removed,
                remaining=plan.item.quantity_remaining,
                reversible=plan.reversible,
                blocked=plan.blocked,
                detail=_conflict_text(plan),
            )
            for plan in plans
            if plan.sold or plan.removed or plan.blocked
        ],
        can_rollback=batch.status != "REVERSED",
    )


@portal_errors
def rollback(
    db: Session, settings: Settings, principal: Principal, batch_id: uuid.UUID, data: RollbackRequest
) -> RollbackResult:
    actor = _actor(principal)
    reason = audit.require_reason(data.reason, "a batch rollback")
    batch = _batch(db, principal, batch_id)
    if batch.status == "REVERSED":
        raise ApiError(409, "batch_locked", "This batch has already been reversed.")
    plans, untouched = _plan(db, batch)
    note = f"{batch.batch_number} rollback: {reason}"
    removed = 0
    for plan in plans:
        if plan.product.is_serialized:
            for serial in plan.serials:
                transition_serial(
                    db,
                    serial,
                    status="reversed",
                    store_id=serial.store_id,
                    movement_type="PURCHASE_REVERSAL",
                    reference_type="purchase_batch",
                    reference_id=batch.id,
                    user_id=actor.id,
                    note=note,
                )
                removed += 1
        elif plan.reversible:
            move_stock(
                db,
                product_id=plan.product.id,
                store_id=plan.item.store_id,
                quantity=-plan.reversible,
                movement_type="PURCHASE_REVERSAL",
                reference_type="purchase_batch",
                reference_id=batch.id,
                user_id=actor.id,
                note=note,
                batch_item_id=plan.item.id,
            )
            removed += plan.reversible
        plan.item.quantity_remaining = 0

    snapshot = {
        "batch_number": batch.batch_number,
        "status": batch.status,
        "units": batch.total_items_count,
        "total_cost_cents": batch.total_cost_amount,
        "lines": len(plans),
    }
    details = {
        "units_removed": removed,
        "units_sold": sum(plan.sold for plan in plans),
        "units_left_on_hand": sum(plan.blocked for plan in plans),
        "products": [plan.product.sku for plan in plans],
    }
    number, store_id = batch.batch_number, batch.store_id
    if untouched:
        item_ids = [plan.item.id for plan in plans]
        for serial in db.scalars(select(SerialNumber).where(SerialNumber.batch_item_id.in_(item_ids))):
            serial.batch_item_id = None
        db.execute(delete(BatchAllocation).where(BatchAllocation.batch_item_id.in_(item_ids)))
        db.flush()
        db.delete(batch)
        mode, status = "DELETE", "DELETED"
        audit.record(
            db,
            action_type="DELETE",
            action="inventory.batch_rollback",
            target_entity="PurchaseBatch",
            target_entity_id=batch_id,
            user=actor,
            store_id=store_id,
            old_values=snapshot,
            details={**details, "mode": "DELETE"},
            reason_notes=reason,
        )
    else:
        batch.status = "REVERSED"
        batch.reversal_reason = reason
        batch.reversed_at = datetime.now(UTC)
        batch.reversed_by_id = actor.id
        mode, status = "REVERSE", "REVERSED"
        audit.record(
            db,
            action_type="UPDATE",
            action="inventory.batch_rollback",
            target_entity="PurchaseBatch",
            target_entity_id=batch.id,
            user=actor,
            store_id=store_id,
            old_values=snapshot,
            new_values={"status": "REVERSED"},
            details={**details, "mode": "REVERSE"},
            reason_notes=reason,
        )
    suffix = Path(batch.file_name or "").suffix.lower()
    db.commit()
    if untouched:
        (_folder("batches") / f"{batch_id}{suffix}").unlink(missing_ok=True)
    return RollbackResult(batch_id=batch_id, batch_number=number, mode=mode, units_removed=removed, status=status)  # type: ignore[arg-type]


# --- Suppliers and templates ---------------------------------------------------------------------


def list_suppliers(db: Session) -> list[SupplierOut]:
    counts = dict(
        db.execute(
            select(PurchaseBatch.supplier_id, func.count())
            .where(PurchaseBatch.supplier_id.is_not(None))
            .group_by(PurchaseBatch.supplier_id)
        ).all()
    )
    return [
        SupplierOut(
            id=supplier.id,
            name=supplier.name,
            code=supplier.code,
            contact_name=supplier.contact_name,
            phone=supplier.phone,
            email=supplier.email,
            is_active=supplier.is_active,
            batch_count=counts.get(supplier.id, 0),
        )
        for supplier in db.scalars(select(Supplier).order_by(Supplier.name)).all()
    ]


@portal_errors
def create_supplier(db: Session, data: SupplierCreate) -> SupplierOut:
    name = " ".join(data.name.split())
    if db.scalar(select(Supplier.id).where(func.lower(Supplier.name) == name.lower())) is not None:
        raise ApiError(409, "conflict", "A supplier with this name already exists.")
    base = "-".join(re.findall(r"[A-Za-z0-9]+", name.upper()))[:24] or "SUP"
    code, suffix = base, 2
    while db.scalar(select(Supplier.id).where(Supplier.code == code)) is not None:
        code = f"{base[:24]}-{suffix}"
        suffix += 1
    supplier = Supplier(
        name=name,
        code=code,
        contact_name=(data.contact_name or "").strip() or None,
        phone=(data.phone or "").strip() or None,
        email=(data.email or "").strip() or None,
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    return next(row for row in list_suppliers(db) if row.id == supplier.id)


def _template_out(template: ImportMappingTemplate, suppliers: dict[uuid.UUID, str]) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        supplier_id=template.supplier_id,
        supplier_name=suppliers.get(template.supplier_id) if template.supplier_id else None,
        mapping=template.mapping,
        options=ImportOptions.model_validate(template.options or {}),
        updated_at=template.updated_at,
    )


def list_templates(db: Session, supplier_id: uuid.UUID | None) -> list[TemplateOut]:
    statement = select(ImportMappingTemplate)
    if supplier_id is not None:
        statement = statement.where(
            or_(ImportMappingTemplate.supplier_id == supplier_id, ImportMappingTemplate.supplier_id.is_(None))
        )
    suppliers = dict(db.execute(select(Supplier.id, Supplier.name)).all())
    rows = db.scalars(statement.order_by(ImportMappingTemplate.name)).all()
    rows = sorted(rows, key=lambda row: (row.supplier_id is None, row.name.lower()))
    return [_template_out(row, suppliers) for row in rows]


def _save_template(db: Session, actor: User, data: TemplateWrite) -> ImportMappingTemplate:
    name = " ".join(data.name.split())
    mapping = {key: value for key, value in data.mapping.items() if value}
    if not mapping:
        raise ApiError(422, "mapping_incomplete", "A template needs at least one mapped column.")
    if data.supplier_id is not None and db.get(Supplier, data.supplier_id) is None:
        raise ApiError(404, "not_found", "Supplier was not found.")
    owner = (
        ImportMappingTemplate.supplier_id.is_(None)
        if data.supplier_id is None
        else ImportMappingTemplate.supplier_id == data.supplier_id
    )
    template = db.scalar(
        select(ImportMappingTemplate).where(owner, func.lower(ImportMappingTemplate.name) == name.lower())
    )
    if template is None:
        template = ImportMappingTemplate(name=name, supplier_id=data.supplier_id, created_by_id=actor.id)
        db.add(template)
    template.mapping = mapping
    template.options = data.options.model_dump()
    db.flush()
    return template


@portal_errors
def save_template(db: Session, principal: Principal, data: TemplateWrite) -> TemplateOut:
    template = _save_template(db, _actor(principal), data)
    db.commit()
    db.refresh(template)
    return _template_out(template, dict(db.execute(select(Supplier.id, Supplier.name)).all()))


@portal_errors
def delete_template(db: Session, template_id: uuid.UUID) -> None:
    template = db.get(ImportMappingTemplate, template_id)
    if template is None:
        raise ApiError(404, "not_found", "Template was not found.")
    db.delete(template)
    db.commit()
