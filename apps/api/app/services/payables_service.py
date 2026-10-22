"""Accounts payable: supplier bills, payments allocated to them, outgoing cheques, statements and aging.

A bill's paid_cents is always recomputed from the allocations of payments that are not void, so voiding a
payment or cancelling a cheque puts the money back on the bills it covered."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch, Supplier
from app.models.payables import SupplierBill, SupplierBillLine, SupplierPayment, SupplierPaymentAllocation
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, PurchaseOrder, PurchaseOrderLine
from app.models.store import Store
from app.models.trade_in import TradeIn
from app.schemas.payables import (
    AllocationOut,
    BillCreate,
    BillFromReceipt,
    BillLineOut,
    BillOut,
    PayablesAging,
    PayablesSummary,
    StatementRow,
    SupplierBalance,
    SupplierPaymentCreate,
    SupplierPaymentOut,
    SupplierStatement,
    SupplierTerms,
    UnbilledReceipt,
)
from app.services.settings_service import business_currency
from app.services.tax import div_half_up
from app.services.tax import policy as tax_policy_for

LIVE_PAYMENT = ("POSTED", "ISSUED", "CLEARED")


def _today() -> date:
    return datetime.now(UTC).date()


def _supplier(db: Session, supplier_id: uuid.UUID) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ApiError(404, "not_found", "Supplier was not found.")
    return supplier


def _input_tax(db: Session, net_cents: int, category: str) -> int:
    rate = tax_policy_for(db).rate_for(category)
    return div_half_up(net_cents * rate, 10_000)


def _status(bill: SupplierBill) -> str:
    if bill.status == "VOID":
        return "VOID"
    if bill.paid_cents <= 0:
        return "OPEN"
    return "PAID" if bill.paid_cents >= bill.total_cents else "PARTIAL"


def _recompute(db: Session, bill_ids: set[uuid.UUID]) -> None:
    db.flush()
    for bill_id in bill_ids:
        bill = db.get(SupplierBill, bill_id)
        if bill is None:
            continue
        paid = db.scalar(
            select(func.coalesce(func.sum(SupplierPaymentAllocation.amount_cents), 0))
            .join(SupplierPayment, SupplierPayment.id == SupplierPaymentAllocation.payment_id)
            .where(SupplierPaymentAllocation.bill_id == bill_id, SupplierPayment.status.in_(LIVE_PAYMENT))
        )
        bill.paid_cents = int(paid or 0)
        bill.status = _status(bill)


def bill_out(db: Session, bill: SupplierBill) -> BillOut:
    supplier = db.get(Supplier, bill.supplier_id)
    store = db.get(Store, bill.store_id)
    order = db.get(PurchaseOrder, bill.purchase_order_id) if bill.purchase_order_id else None
    receipt = db.get(GoodsReceipt, bill.goods_receipt_id) if bill.goods_receipt_id else None
    batch = db.get(PurchaseBatch, bill.purchase_batch_id) if bill.purchase_batch_id else None
    balance = bill.total_cents - bill.paid_cents if bill.status != "VOID" else 0
    overdue = (_today() - bill.due_date).days if balance > 0 and bill.due_date < _today() else 0
    return BillOut(
        id=bill.id,
        supplier_id=bill.supplier_id,
        supplier_name=supplier.name if supplier else "",
        store_id=bill.store_id,
        store_code=store.code if store else "",
        number=bill.number,
        purchase_order_number=order.number if order else None,
        goods_receipt_number=receipt.number if receipt else (batch.batch_number if batch else None),
        bill_date=bill.bill_date,
        due_date=bill.due_date,
        currency=bill.currency,
        subtotal_cents=bill.subtotal_cents,
        tax_cents=bill.tax_cents,
        total_cents=bill.total_cents,
        paid_cents=bill.paid_cents,
        balance_cents=balance,
        status=bill.status,  # type: ignore[arg-type]
        overdue_days=overdue,
        note=bill.note,
        lines=[
            BillLineOut(
                id=line.id,
                product_id=line.product_id,
                description=line.description,
                quantity=line.quantity,
                unit_cost_cents=line.unit_cost_cents,
                tax_category=line.tax_category,  # type: ignore[arg-type]
                tax_cents=line.tax_cents,
                line_total_cents=line.line_total_cents,
            )
            for line in bill.lines
        ],
    )


def _add_bill(
    db: Session,
    *,
    supplier: Supplier,
    store_id: uuid.UUID,
    number: str,
    bill_date: date,
    due_date: date | None,
    lines: list[tuple[uuid.UUID | None, str, int, int, str]],
    note: str,
    user_id: uuid.UUID | None,
    purchase_order_id: uuid.UUID | None = None,
    goods_receipt_id: uuid.UUID | None = None,
    purchase_batch_id: uuid.UUID | None = None,
) -> SupplierBill:
    number = number.strip()
    if db.scalar(select(SupplierBill.id).where(SupplierBill.supplier_id == supplier.id, SupplierBill.number == number)):
        raise ApiError(409, "duplicate_bill", f"{supplier.name} invoice {number} is already recorded.")
    if db.get(Store, store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    bill = SupplierBill(
        supplier_id=supplier.id,
        store_id=store_id,
        number=number,
        purchase_order_id=purchase_order_id,
        goods_receipt_id=goods_receipt_id,
        purchase_batch_id=purchase_batch_id,
        bill_date=bill_date,
        due_date=due_date or bill_date + timedelta(days=supplier.payment_terms_days or 0),
        currency=business_currency(db),
        subtotal_cents=0,
        tax_cents=0,
        total_cents=0,
        note=note.strip(),
        created_by_id=user_id,
    )
    if bill.due_date < bill_date:
        raise ApiError(422, "validation_error", "The due date cannot be before the bill date.")
    for position, (product_id, description, quantity, unit_cost, category) in enumerate(lines):
        net = quantity * unit_cost
        tax = _input_tax(db, net, category)
        bill.lines.append(
            SupplierBillLine(
                position=position,
                product_id=product_id,
                description=description.strip(),
                quantity=quantity,
                unit_cost_cents=unit_cost,
                tax_category=category,
                tax_cents=tax,
                line_total_cents=net + tax,
            )
        )
        bill.subtotal_cents += net
        bill.tax_cents += tax
    bill.total_cents = bill.subtotal_cents + bill.tax_cents
    db.add(bill)
    db.flush()
    return bill


def create_bill(db: Session, data: BillCreate, user_id: uuid.UUID | None) -> BillOut:
    supplier = _supplier(db, data.supplier_id)
    for line in data.lines:
        if line.product_id is not None and db.get(Product, line.product_id) is None:
            raise ApiError(404, "not_found", f"Product for '{line.description}' was not found.")
    bill = _add_bill(
        db,
        supplier=supplier,
        store_id=data.store_id,
        number=data.number,
        bill_date=data.bill_date,
        due_date=data.due_date,
        lines=[
            (row.product_id, row.description, row.quantity, row.unit_cost_cents, row.tax_category) for row in data.lines
        ],
        note=data.note,
        user_id=user_id,
    )
    db.commit()
    return bill_out(db, bill)


def _receipt_supplier(db: Session, order: PurchaseOrder, override: uuid.UUID | None) -> Supplier:
    if override is not None:
        return _supplier(db, override)
    if order.supplier_id is not None:
        return _supplier(db, order.supplier_id)
    matched = db.scalar(select(Supplier).where(func.lower(Supplier.name) == order.supplier_name.strip().lower()))
    if matched is None:
        raise ApiError(
            422,
            "supplier_required",
            f"Choose which supplier '{order.supplier_name}' is; the order is not linked to one.",
        )
    return matched


def _trade_in_batch(db: Session, batch: PurchaseBatch) -> bool:
    return bool(
        db.scalar(
            select(TradeIn.id)
            .join(BatchItem, BatchItem.id == TradeIn.batch_item_id)
            .where(BatchItem.batch_id == batch.id)
            .limit(1)
        )
    )


def _create_bill_from_batch(db: Session, data: BillFromReceipt, user_id: uuid.UUID | None) -> BillOut:
    batch = db.get(PurchaseBatch, data.purchase_batch_id)
    if batch is None or _trade_in_batch(db, batch):
        raise ApiError(404, "not_found", "Purchase batch was not found.")
    if batch.status == "REVERSED":
        raise ApiError(409, "batch_reversed", f"Batch {batch.batch_number} was rolled back.")
    if batch.is_consignment:
        raise ApiError(
            409,
            "consignment_batch",
            f"Batch {batch.batch_number} is consignment stock: it is billed as it sells, from Consignment settlements.",
        )
    if db.scalar(select(SupplierBill.id).where(SupplierBill.purchase_batch_id == batch.id)):
        raise ApiError(409, "already_billed", f"Batch {batch.batch_number} is already billed.")
    supplier_id = data.supplier_id or batch.supplier_id
    if supplier_id is None:
        raise ApiError(422, "supplier_required", f"Choose which supplier batch {batch.batch_number} came from.")
    supplier = _supplier(db, supplier_id)
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in batch.items})))
    }
    lines = [
        (
            item.product_id,
            products[item.product_id].name if item.product_id in products else "Imported item",
            item.quantity_imported,
            item.purchase_cost_per_unit,
            products[item.product_id].tax_category if item.product_id in products else "STANDARD",
        )
        for item in batch.items
        if item.quantity_imported > 0
    ]
    if not lines:
        raise ApiError(422, "empty_batch", f"Batch {batch.batch_number} has no items to bill.")
    bill = _add_bill(
        db,
        supplier=supplier,
        store_id=batch.store_id,
        number=data.number,
        bill_date=data.bill_date,
        due_date=data.due_date,
        lines=lines,
        note=data.note or f"Purchase batch {batch.batch_number}",
        user_id=user_id,
        purchase_batch_id=batch.id,
    )
    if batch.supplier_id is None:
        batch.supplier_id = supplier.id
    db.commit()
    return bill_out(db, bill)


def create_bill_from_receipt(db: Session, data: BillFromReceipt, user_id: uuid.UUID | None) -> BillOut:
    if data.purchase_batch_id is not None:
        return _create_bill_from_batch(db, data, user_id)
    receipt = db.get(GoodsReceipt, data.goods_receipt_id)
    if receipt is None:
        raise ApiError(404, "not_found", "Goods receipt was not found.")
    if db.scalar(select(SupplierBill.id).where(SupplierBill.goods_receipt_id == receipt.id)):
        raise ApiError(409, "already_billed", f"Receipt {receipt.number} is already billed.")
    order = db.get(PurchaseOrder, receipt.purchase_order_id)
    if order is None:
        raise ApiError(404, "not_found", "Purchase order was not found.")
    supplier = _receipt_supplier(db, order, data.supplier_id)
    lines = []
    for row in receipt.lines:
        po_line = db.get(PurchaseOrderLine, row.purchase_order_line_id)
        product = db.get(Product, row.product_id)
        lines.append(
            (
                row.product_id,
                product.name if product else "Received item",
                row.quantity,
                po_line.unit_cost_cents if po_line else 0,
                product.tax_category if product else "STANDARD",
            )
        )
    bill = _add_bill(
        db,
        supplier=supplier,
        store_id=receipt.store_id,
        number=data.number,
        bill_date=data.bill_date,
        due_date=data.due_date,
        lines=lines,
        note=data.note or f"Goods receipt {receipt.number}",
        user_id=user_id,
        purchase_order_id=order.id,
        goods_receipt_id=receipt.id,
    )
    if order.supplier_id is None:
        order.supplier_id = supplier.id
    db.commit()
    return bill_out(db, bill)


def void_bill(db: Session, bill_id: uuid.UUID) -> BillOut:
    bill = db.get(SupplierBill, bill_id)
    if bill is None:
        raise ApiError(404, "not_found", "Bill was not found.")
    if bill.paid_cents > 0:
        raise ApiError(409, "bill_paid", "Void the payments against this bill first.")
    bill.status = "VOID"
    db.commit()
    return bill_out(db, bill)


def list_bills(
    db: Session, *, status: str | None, supplier_id: uuid.UUID | None, store_scope: uuid.UUID | None, limit: int
) -> list[BillOut]:
    query = select(SupplierBill).order_by(SupplierBill.due_date, SupplierBill.created_at).limit(limit)
    if status == "UNPAID":
        query = query.where(SupplierBill.status.in_(("OPEN", "PARTIAL")))
    elif status is not None:
        query = query.where(SupplierBill.status == status)
    if supplier_id is not None:
        query = query.where(SupplierBill.supplier_id == supplier_id)
    if store_scope is not None:
        query = query.where(SupplierBill.store_id == store_scope)
    return [bill_out(db, bill) for bill in db.scalars(query).unique()]


def unbilled_receipts(db: Session, store_scope: uuid.UUID | None) -> list[UnbilledReceipt]:
    billed = select(SupplierBill.goods_receipt_id).where(SupplierBill.goods_receipt_id.is_not(None))
    query = (
        select(GoodsReceipt).where(GoodsReceipt.id.not_in(billed)).order_by(GoodsReceipt.created_at.desc()).limit(100)
    )
    if store_scope is not None:
        query = query.where(GoodsReceipt.store_id == store_scope)
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    out = []
    for receipt in db.scalars(query).unique():
        order = db.get(PurchaseOrder, receipt.purchase_order_id)
        costs = {line.id: line.unit_cost_cents for line in order.lines} if order else {}
        created = receipt.created_at if receipt.created_at.tzinfo else receipt.created_at.replace(tzinfo=UTC)
        out.append(
            UnbilledReceipt(
                goods_receipt_id=receipt.id,
                number=receipt.number,
                purchase_order_number=order.number if order else "",
                supplier_id=order.supplier_id if order else None,
                supplier_name=order.supplier_name if order else "",
                store_code=stores.get(receipt.store_id, ""),
                received_on=created.date(),
                units=sum(line.quantity for line in receipt.lines),
                value_cents=sum(line.quantity * costs.get(line.purchase_order_line_id, 0) for line in receipt.lines),
            )
        )
    billed_batches = select(SupplierBill.purchase_batch_id).where(SupplierBill.purchase_batch_id.is_not(None))
    trade_in_items = select(TradeIn.batch_item_id).where(TradeIn.batch_item_id.is_not(None))
    batches = (
        select(PurchaseBatch)
        .where(
            PurchaseBatch.id.not_in(billed_batches),
            PurchaseBatch.status != "REVERSED",
            PurchaseBatch.total_cost_amount > 0,
            PurchaseBatch.is_consignment.is_(False),
            ~PurchaseBatch.items.any(BatchItem.id.in_(trade_in_items)),
        )
        .order_by(PurchaseBatch.created_at.desc())
        .limit(100)
    )
    if store_scope is not None:
        batches = batches.where(PurchaseBatch.store_id == store_scope)
    suppliers = {row.id: row.name for row in db.scalars(select(Supplier))}
    for batch in db.scalars(batches).unique():
        created = batch.created_at if batch.created_at.tzinfo else batch.created_at.replace(tzinfo=UTC)
        out.append(
            UnbilledReceipt(
                goods_receipt_id=None,
                purchase_batch_id=batch.id,
                number=batch.batch_number,
                purchase_order_number=batch.file_name or batch.import_source,
                supplier_id=batch.supplier_id,
                supplier_name=suppliers.get(batch.supplier_id, "") if batch.supplier_id else "",
                store_code=stores.get(batch.store_id, ""),
                received_on=created.date(),
                units=sum(item.quantity_imported for item in batch.items),
                value_cents=sum(item.quantity_imported * item.purchase_cost_per_unit for item in batch.items),
            )
        )
    out.sort(key=lambda row: row.received_on, reverse=True)
    return out


# --- Payments ----------------------------------------------------------------------------------------------


def payment_out(db: Session, payment: SupplierPayment) -> SupplierPaymentOut:
    supplier = db.get(Supplier, payment.supplier_id)
    numbers = {
        bill.id: bill.number
        for bill in db.scalars(
            select(SupplierBill).where(SupplierBill.id.in_([row.bill_id for row in payment.allocations]))
        ).unique()
    }
    allocated = sum(row.amount_cents for row in payment.allocations)
    return SupplierPaymentOut(
        id=payment.id,
        supplier_id=payment.supplier_id,
        supplier_name=supplier.name if supplier else "",
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        method=payment.method,  # type: ignore[arg-type]
        reference=payment.reference,
        paid_on=payment.paid_on,
        cheque_number=payment.cheque_number,
        cheque_bank=payment.cheque_bank,
        cheque_date=payment.cheque_date,
        status=payment.status,  # type: ignore[arg-type]
        note=payment.note,
        allocations=[
            AllocationOut(bill_id=row.bill_id, bill_number=numbers.get(row.bill_id, ""), amount_cents=row.amount_cents)
            for row in payment.allocations
        ],
        unallocated_cents=payment.amount_cents - allocated if payment.status != "VOID" else 0,
    )


def pay(db: Session, data: SupplierPaymentCreate, user_id: uuid.UUID | None) -> SupplierPaymentOut:
    supplier = _supplier(db, data.supplier_id)
    open_bills = list(
        db.scalars(
            select(SupplierBill)
            .where(SupplierBill.supplier_id == supplier.id, SupplierBill.status.in_(("OPEN", "PARTIAL")))
            .order_by(SupplierBill.due_date, SupplierBill.bill_date)
        ).unique()
    )
    by_id = {bill.id: bill for bill in open_bills}
    plan: list[tuple[SupplierBill, int]] = []
    if data.allocations:
        for item in data.allocations:
            bill = by_id.get(item.bill_id)
            if bill is None:
                raise ApiError(422, "bill_not_open", "Payments can only go to this supplier's unpaid bills.")
            if item.amount_cents > bill.total_cents - bill.paid_cents:
                raise ApiError(
                    422, "over_allocated", f"Bill {bill.number} has only {bill.total_cents - bill.paid_cents} left."
                )
            plan.append((bill, item.amount_cents))
    else:
        left = data.amount_cents
        for bill in open_bills:
            if left <= 0:
                break
            take = min(left, bill.total_cents - bill.paid_cents)
            if take > 0:
                plan.append((bill, take))
                left -= take
    payment = SupplierPayment(
        supplier_id=supplier.id,
        amount_cents=data.amount_cents,
        currency=business_currency(db),
        method=data.method,
        reference=data.reference.strip(),
        paid_on=data.paid_on,
        cheque_number=data.cheque.number.strip() if data.cheque else None,
        cheque_bank=data.cheque.bank.strip() if data.cheque else None,
        cheque_date=data.cheque.cheque_date if data.cheque else None,
        status="ISSUED" if data.method == "cheque" else "POSTED",
        note=data.note.strip(),
        created_by_id=user_id,
    )
    for bill, amount in plan:
        payment.allocations.append(SupplierPaymentAllocation(bill_id=bill.id, amount_cents=amount))
    db.add(payment)
    _recompute(db, {bill.id for bill, _ in plan})
    db.commit()
    return payment_out(db, payment)


def clear_cheque(db: Session, payment_id: uuid.UUID) -> SupplierPaymentOut:
    payment = db.get(SupplierPayment, payment_id)
    if payment is None:
        raise ApiError(404, "not_found", "Payment was not found.")
    if payment.status != "ISSUED":
        raise ApiError(409, "not_issued", "Only issued cheques can be marked cleared.")
    payment.status = "CLEARED"
    payment.cleared_at = datetime.now(UTC)
    db.commit()
    return payment_out(db, payment)


def void_payment(db: Session, payment_id: uuid.UUID, note: str) -> SupplierPaymentOut:
    payment = db.get(SupplierPayment, payment_id)
    if payment is None:
        raise ApiError(404, "not_found", "Payment was not found.")
    if payment.status in ("VOID", "CLEARED"):
        raise ApiError(409, "payment_final", f"A {payment.status.lower()} payment cannot be voided.")
    payment.status = "VOID"
    payment.voided_at = datetime.now(UTC)
    if note.strip():
        payment.note = f"{payment.note} · Voided: {note.strip()}".strip(" ·")[:255]
    _recompute(db, {row.bill_id for row in payment.allocations})
    db.commit()
    return payment_out(db, payment)


def list_payments(db: Session, *, supplier_id: uuid.UUID | None, limit: int) -> list[SupplierPaymentOut]:
    query = select(SupplierPayment).order_by(SupplierPayment.paid_on.desc(), SupplierPayment.created_at.desc())
    if supplier_id is not None:
        query = query.where(SupplierPayment.supplier_id == supplier_id)
    return [payment_out(db, row) for row in db.scalars(query.limit(limit)).unique()]


# --- Balances and statements -------------------------------------------------------------------------------


def _balances(db: Session) -> dict[uuid.UUID, dict[str, int]]:
    today = _today()
    out: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for bill in db.scalars(select(SupplierBill).where(SupplierBill.status.in_(("OPEN", "PARTIAL")))).unique():
        due = bill.total_cents - bill.paid_cents
        row = out[bill.supplier_id]
        row["outstanding"] += due
        row["open_bills"] += 1
        if bill.due_date < today:
            row["overdue"] += due
        elif bill.due_date <= today + timedelta(days=7):
            row["due_7d"] += due
    for payment in db.scalars(select(SupplierPayment).where(SupplierPayment.status.in_(LIVE_PAYMENT))).unique():
        row = out[payment.supplier_id]
        row["credit"] += payment.amount_cents - sum(item.amount_cents for item in payment.allocations)
        if payment.status == "ISSUED":
            row["cheques"] += payment.amount_cents
    return out


def _balance_row(supplier: Supplier, totals: dict[str, int]) -> SupplierBalance:
    return SupplierBalance(
        supplier_id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        trn=supplier.trn,
        payment_terms_days=supplier.payment_terms_days or 0,
        open_bills=totals.get("open_bills", 0),
        outstanding_cents=totals.get("outstanding", 0),
        overdue_cents=totals.get("overdue", 0),
        due_7d_cents=totals.get("due_7d", 0),
        credit_cents=totals.get("credit", 0),
        cheques_issued_cents=totals.get("cheques", 0),
    )


def summary(db: Session) -> PayablesSummary:
    balances = _balances(db)
    rows = [
        _balance_row(supplier, balances.get(supplier.id, {}))
        for supplier in db.scalars(select(Supplier).order_by(Supplier.name))
        if supplier.is_active or supplier.id in balances
    ]
    rows.sort(key=lambda row: (-row.overdue_cents, -row.outstanding_cents, row.name.lower()))
    return PayablesSummary(
        outstanding_cents=sum(row.outstanding_cents for row in rows),
        overdue_cents=sum(row.overdue_cents for row in rows),
        due_7d_cents=sum(row.due_7d_cents for row in rows),
        cheques_issued_cents=sum(row.cheques_issued_cents for row in rows),
        suppliers=rows,
    )


def set_terms(db: Session, supplier_id: uuid.UUID, data: SupplierTerms) -> SupplierBalance:
    supplier = _supplier(db, supplier_id)
    supplier.payment_terms_days = data.payment_terms_days
    supplier.trn = data.trn
    db.commit()
    return _balance_row(supplier, _balances(db).get(supplier.id, {}))


def statement(db: Session, supplier_id: uuid.UUID) -> SupplierStatement:
    supplier = _supplier(db, supplier_id)
    bills = list(
        db.scalars(
            select(SupplierBill).where(SupplierBill.supplier_id == supplier.id, SupplierBill.status != "VOID")
        ).unique()
    )
    payments = list(
        db.scalars(
            select(SupplierPayment).where(
                SupplierPayment.supplier_id == supplier.id, SupplierPayment.status.in_(LIVE_PAYMENT)
            )
        ).unique()
    )
    events: list[tuple[date, int, StatementRow]] = []
    for bill in bills:
        events.append(
            (
                bill.bill_date,
                0,
                StatementRow(
                    on=bill.bill_date,
                    kind="BILL",
                    reference=bill.number,
                    bill_cents=bill.total_cents,
                    paid_cents=0,
                    balance_cents=0,
                    note=f"Due {bill.due_date:%d %b %Y}",
                ),
            )
        )
    for payment in payments:
        label = payment.method if payment.method != "cheque" else f"cheque {payment.cheque_number}"
        events.append(
            (
                payment.paid_on,
                1,
                StatementRow(
                    on=payment.paid_on,
                    kind="PAYMENT",
                    reference=payment.reference or label,
                    bill_cents=0,
                    paid_cents=payment.amount_cents,
                    balance_cents=0,
                    note=f"{label} · {payment.status.lower()}",
                ),
            )
        )
    running = 0
    rows = []
    for _, _, row in sorted(events, key=lambda item: (item[0], item[1])):
        running += row.bill_cents - row.paid_cents
        rows.append(row.model_copy(update={"balance_cents": running}))
    aging = defaultdict(int)
    today = _today()
    open_bills = [bill for bill in bills if bill.status in ("OPEN", "PARTIAL")]
    for bill in open_bills:
        late = (today - bill.due_date).days
        bucket = (
            "current"
            if late <= 0
            else "days_1_30"
            if late <= 30
            else "days_31_60"
            if late <= 60
            else "days_61_90"
            if late <= 90
            else "days_90_plus"
        )
        aging[bucket] += bill.total_cents - bill.paid_cents
    return SupplierStatement(
        supplier=_balance_row(supplier, _balances(db).get(supplier.id, {})),
        currency=business_currency(db),
        rows=rows,
        aging=PayablesAging(**{key: aging.get(key, 0) for key in PayablesAging.model_fields}),
        open_bills=[bill_out(db, bill) for bill in sorted(open_bills, key=lambda bill: bill.due_date)],
    )
