from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WarrantyPolicy(TimestampMixin, Base):
    """Standard (manufacturer or shop) cover for what is sold. Product beats category beats the default."""

    __tablename__ = "warranty_policies"
    __table_args__ = (CheckConstraint("months >= 0 AND months <= 120", name="warranty_months_range"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(12))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), nullable=True)
    months: Mapped[int] = mapped_column(Integer)
    terms: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WarrantyPlan(TimestampMixin, Base):
    """Extended cover sold at the till. Ringing up its service product extends the devices on the same sale."""

    __tablename__ = "warranty_plans"
    __table_args__ = (CheckConstraint("extra_months > 0 AND extra_months <= 60", name="plan_months_range"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    extra_months: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), unique=True)
    terms: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WarrantyRegistration(TimestampMixin, Base):
    """Cover for one sold unit, created automatically for serialized sale lines."""

    __tablename__ = "warranty_registrations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    sale_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sale_items.id"), unique=True)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("serial_numbers.id"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warranty_policies.id"), nullable=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warranty_plans.id"), nullable=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # ACTIVE, CLAIMED (a repair was booked under it), VOID (the unit was returned)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", index=True)
    claims: Mapped[int] = mapped_column(Integer, default=0)
    # SALE: cover on a unit sold here. REPAIR: our guarantee on the parts and labour of an invoiced repair,
    # found by the device's identifier even when the unit was bought elsewhere.
    kind: Mapped[str] = mapped_column(String(8), default="SALE", server_default="SALE")
    # No database foreign key: repair_tickets already points at warranty_registrations, and a second
    # constraint the other way is a cycle SQLite cannot drop. The migration adds the constraint on Postgres.
    repair_ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    identifier_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
