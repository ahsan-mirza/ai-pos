"""FIFO bookkeeping between the stock ledger and purchase batches. move_stock calls on_movement for every
movement, so each unit that leaves a branch is drawn from a batch and each unit that comes back is restored to
the batch it left. Batches are consumed oldest first; stock with no batch (opening balances, goods receipts,
transfers in) is only used once every open batch at that branch is empty, which keeps
sum(batch remaining) <= quantity_on_hand at all times.

Serialized units are tied to their own batch line, so selling an IMEI never draws down a different batch.

With the FEFO module on, open batches are drawn by expiry instead: soonest expiry first, undated batches after,
and expired batches only once nothing fresher is left (an offline register may already have sold them)."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.inventory import StockMovement
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber

SKIP_RESTORE = frozenset({"PURCHASE_IN"})


def _locked(db: Session, statement):  # type: ignore[no-untyped-def]
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return statement


def today() -> date:
    return datetime.now(UTC).date()


def is_expired(item: BatchItem, on: date | None = None) -> bool:
    return item.expiry_date is not None and item.expiry_date < (on or today())


def fefo_order(items: list[BatchItem], on: date | None = None) -> list[BatchItem]:
    """Fresh batches by soonest expiry, then undated ones, then expired ones; FIFO breaks ties (sort is stable)."""
    day = on or today()

    def key(item: BatchItem) -> tuple[int, date]:
        if item.expiry_date is None:
            return (1, date.max)
        return (2 if item.expiry_date < day else 0, item.expiry_date)

    return sorted(items, key=key)


def open_items(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, *, lock: bool = False) -> list[BatchItem]:
    """Open batch lines at a branch in the order sales draw from them."""
    statement = (
        select(BatchItem)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(
            BatchItem.product_id == product_id,
            BatchItem.store_id == store_id,
            BatchItem.quantity_remaining > 0,
            PurchaseBatch.status != "REVERSED",
        )
        .order_by(BatchItem.created_at, BatchItem.position, BatchItem.id)
    )
    items = list(db.scalars(_locked(db, statement) if lock else statement).all())
    return fefo_order(items) if has_capability(db, Capability.FEFO) else items


def _open_items(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> list[BatchItem]:
    return open_items(db, product_id, store_id, lock=True)


def refresh_status(db: Session, batch_ids: set[uuid.UUID]) -> None:
    for batch_id in batch_ids:
        batch = db.get(PurchaseBatch, batch_id)
        if batch is None or batch.status == "REVERSED":
            continue
        imported = sum(item.quantity_imported for item in batch.items)
        remaining = sum(item.quantity_remaining for item in batch.items)
        if remaining <= 0:
            batch.status = "EXHAUSTED"
        elif remaining >= imported:
            batch.status = "ACTIVE"
        else:
            batch.status = "PARTIALLY_SOLD"


def _draw(db: Session, movement: StockMovement, item: BatchItem, quantity: int) -> int:
    taken = min(quantity, item.quantity_remaining)
    if taken <= 0:
        return 0
    item.quantity_remaining -= taken
    db.add(
        BatchAllocation(
            batch_item_id=item.id,
            stock_movement_id=movement.id,
            movement_type=movement.movement_type,
            quantity=taken,
            unit_cost_cents=item.purchase_cost_per_unit,
            expired=is_expired(item),
        )
    )
    return taken


def _flag_expired_sale(db: Session, movement: StockMovement, drawn: list[tuple[BatchItem, int]]) -> None:
    expired = [(item, quantity) for item, quantity in drawn if is_expired(item)]
    if not expired or movement.movement_type != "SALE_OUT":
        return
    from app.services import audit

    audit.record(
        db,
        action_type="EXPIRED_STOCK_SOLD",
        action="inventory.expired_sold",
        target_entity="Product",
        target_entity_id=movement.product_id,
        store_id=movement.store_id,
        client_device="system",
        details={
            "quantity": sum(quantity for _, quantity in expired),
            "batch_items": [
                {"id": str(item.id), "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None}
                for item, _ in expired
            ],
            "reference_id": str(movement.reference_id) if movement.reference_id else None,
        },
    )


def _consume(db: Session, movement: StockMovement, batch_item_id: uuid.UUID | None) -> set[uuid.UUID]:
    needed = -movement.quantity
    touched: set[uuid.UUID] = set()
    if movement.serial_number_id is not None:
        serial = db.get(SerialNumber, movement.serial_number_id)
        target = batch_item_id or (serial.batch_item_id if serial is not None else None)
        item = db.get(BatchItem, target) if target is not None else None
        if item is not None and item.store_id == movement.store_id:
            taken = _draw(db, movement, item, needed)
            if taken:
                touched.add(item.batch_id)
                _flag_expired_sale(db, movement, [(item, taken)])
        return touched
    candidates = _open_items(db, movement.product_id, movement.store_id)
    if batch_item_id is not None:
        candidates.sort(key=lambda row: row.id != batch_item_id)
    drawn: list[tuple[BatchItem, int]] = []
    for item in candidates:
        if needed <= 0:
            break
        taken = _draw(db, movement, item, needed)
        if taken:
            needed -= taken
            touched.add(item.batch_id)
            drawn.append((item, taken))
    _flag_expired_sale(db, movement, drawn)
    return touched


def _restore_serial(db: Session, movement: StockMovement) -> set[uuid.UUID]:
    """A serialized unit coming back to the branch its batch line lives at goes back into that line."""
    serial = db.get(SerialNumber, movement.serial_number_id)
    if serial is None or serial.batch_item_id is None:
        return set()
    item = db.get(BatchItem, serial.batch_item_id)
    if item is None or item.store_id != movement.store_id or item.quantity_remaining >= item.quantity_imported:
        return set()
    batch = db.get(PurchaseBatch, item.batch_id)
    if batch is None or batch.status == "REVERSED":
        return set()
    allocation = db.scalar(
        select(BatchAllocation)
        .join(StockMovement, StockMovement.id == BatchAllocation.stock_movement_id)
        .where(
            BatchAllocation.batch_item_id == item.id,
            StockMovement.serial_number_id == serial.id,
            BatchAllocation.quantity_returned < BatchAllocation.quantity,
        )
        .order_by(BatchAllocation.created_at.desc())
    )
    if allocation is None:
        return set()
    allocation.quantity_returned += 1
    item.quantity_remaining += 1
    return {item.batch_id}


def on_movement(
    db: Session,
    movement: StockMovement,
    *,
    batch_item_id: uuid.UUID | None = None,
    allocate: bool = True,
) -> None:
    if not allocate:
        return
    if movement.quantity < 0:
        touched = _consume(db, movement, batch_item_id)
    elif movement.serial_number_id is not None and movement.movement_type not in SKIP_RESTORE:
        touched = _restore_serial(db, movement)
    else:
        touched = set()
    if touched:
        db.flush()
        refresh_status(db, touched)
        db.flush()


def link_sale(db: Session, sale_id: uuid.UUID) -> None:
    """Hands each sale line the allocations its stock movements made, splitting allocations across lines."""
    rows = db.execute(
        select(BatchAllocation, StockMovement)
        .join(StockMovement, StockMovement.id == BatchAllocation.stock_movement_id)
        .where(
            StockMovement.reference_type == "sale",
            StockMovement.reference_id == sale_id,
            BatchAllocation.sale_item_id.is_(None),
        )
        .order_by(BatchAllocation.created_at, BatchAllocation.id)
    ).all()
    if not rows:
        return
    items = list(db.scalars(select(SaleItem).where(SaleItem.sale_id == sale_id).order_by(SaleItem.id)).all())
    by_serial = {item.serial_number_id: item for item in items if item.serial_number_id is not None}
    open_lines: dict[uuid.UUID, list[list]] = defaultdict(list)  # product -> [[item, units still unlinked]]
    for item in items:
        if item.serial_number_id is None:
            open_lines[item.product_id].append([item, item.quantity])

    for allocation, movement in rows:
        if movement.serial_number_id is not None:
            item = by_serial.get(movement.serial_number_id)
            if item is not None:
                allocation.sale_item_id = item.id
                item.batch_item_id = item.batch_item_id or allocation.batch_item_id
            continue
        left = allocation.quantity
        current = allocation
        for slot in open_lines[movement.product_id]:
            if left <= 0:
                break
            item, unlinked = slot
            if unlinked <= 0:
                continue
            share = min(left, unlinked)
            if current is None:
                current = BatchAllocation(
                    batch_item_id=allocation.batch_item_id,
                    stock_movement_id=allocation.stock_movement_id,
                    movement_type=allocation.movement_type,
                    quantity=share,
                    unit_cost_cents=allocation.unit_cost_cents,
                    created_at=allocation.created_at,
                )
                db.add(current)
            else:
                current.quantity = share
            current.sale_item_id = item.id
            item.batch_item_id = item.batch_item_id or allocation.batch_item_id
            slot[1] -= share
            left -= share
            current = None
    db.flush()


def restore_sale_item(db: Session, *, sale_item_id: uuid.UUID, store_id: uuid.UUID, quantity: int) -> None:
    """Resealable returns go back into the batches the sale drew from, newest allocation first."""
    allocations = db.scalars(
        select(BatchAllocation)
        .where(
            BatchAllocation.sale_item_id == sale_item_id, BatchAllocation.quantity_returned < BatchAllocation.quantity
        )
        .order_by(BatchAllocation.created_at.desc(), BatchAllocation.id.desc())
    ).all()
    touched: set[uuid.UUID] = set()
    left = quantity
    for allocation in allocations:
        if left <= 0:
            break
        item = db.get(BatchItem, allocation.batch_item_id)
        if item is None or item.store_id != store_id:
            continue
        batch = db.get(PurchaseBatch, item.batch_id)
        if batch is None or batch.status == "REVERSED":
            continue
        back = min(
            left, allocation.quantity - allocation.quantity_returned, item.quantity_imported - item.quantity_remaining
        )
        if back <= 0:
            continue
        allocation.quantity_returned += back
        item.quantity_remaining += back
        touched.add(item.batch_id)
        left -= back
    if touched:
        db.flush()
        refresh_status(db, touched)
        db.flush()
