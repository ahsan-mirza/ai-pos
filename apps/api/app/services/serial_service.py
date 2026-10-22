"""One serial/IMEI search for the whole app: checkout pickers, global search, warranty, repairs and stock audit.

Values are encrypted at rest, so a search matches either a full identifier exactly (by hash) or the last few
characters (`value_suffix`). Registers and stock managers see full values; everyone else sees the last four, and
purchase cost is shown only to portal users who manage inventory or read reports."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.core.security import decrypt_value
from app.models.batch import BatchItem, PurchaseBatch
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.schemas.serials import SerialSearchOut, SerialSearchRow
from app.services.identifiers import SUFFIX_LENGTH, identifier_hash, identifier_suffix, is_valid_imei

BACKFILL_BATCH = 2_000
MIN_SUFFIX = 3


@dataclass(frozen=True)
class Visibility:
    reveal: bool
    cost: bool


def visibility(principal: Principal) -> Visibility:
    if principal.kind == "device" or principal.scope == "pos":
        return Visibility(reveal=True, cost=False)
    stock = principal.has(Permission.PORTAL_INVENTORY_MANAGE) or principal.has(Permission.INVENTORY_ADJUST_STOCK)
    reports = principal.has(Permission.PORTAL_REPORTS_READ)
    return Visibility(reveal=stock, cost=stock or reports)


def _exact_hashes(query: str) -> list[str]:
    cleaned = query.strip()
    if is_valid_imei(cleaned):
        return [identifier_hash(cleaned)]
    if re.fullmatch(r"[A-Za-z0-9-]{4,64}", cleaned):
        return [identifier_hash(cleaned.upper()), identifier_hash(cleaned)]
    return []


def backfill_suffixes(db: Session, settings: Settings, limit: int = BACKFILL_BATCH) -> int:
    """Rows written before value_suffix existed get it filled in, a batch at a time."""
    rows = list(db.scalars(select(SerialNumber).where(SerialNumber.value_suffix.is_(None)).limit(limit)))
    for row in rows:
        row.value_suffix = identifier_suffix(decrypt_value(row.value_encrypted, settings))
    if rows:
        db.commit()
    return len(rows)


def held_by_quotes():  # type: ignore[no-untyped-def]
    return (
        select(SaleItem.serial_number_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.quote_status == "OPEN", SaleItem.serial_number_id.is_not(None))
    )


def search(
    db: Session,
    settings: Settings,
    principal: Principal,
    *,
    query: str | None,
    product_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    status: str | None,
    limit: int,
) -> SerialSearchOut:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only search your own branch.")
        store_id = principal.store_id
    statement = select(SerialNumber)
    if product_id is not None:
        statement = statement.where(SerialNumber.product_id == product_id)
    if store_id is not None:
        statement = statement.where(SerialNumber.store_id == store_id)
    if status is not None:
        statement = statement.where(SerialNumber.status == status)
        if status == "in_stock":
            statement = statement.where(SerialNumber.id.not_in(held_by_quotes()))

    needle = (query or "").strip()
    match = "all"
    if needle:
        hashes = _exact_hashes(needle)
        if hashes and len(needle) > SUFFIX_LENGTH:
            match = "exact"
            statement = statement.where(SerialNumber.value_hash.in_(hashes))
        elif MIN_SUFFIX <= len(needle) <= SUFFIX_LENGTH and re.fullmatch(r"[A-Za-z0-9-]+", needle):
            match = "suffix"
            backfill_suffixes(db, settings)
            statement = statement.where(SerialNumber.value_suffix.like(f"%{needle.upper()}"))
        else:
            return SerialSearchOut(
                match="none",
                rows=[],
                hint=f"Scan the full IMEI or serial, or type its last {MIN_SUFFIX}–{SUFFIX_LENGTH} characters.",
            )

    units = list(
        db.scalars(statement.order_by(SerialNumber.created_at, SerialNumber.id).limit(min(max(limit, 1), 500)))
    )
    seen = visibility(principal)
    products = {
        row.id: row for row in db.scalars(select(Product).where(Product.id.in_({unit.product_id for unit in units})))
    }
    stores = {row.id: row.code for row in db.scalars(select(Store).where(Store.id.in_({u.store_id for u in units})))}
    batches = {
        item_id: (number, cost)
        for item_id, number, cost in db.execute(
            select(BatchItem.id, PurchaseBatch.batch_number, BatchItem.purchase_cost_per_unit)
            .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
            .where(BatchItem.id.in_({unit.batch_item_id for unit in units if unit.batch_item_id}))
        )
    }
    rows = []
    for unit in units:
        value = decrypt_value(unit.value_encrypted, settings)
        product = products.get(unit.product_id)
        batch = batches.get(unit.batch_item_id) if unit.batch_item_id else None
        rows.append(
            SerialSearchRow(
                id=unit.id,
                product_id=unit.product_id,
                product_name=product.name if product else None,
                sku=product.sku if product else None,
                store_id=unit.store_id,
                store_code=stores.get(unit.store_id, ""),
                kind=unit.kind,  # type: ignore[arg-type]
                value=value if seen.reveal else f"•••• {value[-4:]}",
                last4=value[-4:],
                status=unit.status,
                batch_number=batch[0] if batch else None,
                purchase_cost_cents=batch[1] if batch and seen.cost else None,
                created_at=unit.created_at,
                updated_at=unit.updated_at,
            )
        )
    hint = None
    if match == "exact" and not rows:
        hint = f"No unit has exactly '{needle}'. Type its last {MIN_SUFFIX}–{SUFFIX_LENGTH} characters to search."
    return SerialSearchOut(match=match, rows=rows, hint=hint)
