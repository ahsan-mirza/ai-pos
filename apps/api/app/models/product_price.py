from __future__ import annotations

import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProductPrice(TimestampMixin, Base):
    """Price for one product at one customer tier. RETAIL falls back to products.price_cents when absent.

    volume_discounts is a list of {"min_qty": int, "price_cents": int} breaks, counted in pieces."""

    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "price_tier", name="uq_product_prices_product_tier"),
        CheckConstraint("price_cents >= 0", name="price_nonnegative"),
        CheckConstraint("min_order_quantity >= 1", name="moq_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    price_tier: Mapped[str] = mapped_column(String(16))
    price_cents: Mapped[int] = mapped_column(Integer)
    min_order_quantity: Mapped[int] = mapped_column(Integer, default=1)
    volume_discounts: Mapped[list[dict[str, int]]] = mapped_column(JSON, default=list)
