from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

TRANSFER_STATUSES = ("requested", "in_transit", "received", "cancelled")


class StockTransfer(TenantScoped, TimestampMixin, Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        tenant_unique("number", name="uq_stock_transfers_number"),
        CheckConstraint("source_store_id <> destination_store_id", name="distinct_stores"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(32))
    source_store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    destination_store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="requested")
    note: Mapped[str] = mapped_column(String(255), default="")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    shipped_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lines: Mapped[list[StockTransferLine]] = relationship(
        "StockTransferLine",
        cascade="all, delete-orphan",
        order_by="StockTransferLine.position",
        lazy="selectin",
    )
    serials: Mapped[list[StockTransferSerial]] = relationship(
        "StockTransferSerial",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StockTransferLine(TenantScoped, Base):
    __tablename__ = "stock_transfer_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("stock_transfers.id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)


class StockTransferSerial(TenantScoped, Base):
    """IMEI/serial units assigned to a transfer line when it ships."""

    __tablename__ = "stock_transfer_serials"

    transfer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("stock_transfers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    serial_number_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("serial_numbers.id"),
        primary_key=True,
    )
    transfer_line_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stock_transfer_lines.id"))
