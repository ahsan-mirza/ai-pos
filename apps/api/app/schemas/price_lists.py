from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, PaymentTerms, PriceListEntryOut, PriceTier, VolumeBreak

PriceListScope = Literal["customer", "group", "store", "global"]
PriceChangeStatus = Literal["SCHEDULED", "APPLIED", "CANCELLED"]
TaxTreatment = Literal["STANDARD", "ZERO_EXPORT", "EXEMPT", "DESIGNATED_ZONE"]


class ProductEntriesOut(PriceListEntryOut):
    product_id: UUID | None


class CustomerPricingOut(ApiModel):
    """A customer's own and group price lists, for the register to cache when the customer is attached."""

    customer_id: UUID
    group_id: UUID | None
    tier: PriceTier
    tax_treatment: TaxTreatment
    tax_certificate_expiry: date | None
    # product_id null: applies to every product (the group's blanket discount).
    entries: list[ProductEntriesOut]
    fetched_at: datetime


class CustomerGroupIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    default_tier: PriceTier | None = None
    default_discount_bps: int = Field(default=0, ge=0, le=9_000)
    payment_terms: PaymentTerms | None = None
    is_active: bool = True


class CustomerGroupOut(CustomerGroupIn):
    id: UUID
    members: int
    price_lists: int


class PriceListItemIn(ApiModel):
    product_id: UUID
    price_cents: int | None = Field(default=None, ge=0)
    discount_bps: int | None = Field(default=None, ge=1, le=9_000)
    min_qty: int = Field(default=1, ge=1, le=1_000_000)
    volume_breaks: list[VolumeBreak] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def price_or_discount(self) -> Self:
        if (self.price_cents is None) == (self.discount_bps is None):
            raise ValueError("Give each item either a fixed price or a discount, not both.")
        return self


class PriceListItemOut(PriceListItemIn):
    sku: str
    name: str
    retail_price_cents: int


class PriceListIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    scope: PriceListScope
    scope_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    priority: int = Field(default=0, ge=-100, le=100)
    is_active: bool = True

    @model_validator(mode="after")
    def scope_target(self) -> Self:
        if (self.scope == "global") != (self.scope_id is None):
            raise ValueError("Business-wide lists have no target; customer, group and store lists need one.")
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("The list must end after it starts.")
        return self


class PriceListRow(PriceListIn):
    id: UUID
    currency: str
    scope_name: str | None
    items: int
    status: Literal["active", "scheduled", "expired", "off"]


class PriceListOut(PriceListRow):
    lines: list[PriceListItemOut]


class PriceListItemsIn(ApiModel):
    items: list[PriceListItemIn] = Field(max_length=5_000)


class CsvImportIn(ApiModel):
    """CSV with a header row: sku, price (in currency units) or discount_percent, min_qty (optional)."""

    csv: str = Field(min_length=1, max_length=2_000_000)
    replace: bool = False


class CsvImportResult(ApiModel):
    imported: int
    skipped: list[str]


class PriceChangeLineIn(ApiModel):
    product_id: UUID
    retail_price_cents: int | None = Field(default=None, ge=0)
    tier_prices: dict[PriceTier, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def something_changes(self) -> Self:
        if self.retail_price_cents is None and not self.tier_prices:
            raise ValueError("Each line needs a new retail or tier price.")
        if any(price < 0 for price in self.tier_prices.values()):
            raise ValueError("Prices cannot be negative.")
        return self


class PriceChangeIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    run_at: datetime
    note: str = Field(default="", max_length=255)
    lines: list[PriceChangeLineIn] = Field(min_length=1, max_length=5_000)


class PriceChangeLineOut(ApiModel):
    product_id: UUID
    sku: str
    name: str
    current_retail_cents: int
    retail_price_cents: int | None
    current_tier_prices: dict[str, int]
    tier_prices: dict[str, int]
    previous_retail_cents: int | None
    previous_tier_prices: dict[str, int] | None


class PriceChangeOut(ApiModel):
    id: UUID
    name: str
    run_at: datetime
    status: PriceChangeStatus
    note: str
    created_by_name: str | None
    applied_at: datetime | None
    lines: list[PriceChangeLineOut]
