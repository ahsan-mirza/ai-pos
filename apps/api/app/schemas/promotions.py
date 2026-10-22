from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.payloads import ApiModel

PromotionKind = Literal["PERCENT_OFF", "BUY_X_GET_Y", "MIX_MATCH", "BUNDLE"]


class BundleComponent(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)


class PromotionWrite(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=255)
    kind: PromotionKind
    product_ids: list[UUID] = Field(default_factory=list, max_length=500)
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    store_ids: list[UUID] = Field(default_factory=list, max_length=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True
    coupon_code: str | None = Field(default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9-]+$")
    max_uses: int | None = Field(default=None, ge=1, le=10_000_000)
    min_spend_cents: int = Field(default=0, ge=0, le=100_000_000)
    percent_bps: int | None = Field(default=None, ge=1, le=10_000)
    buy_qty: int | None = Field(default=None, ge=1, le=100)
    get_qty: int | None = Field(default=None, ge=1, le=100)
    get_discount_bps: int | None = Field(default=None, ge=1, le=10_000)
    group_qty: int | None = Field(default=None, ge=2, le=100)
    group_price_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    components: list[BundleComponent] | None = Field(default=None, max_length=10)
    bundle_price_cents: int | None = Field(default=None, ge=0, le=100_000_000)

    @field_validator("coupon_code")
    @classmethod
    def upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def kind_params(self) -> Self:
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("The promotion must end after it starts.")
        required = {
            "PERCENT_OFF": ("percent_bps",),
            "BUY_X_GET_Y": ("buy_qty", "get_qty"),
            "MIX_MATCH": ("group_qty", "group_price_cents"),
            "BUNDLE": ("components", "bundle_price_cents"),
        }[self.kind]
        missing = [name for name in required if getattr(self, name) in (None, [])]
        if missing:
            raise ValueError(f"{self.kind.replace('_', ' ').title()} needs {', '.join(missing)}.")
        if self.kind == "BUNDLE" and len(self.components or []) < 2:
            raise ValueError("A bundle needs at least two products.")
        return self


class PromotionOut(ApiModel):
    id: UUID
    name: str
    description: str
    kind: PromotionKind
    product_ids: list[str]
    category_ids: list[str]
    store_ids: list[str]
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    coupon_code: str | None
    max_uses: int | None
    uses_count: int
    discount_given_cents: int
    min_spend_cents: int
    percent_bps: int | None
    buy_qty: int | None
    get_qty: int | None
    get_discount_bps: int | None
    group_qty: int | None
    group_price_cents: int | None
    components: list[dict] | None
    bundle_price_cents: int | None
    # Names for product_ids and bundle components, for display.
    product_names: dict[str, str] = Field(default_factory=dict)
