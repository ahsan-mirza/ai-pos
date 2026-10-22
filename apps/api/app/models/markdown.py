"""Scheduled markdowns and the retail price history they (and manual edits) write."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin

STATUSES = ("SCHEDULED", "ACTIVE", "ENDED", "CANCELLED")
REASONS = ("MANUAL", "MARKDOWN", "IMPORT", "BULK")


class MarkdownEvent(TimestampMixin, Base):
    """A catalogue-wide retail markdown. Prices live on the product, so an event applies to every branch."""

    __tablename__ = "markdown_events"
    __table_args__ = (
        CheckConstraint("status IN ('SCHEDULED', 'ACTIVE', 'ENDED', 'CANCELLED')", name="markdown_status"),
        CheckConstraint("(percent_bps IS NOT NULL) <> (price_cents IS NOT NULL)", name="markdown_one_price_rule"),
        CheckConstraint("ends_at > starts_at", name="markdown_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    # {model_ids, category_ids, product_ids, season, collection}; at least one constraint is required.
    scope: Mapped[dict] = mapped_column(JSON)
    percent_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED", index=True)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PriceChange(TimestampMixin, Base):
    """One retail price movement: a markdown, its restore, or a manual edit."""

    __tablename__ = "price_changes"
    __table_args__ = (
        CheckConstraint("reason IN ('MANUAL', 'MARKDOWN', 'IMPORT', 'BULK')", name="price_change_reason"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    old_price_cents: Mapped[int] = mapped_column(Integer)
    new_price_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(16))
    markdown_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("markdown_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
