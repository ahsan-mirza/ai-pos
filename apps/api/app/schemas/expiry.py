from datetime import date
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class ExpiringRow(ApiModel):
    batch_item_id: UUID
    batch_number: str
    product_id: UUID
    product_name: str
    sku: str
    store_id: UUID
    store_code: str
    expiry_date: date
    # Negative once the batch has expired.
    days_left: int
    quantity_remaining: int
    unit_cost_cents: int
    value_cents: int
    expired: bool


class ExpiryWriteOff(ApiModel):
    batch_item_id: UUID
    # Units to write off; omitted writes off everything left on the line.
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    note: str | None = Field(default=None, max_length=500)


class ExpiryWriteOffOut(ApiModel):
    batch_item_id: UUID
    written_off: int
    quantity_remaining: int
