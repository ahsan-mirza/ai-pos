from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

BILL_STATUSES = ("OPEN", "PARTIAL", "PAID", "VOID")


class SupplierBill(TenantScoped, TimestampMixin, Base):
    """A supplier's invoice: what the business owes. Amounts are business-currency cents; tax_cents is the
    input VAT the supplier charged (recoverable when the business is VAT registered)."""

    __tablename__ = "supplier_bills"
    __table_args__ = (
        tenant_unique("goods_receipt_id", name="uq_supplier_bills_goods_receipt_id"),
        tenant_unique("purchase_batch_id", name="uq_supplier_bills_purchase_batch_id"),
        tenant_unique("supplier_id", "number", name="uq_supplier_bills_supplier_number"),
        CheckConstraint("total_cents >= 0", name="bill_total_nonnegative"),
        CheckConstraint("paid_cents >= 0 AND paid_cents <= total_cents", name="bill_paid_within_total"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # The supplier's own invoice number, as printed on their document.
    number: Mapped[str] = mapped_column(String(40))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True
    )
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id"), nullable=True
    )
    purchase_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_batches.id"), nullable=True
    )
    bill_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), default="OPEN", index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    lines: Mapped[list[SupplierBillLine]] = relationship(
        "SupplierBillLine", cascade="all, delete-orphan", lazy="selectin", order_by="SupplierBillLine.position"
    )


class SupplierBillLine(TenantScoped, Base):
    __tablename__ = "supplier_bill_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="bill_line_quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_bills.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer)
    # STANDARD, ZERO or EXEMPT, like products.tax_category.
    tax_category: Mapped[str] = mapped_column(String(8), default="STANDARD")
    tax_cents: Mapped[int] = mapped_column(Integer)
    line_total_cents: Mapped[int] = mapped_column(Integer)


class SupplierPayment(TenantScoped, TimestampMixin, Base):
    """Money paid to a supplier, allocated to bills. An outgoing cheque stays ISSUED until it clears; cancelling a
    payment voids it and releases its allocations."""

    __tablename__ = "supplier_payments"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="supplier_payment_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    # cash, transfer, card or cheque
    method: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str] = mapped_column(String(64), default="")
    paid_on: Mapped[date] = mapped_column(Date, index=True)
    cheque_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cheque_bank: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cheque_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # POSTED for immediate methods; ISSUED -> CLEARED for cheques; VOID once cancelled.
    status: Mapped[str] = mapped_column(String(8), default="POSTED", index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    allocations: Mapped[list[SupplierPaymentAllocation]] = relationship(
        "SupplierPaymentAllocation", cascade="all, delete-orphan", lazy="selectin"
    )


class SupplierPaymentAllocation(TenantScoped, Base):
    __tablename__ = "supplier_payment_allocations"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="allocation_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_payments.id", ondelete="CASCADE"), index=True
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("supplier_bills.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
