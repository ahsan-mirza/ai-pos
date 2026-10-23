from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

SubscriptionStatus = Literal["trialing", "active", "past_due", "canceled"]
PurgeMode = Literal["keep", "fresh"]
OpeningStock = Literal["keep", "reset"]


class PlanOut(ApiModel):
    id: UUID
    code: str
    name: str
    included_registers: int
    included_modules: list[str]
    monthly_fils: int
    trial_days: int
    active: bool
    sort_order: int


class PlanIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    included_registers: int = Field(ge=1, le=500)
    included_modules: list[str] = Field(default_factory=list, max_length=40)
    monthly_fils: int = Field(ge=0, le=100_000_000)
    trial_days: int = Field(ge=0, le=365)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=100)
    reason: str = Field(min_length=3, max_length=500)


class CycleOut(ApiModel):
    id: UUID
    code: str
    name: str
    months: int
    discount_bps: int
    active: bool
    sort_order: int


class CycleIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    months: int = Field(ge=1, le=36)
    discount_bps: int = Field(ge=0, le=10_000)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=100)
    reason: str = Field(min_length=3, max_length=500)


class AddonOut(ApiModel):
    id: UUID
    code: str
    name: str
    description: str
    monthly_fils: int
    one_time_fils: int
    refundable: bool
    active: bool
    sort_order: int


class AddonIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    monthly_fils: int = Field(ge=0, le=100_000_000)
    one_time_fils: int = Field(ge=0, le=100_000_000)
    refundable: bool = False
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=100)
    reason: str = Field(min_length=3, max_length=500)


class FeeOut(ApiModel):
    id: UUID
    code: str
    name: str
    amount_fils: int
    active: bool


class FeeIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    amount_fils: int = Field(ge=0, le=100_000_000)
    active: bool = True
    reason: str = Field(min_length=3, max_length=500)


class CatalogOut(ApiModel):
    plans: list[PlanOut]
    cycles: list[CycleOut]
    addons: list[AddonOut]
    fees: list[FeeOut]


class AddonQty(ApiModel):
    code: str = Field(min_length=1, max_length=32)
    quantity: int = Field(ge=0, le=100)


class QuoteLine(ApiModel):
    code: str
    label: str
    quantity: int
    unit_fils: int
    amount_fils: int
    recurring: bool
    refundable: bool


class QuoteOut(ApiModel):
    currency: str = "AED"
    plan_code: str
    plan_name: str
    cycle_code: str
    cycle_name: str
    months: int
    discount_bps: int
    included_registers: int
    lines: list[QuoteLine]
    recurring_fils: int
    one_time_fils: int
    total_fils: int


class QuoteIn(ApiModel):
    plan_code: str = Field(min_length=1, max_length=32)
    cycle_code: str = Field(min_length=1, max_length=32)
    addons: list[AddonQty] = Field(default_factory=list, max_length=20)


class CheckoutIn(QuoteIn):
    mode: PurgeMode
    opening_stock: OpeningStock | None = None
    confirm: str = Field(min_length=1, max_length=120)
    tax_acknowledged: bool = False


class CheckoutOut(ApiModel):
    checkout_id: UUID
    mode: Literal["simulator", "stripe"]
    url: str | None
    quote: QuoteOut


class CheckoutStatus(ApiModel):
    checkout_id: UUID
    status: Literal["pending", "paid", "failed"]
    error: str | None
    result: dict | None


class SubscriptionOut(ApiModel):
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    plan_code: str
    plan_name: str
    cycle_code: str
    cycle_name: str
    status: SubscriptionStatus
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    practice_mode: bool
    next_recurring_fils: int
    addons: list[AddonQty]


class SubscriptionAssign(ApiModel):
    plan_code: str = Field(min_length=1, max_length=32)
    cycle_code: str = Field(min_length=1, max_length=32)
    addons: list[AddonQty] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
