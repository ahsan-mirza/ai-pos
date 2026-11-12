"""Delivery zones, vehicles, drivers, and manual dispatch plans.

These hang off a sales order. They do not create a second order, and they do not
invoice, take payment, or mark a delivery as out for delivery.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class DeliveryZone(TenantScoped, TimestampMixin, Base):
    __tablename__ = "delivery_zones"
    __table_args__ = (tenant_unique("store_id", "code", name="uq_delivery_zones_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Stored for the branch. It is not added to an invoice.
    fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DeliveryZoneSlot(TenantScoped, Base):
    """A local time of day, on one weekday, when this zone accepts a delivery window."""

    __tablename__ = "delivery_zone_slots"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_zones.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FleetVehicle(TenantScoped, TimestampMixin, Base):
    __tablename__ = "fleet_vehicles"
    __table_args__ = (
        tenant_unique("store_id", "code", name="uq_fleet_vehicles_code"),
        CheckConstraint(
            "availability IN ('AVAILABLE', 'ON_ROUTE', 'OFF_DUTY')",
            name="availability",
        ),
        CheckConstraint(
            "maintenance_status IN ('NONE', 'DUE', 'IN_SHOP')",
            name="maintenance",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    registration: Mapped[str] = mapped_column(String(24))
    vehicle_type: Mapped[str] = mapped_column(String(40))
    # Null means the limit is unknown. It is not zero and it is not unlimited.
    max_weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(8), default="kg")
    max_volume_cm3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume_unit: Mapped[str] = mapped_column(String(8), default="m3")
    availability: Mapped[str] = mapped_column(String(16), default="AVAILABLE")
    maintenance_status: Mapped[str] = mapped_column(String(16), default="NONE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class DriverProfile(TenantScoped, TimestampMixin, Base):
    """A driver linked to an existing user. The name stays on the user."""

    __tablename__ = "driver_profiles"
    __table_args__ = (tenant_unique("user_id", name="uq_driver_profiles_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    license_number: Mapped[str] = mapped_column(String(40), default="")
    license_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    availability: Mapped[str] = mapped_column(String(16), default="AVAILABLE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DispatchPlan(TenantScoped, TimestampMixin, Base):
    __tablename__ = "dispatch_plans"
    __table_args__ = (
        tenant_unique("number", name="uq_dispatch_plans_number"),
        CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')",
            name="status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("fleet_vehicles.id"), index=True)
    driver_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    notes: Mapped[str] = mapped_column(Text, default="")
    capacity_override_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DispatchAssignment(TenantScoped, Base):
    __tablename__ = "dispatch_assignments"
    __table_args__ = (UniqueConstraint("plan_id", "order_id", name="uq_dispatch_assignments_order"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dispatch_plans.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales_orders.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
