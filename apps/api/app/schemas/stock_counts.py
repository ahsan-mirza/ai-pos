from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, SerialKind

StockCountStatus = Literal["OPEN", "SUBMITTED", "POSTED", "CANCELLED"]


class StockCountCreate(ApiModel):
    store_id: UUID
    category_id: UUID | None = None
    product_model_id: UUID | None = None
    blind: bool = True
    note: str = Field(default="", max_length=255)


class CountedSerial(ApiModel):
    kind: SerialKind
    value: str = Field(min_length=4, max_length=64)


class StockCountEntry(ApiModel):
    """counted_qty for stock items; serialized products send the units scanned instead."""

    product_id: UUID
    counted_qty: int | None = Field(default=None, ge=0, le=1_000_000)
    serials: list[CountedSerial] | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def one_measure(self) -> "StockCountEntry":
        if (self.counted_qty is None) == (self.serials is None):
            raise ValueError("Send counted_qty for stock items or serials for serialized products.")
        return self


class StockCountEntries(ApiModel):
    entries: list[StockCountEntry] = Field(min_length=1, max_length=2000)


class StockCountLineOut(ApiModel):
    product_id: UUID
    sku: str
    name: str
    barcode: str
    is_serialized: bool
    counted_qty: int | None
    # Hidden (null) from counters while a blind count is open.
    expected_qty: int | None
    variance: int | None
    variance_value_cents: int | None
    scanned_tails: list[str]
    missing_serials: list[str] | None
    unexpected_serials: list[str] | None
    counted_by_name: str | None
    counted_at: datetime | None


class StockCountOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    store_name: str
    category_id: UUID | None
    category_name: str | None
    product_model_id: UUID | None = None
    status: StockCountStatus
    blind: bool
    note: str
    can_review: bool
    created_by_name: str | None
    created_at: datetime
    submitted_at: datetime | None
    closed_at: datetime | None
    lines_total: int
    lines_counted: int
    net_variance: int | None
    variance_value_cents: int | None
    lines: list[StockCountLineOut]


class StockCountSummary(ApiModel):
    id: UUID
    number: str
    store_name: str
    category_name: str | None
    status: StockCountStatus
    blind: bool
    created_by_name: str | None
    created_at: datetime
    closed_at: datetime | None
    lines_total: int
    lines_counted: int
    net_variance: int | None
    variance_value_cents: int | None
