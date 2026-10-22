from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ConsignmentSettlement(TimestampMixin, Base):
    """What the business owes a consignment supplier for units sold up to `period_end`, raised as one supplier bill."""

    __tablename__ = "consignment_settlements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    bill_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("supplier_bills.id"), unique=True)
    units: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    lines: Mapped[list[ConsignmentSettlementLine]] = relationship(
        "ConsignmentSettlementLine", cascade="all, delete-orphan", lazy="selectin"
    )


class ConsignmentSettlementLine(TimestampMixin, Base):
    """Units of one consignment batch item paid for in a settlement. Their sum per item is what has been settled."""

    __tablename__ = "consignment_settlement_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="settled_quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    settlement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("consignment_settlements.id", ondelete="CASCADE"), index=True
    )
    batch_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("batch_items.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer)
