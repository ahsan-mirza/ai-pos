"""Expiry-first stock (FEFO): what is about to expire, writing off what already has, and the daily alert."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch
from app.models.inventory import StockMovement
from app.models.product import Product
from app.models.store import Store
from app.schemas.expiry import (
    ExpiringRow,
    ExpiryWriteOff,
    ExpiryWriteOffOut,
    WasteHistoryRow,
    WasteOut,
    WasteSource,
    WasteWrite,
)
from app.services import audit
from app.services.batch_ledger import today
from app.services.inventory import DAMAGE_REASONS, MANUAL_REFERENCE, WASTE_REASONS, level_for, move_stock, portal_errors
from app.services.settings_service import cached_settings


def _rows(db: Session, *, store_id: uuid.UUID | None, days: int) -> list[ExpiringRow]:
    day = today()
    horizon = day + timedelta(days=days)
    statement = (
        select(BatchItem, PurchaseBatch, Product, Store)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .join(Product, Product.id == BatchItem.product_id)
        .join(Store, Store.id == BatchItem.store_id)
        .where(
            BatchItem.quantity_remaining > 0,
            BatchItem.expiry_date.is_not(None),
            BatchItem.expiry_date <= horizon,
            PurchaseBatch.status != "REVERSED",
        )
        .order_by(BatchItem.expiry_date, Product.name)
    )
    if store_id is not None:
        statement = statement.where(BatchItem.store_id == store_id)
    rows: list[ExpiringRow] = []
    for item, batch, product, store in db.execute(statement).all():
        expiry = item.expiry_date
        assert expiry is not None
        rows.append(
            ExpiringRow(
                batch_item_id=item.id,
                batch_number=batch.batch_number,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                store_id=store.id,
                store_code=store.code,
                expiry_date=expiry,
                days_left=(expiry - day).days,
                quantity_remaining=item.quantity_remaining,
                unit_cost_cents=item.purchase_cost_per_unit,
                value_cents=item.quantity_remaining * item.purchase_cost_per_unit,
                expired=expiry < day,
            )
        )
    return rows


def expiring(db: Session, principal: Principal, *, store_id: uuid.UUID | None, days: int | None) -> list[ExpiringRow]:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only see your own store's stock.")
        store_id = principal.store_id
    window = days if days is not None else cached_settings(db).module_settings.fefo.alert_days
    return _rows(db, store_id=store_id, days=window)


@portal_errors
def write_off(db: Session, principal: Principal, data: ExpiryWriteOff) -> ExpiryWriteOffOut:
    """Takes an expired batch line's remaining units out of stock (DAMAGE_SHRINKAGE, reason DAMAGED_OR_EXPIRED)."""
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    item = db.get(BatchItem, data.batch_item_id)
    if item is None:
        raise ApiError(404, "not_found", "Batch line was not found.")
    if principal.store_id is not None and item.store_id != principal.store_id:
        raise ApiError(403, "store_scope", "You can only write off your own store's stock.")
    product = db.get(Product, item.product_id)
    assert product is not None
    if product.is_serialized:
        raise ApiError(422, "serialized", "Write serialized units off one by one from Stock adjustments.")
    if item.expiry_date is None or item.expiry_date >= today():
        raise ApiError(422, "not_expired", "Only batches past their expiry date can be written off here.")
    quantity = min(data.quantity or item.quantity_remaining, item.quantity_remaining)
    if quantity <= 0:
        raise ApiError(422, "nothing_left", "This batch line has no units left.")
    level = level_for(db, product.id, item.store_id)
    before = level.quantity_on_hand
    adjustment_id = uuid.uuid4()
    move_stock(
        db,
        product_id=product.id,
        store_id=item.store_id,
        quantity=-min(quantity, level.quantity_on_hand),
        movement_type="DAMAGE_SHRINKAGE",
        reference_type=MANUAL_REFERENCE,
        reference_id=adjustment_id,
        user_id=principal.user.id,
        reason_code="DAMAGED_OR_EXPIRED",
        note=data.note or f"Expired {item.expiry_date.isoformat()}",
        batch_item_id=item.id,
    )
    audit.log_stock_adjustment(
        db,
        level_id=level.id,
        product_id=product.id,
        store_id=item.store_id,
        quantity_before=before,
        quantity_after=level.quantity_on_hand,
        reason="DAMAGED_OR_EXPIRED",
        details={"batch_item_id": str(item.id), "expiry_date": item.expiry_date.isoformat(), "fefo_write_off": True},
    )
    db.commit()
    return ExpiryWriteOffOut(
        batch_item_id=item.id, written_off=before - level.quantity_on_hand, quantity_remaining=item.quantity_remaining
    )


def _waste_result(db: Session, item: BatchItem, adjustment_id: uuid.UUID, *, duplicate: bool) -> WasteOut:
    movement = db.scalar(
        select(StockMovement).where(
            StockMovement.reference_type == MANUAL_REFERENCE,
            StockMovement.reference_id == adjustment_id,
        )
    )
    written = abs(movement.quantity) if movement is not None else 0
    return WasteOut(
        adjustment_id=adjustment_id,
        batch_item_id=item.id,
        written_off=written,
        quantity_remaining=item.quantity_remaining,
        duplicate=duplicate,
    )


@portal_errors
def record_waste(db: Session, principal: Principal, data: WasteWrite) -> WasteOut:
    """Removes units from one batch through the stock ledger. Replaying adjustment_id does not deduct again."""
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    if not has_capability(db, Capability.FEFO):
        raise ApiError(403, "module_off", "Expiry-first stock is turned off.")
    item = db.get(BatchItem, data.batch_item_id)
    if item is None:
        raise ApiError(404, "not_found", "Batch line was not found.")
    if principal.store_id is not None and item.store_id != principal.store_id:
        raise ApiError(403, "store_scope", "You can only write off your own store's stock.")
    product = db.get(Product, item.product_id)
    assert product is not None
    if product.is_serialized:
        raise ApiError(422, "serialized", "Write serialized units off one by one from Stock adjustments.")
    existing = db.scalar(
        select(StockMovement).where(
            StockMovement.reference_type == MANUAL_REFERENCE,
            StockMovement.reference_id == data.adjustment_id,
        )
    )
    if existing is not None:
        return _waste_result(db, item, data.adjustment_id, duplicate=True)
    if data.quantity > item.quantity_remaining:
        raise ApiError(422, "nothing_left", "This batch line does not have that many units left.")
    level = level_for(db, product.id, item.store_id)
    before = level.quantity_on_hand
    move_stock(
        db,
        product_id=product.id,
        store_id=item.store_id,
        quantity=-data.quantity,
        movement_type="DAMAGE_SHRINKAGE" if data.reason_code in DAMAGE_REASONS else "AUDIT_ADJUSTMENT",
        reference_type=MANUAL_REFERENCE,
        reference_id=data.adjustment_id,
        user_id=principal.user.id,
        reason_code=data.reason_code,
        note=data.note or data.reason_code.replace("_", " ").title(),
        batch_item_id=item.id,
    )
    audit.log_stock_adjustment(
        db,
        level_id=level.id,
        product_id=product.id,
        store_id=item.store_id,
        quantity_before=before,
        quantity_after=level.quantity_on_hand,
        reason=data.reason_code,
        details={"batch_item_id": str(item.id), "produce_waste": True},
    )
    db.commit()
    return _waste_result(db, item, data.adjustment_id, duplicate=False)


def waste_sources(db: Session, principal: Principal, *, store_id: uuid.UUID | None) -> list[WasteSource]:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only see your own store's stock.")
        store_id = principal.store_id
    statement = (
        select(BatchItem, PurchaseBatch, Product)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .join(Product, Product.id == BatchItem.product_id)
        .where(BatchItem.quantity_remaining > 0, PurchaseBatch.status != "REVERSED")
        .order_by(Product.name, BatchItem.expiry_date)
        .limit(200)
    )
    if store_id is not None:
        statement = statement.where(BatchItem.store_id == store_id)
    return [
        WasteSource(
            batch_item_id=item.id,
            batch_number=batch.batch_number,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            store_id=item.store_id,
            quantity_remaining=item.quantity_remaining,
            expiry_date=item.expiry_date,
        )
        for item, batch, product in db.execute(statement).all()
    ]


def waste_history(db: Session, principal: Principal, *, store_id: uuid.UUID | None) -> list[WasteHistoryRow]:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only see your own store's stock.")
        store_id = principal.store_id
    statement = (
        select(StockMovement, Product)
        .join(Product, Product.id == StockMovement.product_id)
        .where(StockMovement.reason_code.in_(WASTE_REASONS), StockMovement.quantity < 0)
        .order_by(StockMovement.created_at.desc())
        .limit(50)
    )
    if store_id is not None:
        statement = statement.where(StockMovement.store_id == store_id)
    return [
        WasteHistoryRow(
            id=movement.id,
            adjustment_id=movement.reference_id,
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            store_id=movement.store_id,
            quantity=abs(movement.quantity),
            reason_code=movement.reason_code or "",
            note=movement.note,
            created_at=movement.created_at,
        )
        for movement, product in db.execute(statement).all()
    ]


def run_alert(db: Session) -> str:
    """Daily summary of expired and soon-to-expire stock, recorded for the audit trail and the Expiring stock page."""
    if not has_capability(db, Capability.FEFO):
        return "FEFO is off"
    rows = _rows(db, store_id=None, days=cached_settings(db).module_settings.fefo.alert_days)
    if not rows:
        return "nothing expiring"
    expired = [row for row in rows if row.expired]
    audit.record(
        db,
        action_type="UPDATE",
        action="inventory.expiry_alert",
        target_entity="Inventory",
        client_device="system",
        details={
            "expired_lines": len(expired),
            "expired_units": sum(row.quantity_remaining for row in expired),
            "expiring_lines": len(rows) - len(expired),
            "value_cents": sum(row.value_cents for row in rows),
        },
    )
    db.commit()
    return f"{len(expired)} expired, {len(rows) - len(expired)} expiring batch lines"
