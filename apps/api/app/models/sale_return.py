from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

if TYPE_CHECKING:
    from app.models.return_item import ReturnItem
    from app.models.return_tender import ReturnTender


class SaleReturn(TenantScoped, TimestampMixin, Base):
    __tablename__ = "returns"
    __table_args__ = (
        tenant_unique("credit_note_number", name="uq_returns_credit_note_number"),
        CheckConstraint("subtotal_cents >= 0", name="subtotal_nonnegative"),
        CheckConstraint("tax_refund_cents >= 0", name="tax_refund_nonnegative"),
        CheckConstraint("restocking_fee_cents >= 0", name="restocking_fee_nonnegative"),
        CheckConstraint("total_refund_cents >= 0", name="total_refund_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), index=True)
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    tax_refund_cents: Mapped[int] = mapped_column(Integer)
    restocking_fee_cents: Mapped[int] = mapped_column(Integer)
    total_refund_cents: Mapped[int] = mapped_column(Integer)
    refund_method: Mapped[str] = mapped_column(String(32))
    credit_note_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    reason_notes: Mapped[str] = mapped_column(Text, default="")
    items: Mapped[list[ReturnItem]] = relationship(
        "ReturnItem",
        back_populates="sale_return",
        cascade="all, delete-orphan",
    )
    tenders: Mapped[list[ReturnTender]] = relationship(
        "ReturnTender",
        back_populates="sale_return",
        cascade="all, delete-orphan",
    )
