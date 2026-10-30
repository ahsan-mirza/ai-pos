"""Cost-tracked purchase batches. Every unit that enters a branch through an import belongs to one batch item;
every unit that leaves it (sale, transfer, write-off, reversal) is drawn first-in-first-out and recorded as a
batch allocation carrying the cost it was bought at, so batch P&L survives later cost corrections and rollbacks."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

IMPORT_SOURCES = ("EXCEL", "CSV", "PDF_INVOICE", "MANUAL")
BATCH_STATUSES = ("ACTIVE", "PARTIALLY_SOLD", "EXHAUSTED", "REVERSED")


class Supplier(TenantScoped, TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        tenant_unique("name", name="uq_suppliers_name"),
        tenant_unique("code", name="uq_suppliers_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(32))
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Days from ordering to stock on the shelf; drives reorder points.
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    # Smallest quantity per product line the supplier accepts, and the case size orders are rounded up to.
    moq: Mapped[int] = mapped_column(Integer, default=1)
    pack_size: Mapped[int] = mapped_column(Integer, default=1)
    # Weekdays the supplier takes orders, e.g. ["SUN", "WED"]; empty means any day.
    order_days: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Days of credit the supplier gives; a bill falls due this long after its date.
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    trn: Mapped[str | None] = mapped_column(String(15), nullable=True)


class ImportMappingTemplate(TenantScoped, TimestampMixin, Base):
    """A saved header-to-field mapping, optionally scoped to one supplier's invoice layout."""

    __tablename__ = "import_mapping_templates"
    __table_args__ = (tenant_unique("supplier_id", "name", name="uq_import_mapping_templates_supplier_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # system field -> source header
    mapping: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class PurchaseBatch(TenantScoped, Base):
    __tablename__ = "purchase_batches"
    __table_args__ = (
        tenant_unique("batch_number", name="uq_purchase_batches_batch_number"),
        CheckConstraint("total_cost_amount >= 0", name="total_cost_nonnegative"),
        CheckConstraint("total_items_count >= 0", name="total_items_nonnegative"),
        Index("ix_purchase_batches_store_created", "store_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_number: Mapped[str] = mapped_column(String(32))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id"), nullable=True, index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # Set when this layer was opened by a goods receipt. That receipt already posts the inventory journal.
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id"), nullable=True, index=True
    )
    import_source: Mapped[str] = mapped_column(String(16))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_template_used: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Cents in the business currency; the sum of quantity_imported * purchase_cost_per_unit.
    total_cost_amount: Mapped[int] = mapped_column(Integer, default=0)
    total_items_count: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), index=True, default="ACTIVE")
    # Supplier-owned stock: not billed on receipt, settled with the supplier as it sells (consignment_service).
    is_consignment: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    items: Mapped[list[BatchItem]] = relationship(
        "BatchItem", back_populates="batch", cascade="all, delete-orphan", order_by="BatchItem.position"
    )


class BatchItem(TenantScoped, Base):
    __tablename__ = "batch_items"
    __table_args__ = (
        CheckConstraint("quantity_imported >= 0", name="imported_nonnegative"),
        CheckConstraint("quantity_remaining >= 0", name="remaining_nonnegative"),
        CheckConstraint("quantity_remaining <= quantity_imported", name="remaining_within_imported"),
        CheckConstraint("purchase_cost_per_unit >= 0", name="cost_nonnegative"),
        CheckConstraint("selling_price_per_unit >= 0", name="price_nonnegative"),
        # FIFO picks the oldest open batch item for a product at a branch.
        Index("ix_batch_items_fifo", "product_id", "store_id", "quantity_remaining", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_batches.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    quantity_imported: Mapped[int] = mapped_column(Integer)
    quantity_remaining: Mapped[int] = mapped_column(Integer)
    purchase_cost_per_unit: Mapped[int] = mapped_column(Integer)
    selling_price_per_unit: Mapped[int] = mapped_column(Integer)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Serial-number ids registered by this line. Values stay encrypted on serial_numbers.
    imported_serials: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    batch: Mapped[PurchaseBatch] = relationship("PurchaseBatch", back_populates="items")


class BatchAllocation(TenantScoped, Base):
    """Units drawn from one batch item by one stock movement. quantity_returned counts units that came back."""

    __tablename__ = "batch_allocations"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("quantity_returned >= 0", name="returned_nonnegative"),
        CheckConstraint("quantity_returned <= quantity", name="returned_within_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batch_items.id", ondelete="CASCADE"), index=True
    )
    stock_movement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_movements.id"), index=True
    )
    sale_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sale_items.id"), nullable=True, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[int] = mapped_column(Integer)
    quantity_returned: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_cents: Mapped[int] = mapped_column(Integer)
    # Drawn from a batch already past its expiry date (an offline sale, or FEFO had nothing fresher).
    expired: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
