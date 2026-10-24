"""Customer groups, price lists (customer, group, store or business-wide) and scheduled price changes.

A price list item is a fixed price or a discount off the tier price, from a minimum quantity, with optional volume
breaks. The resolver (services.pricing.resolve_with_lists, mirrored in shared-types) picks the lowest valid price."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

PRICE_LIST_SCOPES = ("customer", "group", "store", "global")
PRICE_CHANGE_STATUSES = ("SCHEDULED", "APPLIED", "CANCELLED")
TAX_TREATMENTS = ("STANDARD", "ZERO_EXPORT", "EXEMPT", "DESIGNATED_ZONE")


class CustomerGroup(TenantScoped, TimestampMixin, Base):
    __tablename__ = "customer_groups"
    __table_args__ = (
        tenant_unique("name", name="uq_customer_groups_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    # Applied to members whose own tier is RETAIL (not set) on wholesale sales.
    default_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # A blanket discount off the tier price for every product, in basis points.
    default_discount_bps: Mapped[int] = mapped_column(Integer, default=0)
    payment_terms: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceList(TenantScoped, TimestampMixin, Base):
    __tablename__ = "price_lists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(10), index=True)
    # The customer, group or store; null for business-wide lists.
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Breaks ties between lists of the same scope offering the same price.
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[list[PriceListItem]] = relationship(
        "PriceListItem", cascade="all, delete-orphan", lazy="selectin", order_by="PriceListItem.product_id"
    )


class PriceListItem(TenantScoped, Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        tenant_unique("price_list_id", "product_id", name="uq_price_list_items_list_product"),
        CheckConstraint("(price_cents IS NULL) <> (discount_bps IS NULL)", name="price_or_discount"),
        CheckConstraint("min_qty >= 1", name="min_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    price_list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("price_lists.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_qty: Mapped[int] = mapped_column(Integer, default=1)
    # [{"min_qty": 50, "price_cents": 900}], in pieces.
    volume_breaks: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ScheduledPriceChange(TenantScoped, TimestampMixin, Base):
    """A batch of new retail / tier prices that the price_changes job applies at run_at."""

    __tablename__ = "scheduled_price_changes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(10), default="SCHEDULED", index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lines: Mapped[list[ScheduledPriceChangeLine]] = relationship(
        "ScheduledPriceChangeLine", cascade="all, delete-orphan", lazy="selectin"
    )


class ScheduledPriceChangeLine(TenantScoped, Base):
    __tablename__ = "scheduled_price_change_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scheduled_price_changes.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    retail_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {"TIER_1": 1200}: the tier's new price (its MOQ and breaks are kept).
    tier_prices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # What the product cost before the change was applied, for the audit trail and a manual revert.
    previous_retail_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_tier_prices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
