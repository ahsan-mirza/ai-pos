from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

PROMOTION_KINDS = ("PERCENT_OFF", "BUY_X_GET_Y", "MIX_MATCH", "BUNDLE")


class Promotion(TenantScoped, TimestampMixin, Base):
    """A retail promotion. `params` holds the kind's numbers (see services/promotion_engine.Rule); eligibility is
    product_ids / category_ids (empty = every product). Coupon promotions apply only when the code is entered."""

    __tablename__ = "promotions"
    __table_args__ = (
        tenant_unique("coupon_code", name="uq_promotions_coupon_code"),
        CheckConstraint("min_spend_cents >= 0", name="promotion_min_spend_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(12))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    product_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    category_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    store_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    coupon_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PromotionRedemption(TenantScoped, Base):
    """One sale that used a promotion, with the discount it gave. Counts coupon uses."""

    __tablename__ = "promotion_redemptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("promotions.id"), index=True)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    discount_cents: Mapped[int] = mapped_column(Integer)
    coupon_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
