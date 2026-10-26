"""Customer-specific recurring reorder reminders. A due plan opens an alert; it does not confirm a sale."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

PLAN_STATUSES = ("ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED")
FREQUENCIES = ("DAILY", "WEEKLY", "MONTHLY", "CUSTOM_DAYS")
FULFILLMENT = ("DELIVERY", "COLLECTION")
OCCURRENCE_STATUSES = ("PENDING", "SNOOZED", "SKIPPED", "ORDERED", "DELIVERED")


class CustomerReorderPlan(TenantScoped, TimestampMixin, Base):
    __tablename__ = "customer_reorder_plans"
    __table_args__ = (
        Index("ix_reorder_plans_due", "tenant_id", "status", "next_on"),
        Index("ix_reorder_plans_customer", "tenant_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    frequency: Mapped[str] = mapped_column(String(16))
    weekdays: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_on: Mapped[date] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Dubai")
    lead_days: Mapped[int] = mapped_column(Integer, default=0)
    fulfillment: Mapped[str] = mapped_column(String(16), default="DELIVERY")
    delivery_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    salesperson_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    notify_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)

    customer = relationship("Customer")
    salesperson = relationship("User", foreign_keys=[salesperson_id])
    items: Mapped[list[CustomerReorderPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="CustomerReorderPlanItem.position"
    )
    occurrences: Mapped[list[CustomerReorderOccurrence]] = relationship(back_populates="plan")


class CustomerReorderPlanItem(TenantScoped, Base):
    __tablename__ = "customer_reorder_plan_items"
    __table_args__ = (Index("ix_reorder_items_plan", "tenant_id", "plan_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_reorder_plans.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(16), default="PIECE")
    note: Mapped[str | None] = mapped_column(String(160), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[CustomerReorderPlan] = relationship(back_populates="items")
    product = relationship("Product")


class CustomerReorderOccurrence(TenantScoped, Base):
    __tablename__ = "customer_reorder_occurrences"
    __table_args__ = (
        tenant_unique("plan_id", "scheduled_on", name="uq_reorder_occurrences_plan_day"),
        Index("ix_reorder_occurrences_due", "tenant_id", "status", "scheduled_on"),
        Index("ix_reorder_occurrences_order", "tenant_id", "sales_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_reorder_plans.id"), index=True
    )
    scheduled_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_orders.id"), nullable=True
    )
    notification_status: Mapped[str] = mapped_column(String(16), default="PENDING")
    notification_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stock_note: Mapped[str] = mapped_column(String(500), default="")
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[CustomerReorderPlan] = relationship(back_populates="occurrences")
    sales_order = relationship("SalesOrder")
