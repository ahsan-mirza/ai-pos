from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.payloads import ApiModel


class RunCreate(ApiModel):
    store_id: UUID
    review_days: int = Field(default=7, ge=1, le=60)
    split_by_size_curve: bool = False


class SuggestionOut(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    source: Literal["PURCHASE", "TRANSFER"]
    supplier_id: UUID | None
    supplier_name: str | None
    from_store_code: str | None
    on_hand: int
    on_order: int
    daily_rate: float
    lead_time_days: int
    forecast_units: int
    safety_stock: int
    suggested_qty: int
    unit_cost_cents: int
    seasonal_note: str | None
    terms_note: str | None = None
    forecast_method: str | None = None
    forecast_method_label: str | None = None
    #: Backtest accuracy 0-1 (1 - WAPE over the last 28 days); None with too little history.
    forecast_accuracy: float | None = None
    trend_pct_week: int | None = None
    status: Literal["PENDING", "ACCEPTED", "DISMISSED"]
    purchase_order_id: UUID | None
    transfer_id: UUID | None


class RunOut(ApiModel):
    id: UUID
    store_id: UUID
    store_code: str
    review_days: int
    created_at: datetime
    purchase_value_cents: int
    suggestions: list[SuggestionOut]


class AcceptLine(ApiModel):
    id: UUID
    quantity: int = Field(ge=0, le=100_000)


class AcceptRequest(ApiModel):
    lines: list[AcceptLine] = Field(min_length=1, max_length=500)


class AcceptResult(ApiModel):
    purchase_order_ids: list[UUID]
    transfer_ids: list[UUID]
    run: RunOut


class SeasonalEventWrite(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    starts_on: date
    ends_on: date
    uplift_bps: int = Field(ge=0, le=100_000)
    category_id: UUID | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.ends_on < self.starts_on:
            raise ValueError("The event ends before it starts.")
        return self


class SeasonalEventOut(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    starts_on: date
    ends_on: date
    uplift_bps: int
    category_id: UUID | None
    is_active: bool


Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class SupplierLeadOut(ApiModel):
    id: UUID
    name: str
    code: str
    lead_time_days: int
    moq: int = 1
    pack_size: int = 1
    order_days: list[Weekday] = Field(default_factory=list)


class SupplierTermsWrite(ApiModel):
    lead_time_days: int = Field(ge=0, le=365)
    moq: int = Field(default=1, ge=1, le=100_000)
    pack_size: int = Field(default=1, ge=1, le=10_000)
    order_days: list[Weekday] = Field(default_factory=list, max_length=7)


class LeadTimeWrite(ApiModel):
    lead_time_days: int = Field(ge=0, le=365)
