"""Laundry order requests. Money is integer cents. The server total is authoritative."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class GarmentIn(ApiModel):
    service_id: uuid.UUID
    quantity: int = Field(ge=1)
    garment_type: str = ""
    description: str = ""
    brand: str = ""
    colour: str = ""
    fabric: str = ""
    size: str = ""
    instructions: str = ""
    condition: str = ""
    stains: str = ""
    pre_existing_damage: str = ""
    extras_cents: int = Field(default=0, ge=0)


class BagIn(ApiModel):
    service_id: uuid.UUID
    bag_type: str = "MIXED"
    gross_weight: int = Field(ge=0)
    tare_weight: int = Field(default=0, ge=0)
    scale_reference: str = ""
    extras_cents: int = Field(default=0, ge=0)


class DepositIn(ApiModel):
    amount_cents: int = Field(ge=1)
    method: str = Field(pattern=r"^(cash|card)$")
    shift_id: uuid.UUID | None = None


class OrderIn(ApiModel):
    id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=80)
    intake_store_id: uuid.UUID
    plant_store_id: uuid.UUID | None = None
    customer_id: uuid.UUID
    order_type: str = Field(pattern=r"^(WALK_IN|DROP_OFF|PICKUP)$")
    price_list_id: uuid.UUID | None = None
    promised_at: datetime | None = None
    express: bool = False
    instructions: str = ""
    discount_cents: int = Field(default=0, ge=0)
    garments: list[GarmentIn] = Field(default_factory=list)
    bags: list[BagIn] = Field(default_factory=list)
    deposit: DepositIn | None = None
    device_id: uuid.UUID | None = None


class QuantityChange(ApiModel):
    garment_id: uuid.UUID
    quantity: int = Field(ge=1)
    reason: str = ""
    version: int = Field(ge=1)


class GarmentPatch(ApiModel):
    garment_id: uuid.UUID
    version: int = Field(ge=1)
    description: str | None = None
    condition: str | None = None
    stains: str | None = None
    instructions: str | None = None
    service_id: uuid.UUID | None = None


class DepositPost(ApiModel):
    id: uuid.UUID
    amount_cents: int = Field(ge=1)
    method: str = Field(pattern=r"^(cash|card)$")
    version: int = Field(ge=1)
    shift_id: uuid.UUID | None = None


class CancelIn(ApiModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class ProductionIn(ApiModel):
    reason: str = Field(min_length=1, max_length=500)


class ScanIn(ApiModel):
    code: str = Field(min_length=1, max_length=40)
    order_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=8, max_length=80)
    device_id: uuid.UUID | None = None


class TagActionIn(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    device_id: uuid.UUID | None = None


class PhotoIn(ApiModel):
    mime: str
    content_base64: str = Field(min_length=8)
    garment_id: uuid.UUID | None = None


class OrderOut(ApiModel):
    id: uuid.UUID
    code: str
    idempotency_key: str
    intake_store_id: uuid.UUID
    customer_id: uuid.UUID
    order_type: str
    currency: str
    express: bool
    instructions: str
    garment_count: int
    bag_count: int
    measured_weight: int
    subtotal_cents: int
    discount_cents: int
    surcharge_cents: int
    tax_cents: int
    total_cents: int
    amount_paid_cents: int
    balance_due_cents: int
    payment_status: str
    operational_status: str
    collection_status: str
    claim_status: str
    pricing_snapshot: dict
    version: int
    promised_at: datetime | None = None


class GarmentOut(ApiModel):
    id: uuid.UUID
    service_id: uuid.UUID
    description: str
    quantity: int
    instructions: str
    condition: str
    stains: str
    pre_existing_damage: str
    stage: str
    exception_state: str
    line_snapshot: dict


class BagOut(ApiModel):
    id: uuid.UUID
    service_id: uuid.UUID
    bag_type: str
    gross_weight: int
    tare_weight: int
    net_weight: int
    line_snapshot: dict


class TagOut(ApiModel):
    id: uuid.UUID
    code: str
    order_id: uuid.UUID
    garment_id: uuid.UUID | None
    bag_id: uuid.UUID | None
    status: str


class EventOut(ApiModel):
    id: uuid.UUID
    kind: str
    from_status: str | None
    to_status: str | None
    reason: str
    created_at: datetime


class PhotoOut(ApiModel):
    id: uuid.UUID
    mime: str
    byte_size: int
    sha256: str
    garment_id: uuid.UUID | None
    created_at: datetime


class OrderDetail(OrderOut):
    garments: list[GarmentOut]
    bags: list[BagOut]
    tags: list[TagOut]
    events: list[EventOut]
    photos: list[PhotoOut]
