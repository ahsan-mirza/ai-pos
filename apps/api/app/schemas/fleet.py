from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

SchedulingStatus = Literal["UNSCHEDULED", "SCHEDULED", "CANCELLED"]
VehicleAvailability = Literal["AVAILABLE", "ON_ROUTE", "OFF_DUTY"]
MaintenanceStatus = Literal["NONE", "DUE", "IN_SHOP"]
DriverAvailability = Literal["AVAILABLE", "ON_ROUTE", "OFF_DUTY"]
PlanStatus = Literal["DRAFT", "CONFIRMED", "CANCELLED"]
FleetView = Literal[
    "unscheduled",
    "scheduled",
    "unassigned",
    "assigned",
    "dispatched",
    "delivered",
    "exceptions",
]
WeightUnit = Literal["g", "kg"]
VolumeUnit = Literal["cm3", "l", "m3"]


class ScheduleIn(ApiModel):
    promised_on: date | None = None
    window_start: time | None = None
    window_end: time | None = None
    delivery_zone_id: UUID | None = None
    delivery_address: str | None = Field(default=None, max_length=255)
    delivery_instructions: str | None = Field(default=None, max_length=500)
    requested_date: date | None = None


class ZoneIn(ApiModel):
    store_id: UUID
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    is_active: bool = True
    fee_cents: int | None = Field(default=None, ge=0)


class ZoneUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    fee_cents: int | None = Field(default=None, ge=0)
    clear_fee: bool = False


class SlotIn(ApiModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    is_active: bool = True


class ZoneOut(ApiModel):
    id: UUID
    store_id: UUID
    code: str
    name: str
    description: str
    is_active: bool
    fee_cents: int | None
    slots: list["SlotOut"]


class SlotOut(ApiModel):
    id: UUID
    weekday: int
    start_time: time
    end_time: time
    is_active: bool


class VehicleIn(ApiModel):
    store_id: UUID
    code: str = Field(min_length=1, max_length=16)
    registration: str = Field(min_length=1, max_length=24)
    vehicle_type: str = Field(min_length=1, max_length=40)
    weight_amount: Decimal | None = Field(default=None, ge=0)
    weight_unit: WeightUnit = "kg"
    volume_amount: Decimal | None = Field(default=None, ge=0)
    volume_unit: VolumeUnit = "m3"
    availability: VehicleAvailability = "AVAILABLE"
    maintenance_status: MaintenanceStatus = "NONE"
    is_active: bool = True
    notes: str = Field(default="", max_length=2000)


class VehicleUpdate(ApiModel):
    registration: str | None = Field(default=None, min_length=1, max_length=24)
    vehicle_type: str | None = Field(default=None, min_length=1, max_length=40)
    weight_amount: Decimal | None = Field(default=None, ge=0)
    weight_unit: WeightUnit | None = None
    volume_amount: Decimal | None = Field(default=None, ge=0)
    volume_unit: VolumeUnit | None = None
    clear_weight: bool = False
    clear_volume: bool = False
    availability: VehicleAvailability | None = None
    maintenance_status: MaintenanceStatus | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class VehicleOut(ApiModel):
    id: UUID
    store_id: UUID
    code: str
    registration: str
    vehicle_type: str
    max_weight_grams: int | None
    weight_unit: str
    weight_amount: str | None
    max_volume_cm3: int | None
    volume_unit: str
    volume_amount: str | None
    availability: str
    maintenance_status: str
    is_active: bool
    notes: str


class DriverIn(ApiModel):
    user_id: UUID
    store_id: UUID
    phone: str = Field(default="", max_length=40)
    license_number: str = Field(default="", max_length=40)
    license_expiry: date | None = None
    availability: DriverAvailability = "AVAILABLE"
    is_active: bool = True


class DriverUpdate(ApiModel):
    phone: str | None = Field(default=None, max_length=40)
    license_number: str | None = Field(default=None, max_length=40)
    license_expiry: date | None = None
    clear_license_expiry: bool = False
    availability: DriverAvailability | None = None
    is_active: bool | None = None


class DriverOut(ApiModel):
    id: UUID
    user_id: UUID
    name: str
    store_id: UUID
    phone: str
    license_number: str | None
    license_on_file: bool
    license_expiry: date | None
    availability: str
    is_active: bool


class PlanIn(ApiModel):
    store_id: UUID
    service_date: date
    vehicle_id: UUID
    driver_user_id: UUID
    order_ids: list[UUID] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=2000)


class PlanUpdate(ApiModel):
    vehicle_id: UUID | None = None
    driver_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AssignIn(ApiModel):
    order_id: UUID


class ConfirmIn(ApiModel):
    override: bool = False
    reason: str | None = Field(default=None, max_length=240)


class CapacityOut(ApiModel):
    cargo_weight_grams: int | None
    cargo_volume_cm3: int | None
    cargo_weight_incomplete: bool
    cargo_volume_incomplete: bool
    vehicle_weight_grams: int | None
    vehicle_volume_cm3: int | None
    remaining_weight_grams: int | None
    remaining_volume_cm3: int | None
    weight_over: bool
    volume_over: bool
    blocked: bool
    policy: str


class AssignmentOut(ApiModel):
    order_id: UUID
    order_number: str
    customer_name: str
    position: int
    cargo_weight_grams: int | None
    cargo_volume_cm3: int | None
    cargo_weight_incomplete: bool
    cargo_volume_incomplete: bool


class PlanOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    service_date: date
    vehicle_id: UUID
    vehicle_code: str
    driver_user_id: UUID
    driver_name: str
    status: str
    notes: str
    capacity_override_by_id: UUID | None
    confirmed_at: datetime | None
    timezone: str
    assignments: list[AssignmentOut]
    capacity: CapacityOut


class FleetOrderRow(ApiModel):
    id: UUID
    number: str
    customer_name: str
    status: str
    scheduling_status: str
    requested_date: date | None
    promised_on: date | None
    window_start: time | None
    window_end: time | None
    delivery_zone_id: UUID | None
    zone_name: str | None
    delivery_address: str | None
    store_id: UUID
    plan_id: UUID | None
    plan_number: str | None
    plan_status: str | None
    cargo_weight_incomplete: bool
    cargo_volume_incomplete: bool


class PolicyUpdate(ApiModel):
    policy: Literal["block"]


class PolicyOut(ApiModel):
    policy: Literal["block"]
    timezone: str
