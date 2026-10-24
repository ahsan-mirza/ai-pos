"""Restaurant service: open orders (tabs) shared by every register in a store, and the dining-room floor plan."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

SERVICE_TYPES = ("DINE_IN", "TAKEAWAY", "DELIVERY")
ORDER_STATUSES = ("OPEN", "SETTLED", "VOID")
TABLE_SHAPES = ("square", "round", "rect")


class DiningArea(TenantScoped, TimestampMixin, Base):
    __tablename__ = "dining_areas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DiningTable(TenantScoped, TimestampMixin, Base):
    __tablename__ = "dining_tables"
    __table_args__ = (
        tenant_unique("area_id", "label", name="uq_dining_tables_area_label"),
        CheckConstraint("seats >= 1", name="seats_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dining_areas.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(16))
    seats: Mapped[int] = mapped_column(Integer, default=4)
    shape: Mapped[str] = mapped_column(String(8), default="square")
    # Position and size on the floor-plan grid (cells, not pixels).
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    w: Mapped[int] = mapped_column(Integer, default=2)
    h: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OpenOrder(TenantScoped, Base):
    """A tab: lines are added and sent to the kitchen over time, then settled into one or more sales."""

    __tablename__ = "open_orders"
    __table_args__ = (
        Index("ix_open_orders_store_status", "store_id", "status"),
        CheckConstraint("covers >= 0", name="covers_nonnegative"),
        # A delivery app's order arrives once however often its webhook retries.
        tenant_unique("channel_id", "external_ref", name="uq_open_orders_channel_ref"),
    )

    # Registers mint the id, so an order opened offline keeps it when it syncs.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    number: Mapped[int] = mapped_column(Integer)
    service_type: Mapped[str] = mapped_column(String(10), default="DINE_IN")
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dining_tables.id", ondelete="SET NULL"), nullable=True, index=True
    )
    covers: Mapped[int] = mapped_column(Integer, default=0)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # Bumped on every change; writers send the revision they read and get a 409 when it moved on.
    revision: Mapped[int] = mapped_column(Integer, default=1)
    bill_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Delivery-app orders (delivery channels module).
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_channels.id"), nullable=True, index=True
    )
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    items: Mapped[list[OpenOrderItem]] = relationship(
        "OpenOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OpenOrderItem.position",
        lazy="selectin",
    )


class OpenOrderItem(TenantScoped, Base):
    __tablename__ = "open_order_items"
    __table_args__ = (CheckConstraint("quantity >= 1", name="quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("open_orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    # Price per unit when ordered, modifiers included; settlement re-prices from the catalogue.
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    modifiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Meal components, as sent by the register (see SaleItem.components); priced again at settlement.
    components: Mapped[list | None] = mapped_column(JSON, nullable=True)
    seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(160), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # The sale that paid for this line (split bills settle an order in several sales).
    paid_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    order: Mapped[OpenOrder] = relationship("OpenOrder", back_populates="items")
