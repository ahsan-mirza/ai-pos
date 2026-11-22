"""Laundry catalog requests. Tenant and branch come from the session, not the body."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class LaundrySettingsIn(ApiModel):
    operating_modes: list[str] = Field(default_factory=list)
    tracking_mode: str = "individual"
    weight_precision: int = 3
    express_daily_capacity: int | None = None


class LaundrySettingsOut(ApiModel):
    operating_modes: list[str]
    tracking_mode: str
    weight_precision: int
    express_daily_capacity: int | None


class NamedIn(ApiModel):
    code: str
    name: str


class NamedOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class ServiceIn(ApiModel):
    category_id: uuid.UUID
    code: str
    name: str
    pricing_unit: str
    base_rate_cents: int = 0
    min_charge_cents: int = 0
    min_quantity: int = 0
    weight_precision: int = 0
    express_surcharge_cents: int | None = None
    same_day_surcharge_cents: int | None = None
    special_surcharge_cents: int | None = None
    tax_category: str = "STANDARD"
    price_includes_tax: bool = False
    allow_zero_rate: bool = False
    turnaround_minutes: int = 1440
    workflow_code: str = ""
    garment_type_ids: list[uuid.UUID] = Field(default_factory=list)


class ServiceOut(ApiModel):
    id: uuid.UUID
    category_id: uuid.UUID
    code: str
    name: str
    pricing_unit: str
    base_rate_cents: int
    min_charge_cents: int
    min_quantity: int
    weight_precision: int
    express_surcharge_cents: int | None
    tax_category: str
    is_active: bool
    workflow_code: str


class ServicePatch(ApiModel):
    name: str | None = None
    base_rate_cents: int | None = None
    min_charge_cents: int | None = None
    min_quantity: int | None = None
    weight_precision: int | None = None
    express_surcharge_cents: int | None = None
    is_active: bool | None = None
    allow_zero_rate: bool | None = None


class BranchCapacityIn(ApiModel):
    express_daily_capacity: int | None = None


class BranchCapacityOut(ApiModel):
    id: uuid.UUID
    store_id: uuid.UUID
    express_daily_capacity: int | None


class PriceListIn(ApiModel):
    code: str
    name: str
    kind: str
    store_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class PriceListOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    store_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    valid_from: date | None
    valid_to: date | None
    is_active: bool


class RateIn(ApiModel):
    service_id: uuid.UUID
    unit_price_cents: int


class QuoteIn(ApiModel):
    service_id: uuid.UUID
    quantity: int
    on: date
    store_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    price_list_id: uuid.UUID | None = None
    extras_cents: int = 0
    express: bool = False
    same_day: bool = False
    special: bool = False
    discount_cents: int = 0


class QuoteOut(ApiModel):
    unit: str
    quantity: int
    unit_price_cents: int
    extras_cents: int
    surcharge_cents: int
    discount_cents: int
    merchandise_cents: int
    minimum_charge_applied: bool
    tax_category: str
    rate_bps: int
    net_cents: int
    tax_cents: int
    total_cents: int
    price_list_id: uuid.UUID | None
