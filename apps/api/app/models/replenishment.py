from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, utcnow


class DemandDaily(TenantScoped, Base):
    """Net units sold per product, branch, and day (sales minus returns). Rebuilt nightly for recent days."""

    __tablename__ = "demand_daily"
    __table_args__ = (PrimaryKeyConstraint("product_id", "store_id", "day", name="pk_demand_daily"),)

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    units: Mapped[int] = mapped_column(Integer, default=0)


class SeasonalEvent(TenantScoped, TimestampMixin, Base):
    """A known demand swing (Ramadan, Eid, back to school, DSF). Multiplies forecast demand on its days."""

    __tablename__ = "seasonal_events"
    __table_args__ = (CheckConstraint("uplift_bps >= 0 AND uplift_bps <= 100000", name="uplift_range"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    # 13000 = demand at 130% of normal.
    uplift_bps: Mapped[int] = mapped_column(Integer, default=10000)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReplenishmentRun(TenantScoped, Base):
    __tablename__ = "replenishment_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    review_days: Mapped[int] = mapped_column(Integer, default=7)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReplenishmentSuggestion(TenantScoped, Base):
    __tablename__ = "replenishment_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("replenishment_runs.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    # PURCHASE from a supplier, or TRANSFER from a branch / warehouse with surplus.
    source: Mapped[str] = mapped_column(String(12))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    from_store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    on_hand: Mapped[int] = mapped_column(Integer)
    on_order: Mapped[int] = mapped_column(Integer)
    # Forecast daily demand in thousandths of a unit, so slow movers are not rounded to zero.
    daily_rate_milli: Mapped[int] = mapped_column(Integer)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    forecast_units: Mapped[int] = mapped_column(Integer)
    safety_stock: Mapped[int] = mapped_column(Integer)
    suggested_qty: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    seasonal_note: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # services.forecasting method picked by backtest, its accuracy (1 - WAPE) in basis points, and the weekly trend.
    forecast_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    forecast_accuracy_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trend_pct_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How supplier terms shaped the quantity or timing, e.g. "MOQ 50 · cases of 12 · next order day Wed".
    terms_note: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # PENDING -> ACCEPTED (became a draft PO or transfer) or DISMISSED
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True
    )
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stock_transfers.id"), nullable=True
    )
