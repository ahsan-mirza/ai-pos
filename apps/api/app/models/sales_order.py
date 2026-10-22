"""Wholesale sales orders: taken now, reserved against branch stock, picked, delivered in one or more deliveries
(each invoiced as an ordinary sale when it leaves), with backorders for what is not yet in stock."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utcnow

ORDER_STATUSES = ("DRAFT", "CONFIRMED", "PICKING", "PARTIALLY_DELIVERED", "DELIVERED", "CLOSED", "CANCELLED")
ORDER_SOURCES = ("manual", "register", "quote", "b2b", "ecommerce", "rep")


class SalesOrder(TimestampMixin, Base):
    __tablename__ = "sales_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    sale_type: Mapped[str] = mapped_column(String(10), default="WHOLESALE")
    price_tier: Mapped[str] = mapped_column(String(16), default="RETAIL")
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(12), default="manual")
    # The quote it came from, or the shop / portal order it mirrors.
    quote_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    channel_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    customer_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # At the order's prices; each delivery invoices its own share.
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lines: Mapped[list[SalesOrderLine]] = relationship(
        "SalesOrderLine", cascade="all, delete-orphan", order_by="SalesOrderLine.position", lazy="selectin"
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        CheckConstraint("quantity_ordered >= 1", name="ordered_positive"),
        CheckConstraint("quantity_delivered + quantity_cancelled <= quantity_ordered", name="fulfilled_within_ordered"),
        CheckConstraint("quantity_reserved >= 0", name="reserved_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Pieces; the price is per piece, as on sale lines.
    quantity_ordered: Mapped[int] = mapped_column(Integer)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)
    quantity_delivered: Mapped[int] = mapped_column(Integer, default=0)
    quantity_cancelled: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    # The tier / list price when ordered; a lower agreed price needs an approver, kept for the invoices.
    list_price_cents: Mapped[int] = mapped_column(Integer)
    price_override_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    line_total_cents: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def outstanding(self) -> int:
        return self.quantity_ordered - self.quantity_delivered - self.quantity_cancelled


class PickList(Base):
    __tablename__ = "pick_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lines: Mapped[list[PickListLine]] = relationship(
        "PickListLine", cascade="all, delete-orphan", order_by="PickListLine.position", lazy="selectin"
    )


class PickListLine(Base):
    __tablename__ = "pick_list_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pick_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pick_lists.id", ondelete="CASCADE"), index=True
    )
    order_line_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_order_lines.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    bin_location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class DeliveryNote(Base):
    """One delivery of an order. It is invoiced as it leaves (the sale), then signed for at the customer."""

    __tablename__ = "delivery_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    # DISPATCHED when it leaves (and is invoiced), DELIVERED once signed for.
    status: Mapped[str] = mapped_column(String(12), default="DISPATCHED", index=True)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    vehicle: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dispatched_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receiver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Signature drawn on the driver's phone, as a PNG data URL.
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    pod_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lines: Mapped[list[DeliveryNoteLine]] = relationship(
        "DeliveryNoteLine", cascade="all, delete-orphan", order_by="DeliveryNoteLine.position", lazy="selectin"
    )


class DeliveryNoteLine(Base):
    __tablename__ = "delivery_note_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_notes.id", ondelete="CASCADE"), index=True
    )
    order_line_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_order_lines.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    # Last digits of the IMEIs / serials delivered (the full values are on the sale's serial records).
    serial_suffixes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
