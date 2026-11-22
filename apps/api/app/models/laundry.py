"""Laundry catalog. Garments in process are not inventory quantities."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

OPERATING_MODES = (
    "DRY_CLEANING",
    "WASH_AND_FOLD",
    "WASH_AND_IRON",
    "PRESSING_ONLY",
    "ALTERATIONS",
    "COMMERCIAL_LAUNDRY",
    "SELF_SERVICE_LAUNDROMAT",
    "PICKUP_AND_DELIVERY",
    "CENTRAL_PLANT",
)
TRACKING_MODES = ("individual", "bag", "bulk")
PRICE_LIST_KINDS = ("standard", "premium", "express", "branch", "customer", "corporate")


class LaundrySettings(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_laundry_settings_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operating_modes: Mapped[list] = mapped_column(JSON, default=list)
    tracking_mode: Mapped[str] = mapped_column(String(16), default="individual")
    weight_precision: Mapped[int] = mapped_column(Integer, default=3)
    express_daily_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LaundryServiceCategory(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_service_categories"
    __table_args__ = (tenant_unique("code", name="uq_laundry_service_categories_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LaundryGarmentType(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_garment_types"
    __table_args__ = (tenant_unique("code", name="uq_laundry_garment_types_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LaundryService(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_services"
    __table_args__ = (
        tenant_unique("code", name="uq_laundry_services_code"),
        CheckConstraint("base_rate_cents >= 0", name="rate"),
        CheckConstraint("min_charge_cents >= 0", name="min_charge"),
        CheckConstraint("min_quantity >= 0", name="min_quantity"),
        CheckConstraint("weight_precision >= 0 AND weight_precision <= 3", name="precision"),
        CheckConstraint("turnaround_minutes >= 0", name="turnaround"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laundry_service_categories.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    pricing_unit: Mapped[str] = mapped_column(String(20))
    base_rate_cents: Mapped[int] = mapped_column(Integer, default=0)
    min_charge_cents: Mapped[int] = mapped_column(Integer, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0)
    weight_precision: Mapped[int] = mapped_column(Integer, default=3)
    express_surcharge_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    same_day_surcharge_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    special_surcharge_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_category: Mapped[str] = mapped_column(String(16), default="STANDARD")
    price_includes_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_zero_rate: Mapped[bool] = mapped_column(Boolean, default=False)
    turnaround_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    workflow_code: Mapped[str] = mapped_column(String(40), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LaundryServiceGarment(Base, TenantScoped):
    __tablename__ = "laundry_service_garments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_id", "garment_type_id", name="uq_laundry_service_garments"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laundry_services.id", ondelete="CASCADE"))
    garment_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laundry_garment_types.id"))


class LaundryPriceList(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_price_lists"
    __table_args__ = (tenant_unique("code", name="uq_laundry_price_lists_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LaundryPriceRate(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_price_rates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "price_list_id", "service_id", name="uq_laundry_price_rates_service"),
        CheckConstraint("unit_price_cents >= 0", name="rate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    price_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laundry_price_lists.id", ondelete="CASCADE"))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("laundry_services.id"))
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class LaundryBranchCapacity(Base, TenantScoped, TimestampMixin):
    """Express capacity for one branch. A missing row uses the tenant setting."""

    __tablename__ = "laundry_branch_capacities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "store_id", name="uq_laundry_branch_capacities"),
        CheckConstraint(
            "express_daily_capacity IS NULL OR express_daily_capacity >= 0",
            name="express",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    express_daily_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LaundryWorkflowTemplate(Base, TenantScoped, TimestampMixin):
    __tablename__ = "laundry_workflow_templates"
    __table_args__ = (tenant_unique("code", name="uq_laundry_workflow_templates_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    stages: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
