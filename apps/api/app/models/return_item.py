from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped
from app.models.product import Product

if TYPE_CHECKING:
    from app.models.sale_return import SaleReturn


class ReturnItem(TenantScoped, Base):
    __tablename__ = "return_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="unit_price_nonnegative"),
        CheckConstraint("tax_refund_cents >= 0", name="tax_refund_nonnegative"),
        CheckConstraint("restocking_fee_cents >= 0", name="restocking_fee_nonnegative"),
        CheckConstraint("refund_cents >= 0", name="refund_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("returns.id"), index=True)
    sale_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sale_items.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("serial_numbers.id"),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    tax_refund_cents: Mapped[int] = mapped_column(Integer)
    restocking_fee_cents: Mapped[int] = mapped_column(Integer)
    refund_cents: Mapped[int] = mapped_column(Integer)
    condition_status: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str] = mapped_column(String(32))
    sale_return: Mapped[SaleReturn] = relationship("SaleReturn", back_populates="items")
    product: Mapped[Product] = relationship()
