from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

MOVEMENT_TYPES = (
    "PURCHASE_IN",
    "SALE_OUT",
    "RETURN_IN",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "DAMAGE_SHRINKAGE",
    "AUDIT_ADJUSTMENT",
    "PURCHASE_REVERSAL",
    # Ingredients drawn by a sold dish (recipes module); the dish itself carries no stock.
    "RECIPE_OUT",
)


class InventoryLevel(TenantScoped, TimestampMixin, Base):
    """Stock of one product at one branch. Only services.inventory writes quantities."""

    __tablename__ = "inventory_levels"
    __table_args__ = (
        tenant_unique("product_id", "store_id", name="uq_inventory_levels_product_store"),
        CheckConstraint("quantity_on_hand >= 0", name="on_hand_nonnegative"),
        CheckConstraint("quantity_reserved >= 0", name="reserved_nonnegative"),
        CheckConstraint("min_reorder_level >= 0", name="min_reorder_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)
    min_reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    max_stock_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aisle_shelf_location: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def available(self) -> int:
        return self.quantity_on_hand - self.quantity_reserved


class StockMovement(TenantScoped, Base):
    """Append-only ledger. quantity is signed; quantity_after is the branch on-hand after the movement."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        Index("ix_stock_movements_product_store_created", "product_id", "store_id", "created_at"),
        Index("ix_stock_movements_tenant_store_created", "tenant_id", "store_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("serial_numbers.id"),
        nullable=True,
        index=True,
    )
    movement_type: Mapped[str] = mapped_column(String(24), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reference_type: Mapped[str] = mapped_column(String(32))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
