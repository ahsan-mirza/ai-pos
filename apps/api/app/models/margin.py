from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class MarginPolicy(TenantScoped, TimestampMixin, Base):
    """Minimum margin over cost. The most specific active policy wins: product, then category, then global."""

    __tablename__ = "margin_policies"
    __table_args__ = (
        tenant_unique("scope", "category_id", "product_id", name="uq_margin_policy_target"),
        CheckConstraint("min_margin_bps >= 0 AND min_margin_bps <= 100000", name="margin_bps_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(12))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True
    )
    min_margin_bps: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
