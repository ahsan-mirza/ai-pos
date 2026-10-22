from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class ConsignmentItemOut(ApiModel):
    batch_item_id: UUID
    batch_id: UUID
    batch_number: str
    store_code: str
    product_id: UUID
    sku: str
    name: str
    received: int
    on_hand: int
    sold: int
    settled: int
    unsettled: int
    unit_cost_cents: int
    unsettled_cents: int


class ConsignmentSupplierOut(ApiModel):
    supplier_id: UUID
    supplier_name: str
    batches: int
    units_on_hand: int
    value_on_hand_cents: int
    units_sold: int
    unsettled_units: int
    unsettled_cents: int
    settled_cents: int
    items: list[ConsignmentItemOut]


class ConsignmentOverview(ApiModel):
    currency: str
    units_on_hand: int
    value_on_hand_cents: int
    unsettled_cents: int
    suppliers: list[ConsignmentSupplierOut]


class SettlementCreate(ApiModel):
    supplier_id: UUID
    bill_date: date | None = None
    note: str = Field(default="", max_length=255)


class SettlementOut(ApiModel):
    id: UUID
    number: str
    supplier_id: UUID
    supplier_name: str
    store_code: str
    period_end: date
    units: int
    total_cents: int
    bill_id: UUID
    bill_total_cents: int
    bill_status: str
    created_at: datetime
