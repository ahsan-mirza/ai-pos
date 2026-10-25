from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

if TYPE_CHECKING:
    from app.models.sale_item import SaleItem
    from app.models.sale_tender import SaleTender

SALE_TYPES = ("RETAIL", "WHOLESALE")
PAYMENT_STATUSES = ("PAID", "PARTIAL", "ON_ACCOUNT_UNPAID")
QUOTE_STATUSES = ("OPEN", "CONVERTED", "EXPIRED", "CANCELLED")


class Sale(TenantScoped, TimestampMixin, Base):
    """A completed sale, or a proforma quote (status "quote", is_quote_proforma) that only reserves stock."""

    __tablename__ = "sales"
    __table_args__ = (
        tenant_unique("client_sale_id", name="uq_sales_client_sale_id"),
        tenant_unique("invoice_number", name="uq_sales_invoice_number"),
        CheckConstraint("subtotal_cents >= 0", name="subtotal_nonnegative"),
        CheckConstraint("tax_cents >= 0", name="tax_nonnegative"),
        CheckConstraint("total_cents >= 0", name="total_nonnegative"),
        CheckConstraint("amount_paid_cents >= 0", name="amount_paid_nonnegative"),
        CheckConstraint("due_balance_cents >= 0", name="due_balance_nonnegative"),
        CheckConstraint("amount_paid_cents + due_balance_cents = total_cents", name="paid_plus_due_is_total"),
        Index("ix_sales_tenant_store_created", "tenant_id", "store_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    # The stylist who served the customer when it is not the cashier; commissions credit coalesce(this, cashier).
    sales_associate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    payment_method: Mapped[str] = mapped_column(String(32))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    client_sale_id: Mapped[str] = mapped_column(String(64))
    # Tax invoice number for sales, quotation number for quotes; unique across the business.
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    # No foreign key: a register may sync a sale before the shift that rang it (e.g. a rejected open retried).
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    sale_type: Mapped[str] = mapped_column(String(16), default="RETAIL", index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    is_quote_proforma: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quote_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quote_status: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    converted_sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # QUOTE: a proforma offer. LAYAWAY: goods held against deposits until the customer pays in full.
    quote_kind: Mapped[str | None] = mapped_column(String(12), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(24), default="PAID", index=True)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    due_balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Restaurant service: the tab this sale paid, the service charge inside total_cents (its VAT is in
    # tax_cents), and the tip collected on top of total_cents for staff.
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    service_charge_cents: Mapped[int] = mapped_column(Integer, default=0)
    service_charge_tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    tip_cents: Mapped[int] = mapped_column(Integer, default=0)
    tip_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # The wholesale sales order this sale invoices (one sale per delivery).
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    items: Mapped[list[SaleItem]] = relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
    )
    tenders: Mapped[list[SaleTender]] = relationship(
        "SaleTender",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
