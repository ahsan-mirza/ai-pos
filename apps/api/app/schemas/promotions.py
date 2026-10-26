from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.payloads import ApiModel

PromotionKind = Literal["PERCENT_OFF", "BUY_X_GET_Y", "MIX_MATCH", "BUNDLE", "AMOUNT_OFF"]
CouponSegment = Literal["repeat", "win_back", "category", "basket", "milestone", "loyalty", "birthday"]


class BundleComponent(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)


class CustomerCouponOut(ApiModel):
    id: UUID
    code: str
    status: str
    reason: str
    issued_at: datetime
    expires_at: datetime | None
    min_spend_cents: int
    promotion_id: UUID
    promotion_name: str
    kind: str
    amount_cents: int | None = None
    percent_bps: int | None = None
    product_ids: list[str] = Field(default_factory=list)
    category_ids: list[str] = Field(default_factory=list)


class CouponReportOut(ApiModel):
    issued: int
    redeemed: int
    discount_cents: int
    sales: int


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
    amount_cents: int | None = Field(default=None, ge=1, le=100_000_000)
    max_discount_cents: int | None = Field(default=None, ge=1, le=100_000_000)
    customer_issued: bool = False
    segment: CouponSegment | None = None
    repeat_count: int | None = Field(default=None, ge=1, le=1000)
    window_days: int | None = Field(default=None, ge=1, le=3650)
    quiet_days: int | None = Field(default=None, ge=1, le=3650)
    visit_count: int | None = Field(default=None, ge=1, le=100_000)
    spend_cents: int | None = Field(default=None, ge=1, le=100_000_000_00)
    notify: bool = False

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
            "AMOUNT_OFF": ("amount_cents",),
        }[self.kind]
        missing = [name for name in required if getattr(self, name) in (None, [])]
        if missing:
            raise ValueError(f"{self.kind.replace('_', ' ').title()} needs {', '.join(missing)}.")
        if self.kind == "BUNDLE" and len(self.components or []) < 2:
            raise ValueError("A bundle needs at least two products.")
        if self.customer_issued and self.coupon_code:
            raise ValueError("A customer voucher uses its own code. Leave the shared coupon blank.")
        if self.customer_issued and self.segment is None:
            raise ValueError("Choose who receives this voucher.")
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
    percent_bps: int | None = None
    buy_qty: int | None = None
    get_qty: int | None = None
    get_discount_bps: int | None = None
    group_qty: int | None = None
    group_price_cents: int | None = None
    components: list[dict] | None = None
    bundle_price_cents: int | None = None
    amount_cents: int | None = None
    max_discount_cents: int | None = None
    customer_issued: bool = False
    segment: str | None = None
    repeat_count: int | None = None
    window_days: int | None = None
    quiet_days: int | None = None
    visit_count: int | None = None
    spend_cents: int | None = None
    notify: bool = False
    # Names for product_ids and bundle components, for display.
    product_names: dict[str, str] = Field(default_factory=dict)
