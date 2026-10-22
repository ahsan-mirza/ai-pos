from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel

MarginScope = Literal["GLOBAL", "CATEGORY", "PRODUCT"]


class FloorOut(ApiModel):
    product_id: UUID
    floor_cents: int
    cost_cents: int
    cost_estimated: bool
    min_margin_bps: int


class MarginPolicyWrite(ApiModel):
    scope: MarginScope
    category_id: UUID | None = None
    product_id: UUID | None = None
    min_margin_bps: int = Field(ge=0, le=100_000)
    is_active: bool = True

    @model_validator(mode="after")
    def target(self) -> Self:
        if self.scope == "CATEGORY" and self.category_id is None:
            raise ValueError("Category policies need a category.")
        if self.scope == "PRODUCT" and self.product_id is None:
            raise ValueError("Product policies need a product.")
        return self


class MarginPolicyOut(ApiModel):
    id: UUID
    scope: MarginScope
    category_id: UUID | None
    category_name: str | None
    product_id: UUID | None
    product_name: str | None
    min_margin_bps: int
    is_active: bool


class MarginExceptionOut(ApiModel):
    sale_id: UUID
    invoice: str
    store_code: str
    sold_at: datetime
    product_name: str
    quantity: int
    unit_price_cents: int
    floor_cents: int
    shortfall_cents: int
    cashier_name: str | None
    approved_by_name: str | None
    currency: str


class MarginExceptionList(ApiModel):
    total_shortfall_cents: int
    exceptions: list[MarginExceptionOut]
