"""Consignment stock: units a supplier owns until they sell. Sell-through comes from the batch ledger (allocations
linked to sale lines, net of returns), so a settlement pays exactly for what left the shop in a sale; settling raises
an ordinary supplier bill, which Payables then pays like any other."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch, Supplier
from app.models.consignment import ConsignmentSettlement, ConsignmentSettlementLine
from app.models.payables import SupplierBill
from app.models.product import Product
from app.models.store import Store
from app.schemas.consignment import (
    ConsignmentItemOut,
    ConsignmentOverview,
    ConsignmentSupplierOut,
    SettlementCreate,
    SettlementOut,
)
from app.services import audit
from app.services.payables_service import _add_bill
from app.services.settings_service import business_currency


def _items(db: Session, supplier_id: uuid.UUID | None = None) -> list[ConsignmentItemOut]:
    statement = (
        select(BatchItem, PurchaseBatch, Product, Store.code)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .join(Product, Product.id == BatchItem.product_id)
        .join(Store, Store.id == BatchItem.store_id)
        .where(PurchaseBatch.is_consignment.is_(True), PurchaseBatch.status != "REVERSED")
        .order_by(PurchaseBatch.created_at, BatchItem.position)
    )
    if supplier_id is not None:
        statement = statement.where(PurchaseBatch.supplier_id == supplier_id)
    rows = db.execute(statement).all()
    ids = [item.id for item, *_ in rows]
    sold: dict[uuid.UUID, int] = defaultdict(int)
    settled: dict[uuid.UUID, int] = defaultdict(int)
    if ids:
        for item_id, units in db.execute(
            select(
                BatchAllocation.batch_item_id,
                func.sum(BatchAllocation.quantity - BatchAllocation.quantity_returned),
            )
            .where(BatchAllocation.batch_item_id.in_(ids), BatchAllocation.sale_item_id.is_not(None))
            .group_by(BatchAllocation.batch_item_id)
        ):
            sold[item_id] = int(units or 0)
        for item_id, units in db.execute(
            select(ConsignmentSettlementLine.batch_item_id, func.sum(ConsignmentSettlementLine.quantity))
            .where(ConsignmentSettlementLine.batch_item_id.in_(ids))
            .group_by(ConsignmentSettlementLine.batch_item_id)
        ):
            settled[item_id] = int(units or 0)
    out = []
    for item, batch, product, store_code in rows:
        unsettled = max(0, sold[item.id] - settled[item.id])
        out.append(
            ConsignmentItemOut(
                batch_item_id=item.id,
                batch_id=batch.id,
                batch_number=batch.batch_number,
                store_code=store_code,
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                received=item.quantity_imported,
                on_hand=item.quantity_remaining,
                sold=sold[item.id],
                settled=settled[item.id],
                unsettled=unsettled,
                unit_cost_cents=item.purchase_cost_per_unit,
                unsettled_cents=unsettled * item.purchase_cost_per_unit,
            )
        )
    return out


def overview(db: Session) -> ConsignmentOverview:
    items = _items(db)
    batch_supplier = dict(
        db.execute(
            select(PurchaseBatch.id, PurchaseBatch.supplier_id).where(
                PurchaseBatch.id.in_({item.batch_id for item in items})
            )
        ).all()
    )
    by_supplier: dict[uuid.UUID, list[ConsignmentItemOut]] = defaultdict(list)
    for item in items:
        supplier_id = batch_supplier.get(item.batch_id)
        if supplier_id is not None:
            by_supplier[supplier_id].append(item)
    names = (
        dict(db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(list(by_supplier)))).all())
        if by_supplier
        else {}
    )
    suppliers = [
        ConsignmentSupplierOut(
            supplier_id=supplier_id,
            supplier_name=names.get(supplier_id, "Supplier"),
            batches=len({row.batch_id for row in rows}),
            units_on_hand=sum(row.on_hand for row in rows),
            value_on_hand_cents=sum(row.on_hand * row.unit_cost_cents for row in rows),
            units_sold=sum(row.sold for row in rows),
            unsettled_units=sum(row.unsettled for row in rows),
            unsettled_cents=sum(row.unsettled_cents for row in rows),
            settled_cents=sum(row.settled * row.unit_cost_cents for row in rows),
            items=rows,
        )
        for supplier_id, rows in by_supplier.items()
    ]
    suppliers.sort(key=lambda row: -row.unsettled_cents)
    return ConsignmentOverview(
        currency=business_currency(db),
        units_on_hand=sum(row.units_on_hand for row in suppliers),
        value_on_hand_cents=sum(row.value_on_hand_cents for row in suppliers),
        unsettled_cents=sum(row.unsettled_cents for row in suppliers),
        suppliers=suppliers,
    )


def _next_number(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(ConsignmentSettlement)) or 0
    return f"CONS-{count + 1:06d}"


def settle(db: Session, data: SettlementCreate, user_id: uuid.UUID | None) -> list[SettlementOut]:
    """Bills the supplier for every unit sold and not yet settled, one settlement (and bill) per branch."""
    supplier = db.get(Supplier, data.supplier_id)
    if supplier is None:
        raise ApiError(404, "not_found", "Supplier was not found.")
    items = [item for item in _items(db, supplier.id) if item.unsettled > 0]
    if not items:
        raise ApiError(422, "nothing_to_settle", f"Nothing sold from {supplier.name}'s consignment stock is unsettled.")
    store_of = dict(
        db.execute(
            select(BatchItem.id, BatchItem.store_id).where(BatchItem.id.in_([item.batch_item_id for item in items]))
        ).all()
    )
    tax_of = dict(
        db.execute(
            select(Product.id, Product.tax_category).where(Product.id.in_({item.product_id for item in items}))
        ).all()
    )
    by_store: dict[uuid.UUID, list[ConsignmentItemOut]] = defaultdict(list)
    for item in items:
        by_store[store_of[item.batch_item_id]].append(item)
    bill_date = data.bill_date or datetime.now(UTC).date()
    created: list[ConsignmentSettlement] = []
    for store_id, rows in by_store.items():
        number = _next_number(db)
        bill = _add_bill(
            db,
            supplier=supplier,
            store_id=store_id,
            number=number,
            bill_date=bill_date,
            due_date=None,
            lines=[
                (
                    row.product_id,
                    f"{row.name} (consignment {row.batch_number})",
                    row.unsettled,
                    row.unit_cost_cents,
                    tax_of.get(row.product_id, "STANDARD"),
                )
                for row in rows
            ],
            note=data.note or f"Consignment sell-through to {bill_date:%d %b %Y}",
            user_id=user_id,
        )
        settlement = ConsignmentSettlement(
            number=number,
            supplier_id=supplier.id,
            period_end=bill_date,
            bill_id=bill.id,
            units=sum(row.unsettled for row in rows),
            total_cents=sum(row.unsettled_cents for row in rows),
            created_by_id=user_id,
            lines=[
                ConsignmentSettlementLine(
                    batch_item_id=row.batch_item_id,
                    product_id=row.product_id,
                    quantity=row.unsettled,
                    unit_cost_cents=row.unit_cost_cents,
                )
                for row in rows
            ],
        )
        db.add(settlement)
        db.flush()
        audit.record(
            db,
            action_type="CREATE",
            action="consignment.settled",
            target_entity="ConsignmentSettlement",
            target_entity_id=settlement.id,
            details={"supplier": supplier.name, "units": settlement.units, "total_cents": settlement.total_cents},
        )
        created.append(settlement)
    db.commit()
    return [_settlement_out(db, row) for row in created]


def _settlement_out(db: Session, row: ConsignmentSettlement) -> SettlementOut:
    bill = db.get(SupplierBill, row.bill_id)
    supplier = db.get(Supplier, row.supplier_id)
    store = db.get(Store, bill.store_id) if bill is not None else None
    assert bill is not None and supplier is not None
    return SettlementOut(
        id=row.id,
        number=row.number,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        store_code=store.code if store is not None else "",
        period_end=row.period_end,
        units=row.units,
        total_cents=row.total_cents,
        bill_id=bill.id,
        bill_total_cents=bill.total_cents,
        bill_status=bill.status,
        created_at=row.created_at,
    )


def settlements(db: Session, supplier_id: uuid.UUID | None = None, limit: int = 100) -> list[SettlementOut]:
    statement = select(ConsignmentSettlement).order_by(ConsignmentSettlement.created_at.desc()).limit(limit)
    if supplier_id is not None:
        statement = statement.where(ConsignmentSettlement.supplier_id == supplier_id)
    return [_settlement_out(db, row) for row in db.scalars(statement)]


def consigned_units(db: Session, store_id: uuid.UUID | None) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    """Supplier-owned units on hand per (product, store): what owned-stock valuations leave out."""
    statement = (
        select(BatchItem.product_id, BatchItem.store_id, func.sum(BatchItem.quantity_remaining))
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(PurchaseBatch.is_consignment.is_(True), PurchaseBatch.status != "REVERSED")
        .group_by(BatchItem.product_id, BatchItem.store_id)
    )
    if store_id is not None:
        statement = statement.where(BatchItem.store_id == store_id)
    return {(product_id, store): int(units or 0) for product_id, store, units in db.execute(statement)}
