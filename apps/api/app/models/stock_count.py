from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

COUNT_STATUSES = ("OPEN", "SUBMITTED", "POSTED", "CANCELLED")


class StockCount(TenantScoped, TimestampMixin, Base):
    """A counting session at one branch: OPEN while staff count, SUBMITTED for review, POSTED once the
    variances are booked to the stock ledger."""

    __tablename__ = "stock_counts"
    __table_args__ = (
        tenant_unique("number", name="uq_stock_counts_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    product_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_models.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(10), default="OPEN", index=True)
    # Counters do not see system quantities while counting; reviewers with inventory:adjust_stock always do.
    blind: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lines: Mapped[list[StockCountLine]] = relationship(
        "StockCountLine", lazy="selectin", cascade="all, delete-orphan", order_by="StockCountLine.created_at"
    )


class StockCountLine(TenantScoped, TimestampMixin, Base):
    """expected_qty is the branch on-hand at the moment the line was counted, so sales made during the
    count do not show up as variance."""

    __tablename__ = "stock_count_lines"
    __table_args__ = (
        tenant_unique("count_id", "product_id", name="uq_stock_count_lines_count_product"),
        CheckConstraint("counted_qty IS NULL OR counted_qty >= 0", name="counted_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    count_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stock_counts.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    expected_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Serialized products are counted by scanning. Units are kept as {"hash", "tail"}: the identifier hash used
    # by serial_numbers and its last four characters for display, never the full IMEI.
    scanned_serials: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    # Filled when the count is posted: {"missing": [tails], "unexpected": [tails]}.
    serial_result: Mapped[dict[str, list[str]] | None] = mapped_column(JSON, nullable=True)
    counted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
