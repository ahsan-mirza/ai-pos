"""Kitchen display: stations that categories route to, and the tickets fired to them when an order is sent."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, utcnow

TICKET_STATUSES = ("NEW", "PREPARING", "READY", "BUMPED")


class KitchenStation(TenantScoped, TimestampMixin, Base):
    __tablename__ = "kitchen_stations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    # Category ids (as strings) whose items fire here; a default station takes everything unrouted.
    category_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # The register that sends the order also prints this station's ticket (no screen, or as a backup).
    print_tickets: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KitchenTicket(TenantScoped, Base):
    __tablename__ = "kitchen_tickets"
    __table_args__ = (Index("ix_kitchen_tickets_station_status", "station_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    station_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kitchen_stations.id", ondelete="CASCADE")
    )
    # Fired from an open order when it is sent, or from a counter sale (pay first, no order).
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("open_orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The order number, or for counter sales the day's running ticket number at the store.
    number: Mapped[int] = mapped_column(Integer)
    # Where it goes: the table label, the tab name, or the service type.
    label: Mapped[str] = mapped_column(String(80))
    service_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="NEW")
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bumped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)
    items: Mapped[list[KitchenTicketItem]] = relationship(
        "KitchenTicketItem", cascade="all, delete-orphan", order_by="KitchenTicketItem.position", lazy="selectin"
    )


class KitchenTicketItem(TenantScoped, Base):
    __tablename__ = "kitchen_ticket_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kitchen_tickets.id", ondelete="CASCADE"), index=True
    )
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("open_order_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    modifiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The meal this item belongs to ("Burger Meal"); its other components may fire at other stations.
    combo_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(160), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
