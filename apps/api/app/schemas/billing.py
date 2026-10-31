from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.hardware import HardwareItemOut, HardwarePick
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


class AddonBenefit(ApiModel):
    title: str = ""
    description: str = ""


class AddonFaq(ApiModel):
    question: str = ""
    answer: str = ""


class AddonListing(ApiModel):
    short_description: str = ""
    overview: str = ""
    category: str = "operations"
    tags: list[str] = Field(default_factory=list)
    benefits: list[AddonBenefit] = Field(default_factory=list)
    features: list[AddonBenefit] = Field(default_factory=list)
    steps: list[AddonBenefit] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    faqs: list[AddonFaq] = Field(default_factory=list)
    documentation_url: str = ""
    video_url: str = ""
    support: str = ""
    icon: str = "puzzle"
    image_url: str = ""
    featured: bool = False
    publication: Literal["published", "draft", "archived"] = "published"


class AddonPricePoint(ApiModel):
    monthly_fils: int
    one_time_fils: int
    refundable: bool
    effective_at: str
    reason: str = ""


class AddonOut(ApiModel):
    id: UUID
    code: str
    name: str
    description: str
    monthly_fils: int
    one_time_fils: int
    refundable: bool
    active: bool
    module_keys: list[str] = Field(default_factory=list)
    sort_order: int
    listing: AddonListing = Field(default_factory=AddonListing)
    price_history: list[AddonPricePoint] = Field(default_factory=list)
    updated_at: datetime | None = None


class AddonIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    monthly_fils: int = Field(ge=0, le=100_000_000)
    one_time_fils: int = Field(ge=0, le=100_000_000)
    refundable: bool = False
    active: bool = True
    module_keys: list[str] = Field(default_factory=list, max_length=40)
    sort_order: int = Field(default=0, ge=0, le=1000)
    reason: str = Field(min_length=3, max_length=500)
    listing: AddonListing | None = None


class ModuleCatalogueItem(ApiModel):
    key: str
    label: str
    available: bool
    requires: list[str]
    business_types: list[str]
    preset_for: list[str]
    plan_codes: list[str]
    addon_codes: list[str]


class BusinessTypeModules(ApiModel):
    key: str
    label: str
    preset: list[str]
    eligible: list[str]


class ModuleSummary(ApiModel):
    catalogue_total: int
    implemented: int
    not_implemented: int
    active_addons: int
    mapped_addons: int
    active_subscriptions: int
    trialing_subscriptions: int
    past_due_subscriptions: int
    canceled_subscriptions: int
    pending_payments: int
    # Monthly catalogue price of add-on lines on subscriptions whose status is active. Trials, deposits,
    # one-time fees, and unpaid invoices are not included.
    addon_mrr_fils: int


class EntitlementLine(ApiModel):
    key: str
    label: str
    enabled: bool
    available: bool
    fits_type: bool
    reason: str
    override: str | None = None
    addon_codes: list[str] = Field(default_factory=list)


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
    hardware: list[HardwareItemOut] = Field(default_factory=list)


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
    hardware_monthly_fils: int = 0
    deposit_fils: int = 0


class QuoteIn(ApiModel):
    plan_code: str = Field(min_length=1, max_length=32)
    cycle_code: str = Field(min_length=1, max_length=32)
    addons: list[AddonQty] = Field(default_factory=list, max_length=20)
    hardware: list[HardwarePick] = Field(default_factory=list, max_length=100)


class CheckoutIn(QuoteIn):
    mode: PurgeMode
    opening_stock: OpeningStock | None = None
    confirm: str = Field(min_length=1, max_length=120)
    tax_acknowledged: bool = False
    # card keeps the existing Stripe or simulator path. transfer issues an invoice and waits for a receipt.
    payment: Literal["card", "transfer"] = "card"


class CheckoutOut(ApiModel):
    checkout_id: UUID
    mode: Literal["simulator", "stripe", "transfer"]
    url: str | None
    quote: QuoteOut
    bank: dict[str, str] | None = None


class CheckoutStatus(ApiModel):
    checkout_id: UUID
    status: Literal["pending", "paid", "failed"]
    error: str | None
    result: dict | None
    total_fils: int = 0
    currency: str = "AED"
    bank: dict[str, str] | None = None


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


class PlanRevenue(ApiModel):
    plan_code: str
    plan_name: str
    paying_tenants: int
    mrr_fils: int


class StatusCount(ApiModel):
    status: str
    tenants: int


class OverviewOut(ApiModel):
    """Figures from the control database. MRR is the monthly equivalent of active and past-due subscriptions."""

    currency: str = "AED"
    tenants: int
    active_tenants: int
    suspended_tenants: int
    practice_tenants: int
    new_tenants_30d: int
    stores: int
    registers: int
    paying_subscriptions: int
    trialing: int
    trials_ending_14d: int
    past_due: int
    canceled: int
    mrr_fils: int
    arr_fils: int
    unpaid_checkouts_fils: int
    unpaid_checkouts: int
    open_change_requests: int
    by_status: list[StatusCount]
    by_plan: list[PlanRevenue]
    definitions: list[str]


class BankAccountIn(ApiModel):
    display_name: str = Field(min_length=1, max_length=80)
    bank_name: str = Field(min_length=1, max_length=120)
    holder_name: str = Field(min_length=1, max_length=120)
    account_number: str = Field(default="", max_length=40)
    iban: str = Field(default="", max_length=40)
    swift: str = Field(default="", max_length=16)
    country: str = Field(default="AE", min_length=2, max_length=2)
    currency: str = Field(default="AED", min_length=3, max_length=3)
    instructions: str = Field(default="", max_length=500)
    active: bool = True


class BankAccountOut(BankAccountIn):
    id: UUID


class TransferOut(ApiModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    invoice_id: UUID
    status: Literal["pending_review", "approved", "rejected"]
    amount_fils: int
    invoice_total_fils: int
    currency: str
    transferred_on: str
    bank_reference: str
    sending_bank: str = ""
    plan_code: str = ""
    cycle_code: str = ""
    tenant_slug: str = ""
    created_at: datetime
    decision_reason: str | None


class ReviewSummary(ApiModel):
    pending: int


class ReviewNotice(ApiModel):
    id: UUID
    payment_submission_id: UUID
    tenant_name: str
    invoice_reference: str
    amount_fils: int
    currency: str
    submitted_at: datetime
    status: Literal["pending_review", "approved", "rejected"]
    read: bool


class PaymentOut(ApiModel):
    id: UUID
    invoice_id: UUID
    amount_fils: int
    bank_reference: str | None


class GraceIn(ApiModel):
    grace_days: int = Field(ge=0, le=60)


class RejectIn(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class PaymentAttention(ApiModel):
    kind: Literal["awaiting_proof", "pending_review", "rejected", "revoked"]
    invoice_id: UUID
    plan_code: str
    cycle_code: str
    currency: str
    total_fils: int
    issued_at: str
    bank: dict[str, str] | None = None
    transfer_id: UUID | None = None
    reason: str | None = None


class AccessSubscription(ApiModel):
    """The store's current package, as stored. Status is the subscription row, not a second calculation."""

    id: UUID
    plan_code: str
    plan_name: str
    cycle_name: str
    status: str
    price_fils: int
    currency: str
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    grace_ends_at: datetime | None = None


class AccessOut(ApiModel):
    state: str
    ai_allowed: bool
    operational: bool = True
    attention: PaymentAttention | None = None
    subscription: AccessSubscription | None = None


MarketplaceState = Literal[
    "included",
    "available",
    "activated",
    "pending_payment",
    "pending_activation",
    "expired",
    "unavailable",
    "unpriced",
]


class MarketplaceItem(ApiModel):
    addon: AddonOut
    state: MarketplaceState
    reason: str = ""
    invoice_id: UUID | None = None
    compatible_labels: list[str] = Field(default_factory=list)
    search_text: str = ""


class MarketplaceOut(ApiModel):
    currency: str = "AED"
    available: int = 0
    activated: int = 0
    pending: int = 0
    recurring_fils: int = 0
    items: list[MarketplaceItem] = Field(default_factory=list)


class SubscriptionAssign(ApiModel):
    plan_code: str = Field(min_length=1, max_length=32)
    cycle_code: str = Field(min_length=1, max_length=32)
    addons: list[AddonQty] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
