from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.payloads import (
    ApiModel,
    ChequeDetails,
    CreditOverridePayload,
    CustomerType,
    PaymentMethod,
    PaymentTerms,
    PriceTier,
    ProductPriceOut,
    SaleItemPayload,
    SaleOut,
    SaleTenderPayload,
    SaleType,
    UnitType,
    VolumeBreak,
    _currency,
)

TaxTreatment = Literal["STANDARD", "ZERO_EXPORT", "EXEMPT", "DESIGNATED_ZONE"]
LedgerEntryType = Literal["INVOICE", "PAYMENT", "ADJUSTMENT"]
CollectionMethod = Literal["cash", "card", "transfer"]
QuoteKind = Literal["QUOTE", "LAYAWAY"]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# --- Customers -----------------------------------------------------------------------------------


class CustomerWrite(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    customer_type: CustomerType = "RETAIL"
    company_name: str | None = Field(default=None, max_length=160)
    trn_vat_number: str | None = Field(default=None, max_length=32)
    price_tier: PriceTier = "RETAIL"
    credit_limit_cents: int = Field(default=0, ge=0, le=10_000_000_000)
    payment_terms: PaymentTerms = "DUE_ON_RECEIPT"
    address: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    whatsapp_opt_in: bool = False
    sms_opt_in: bool = False
    email_opt_in: bool = False
    group_id: UUID | None = None
    tax_treatment: TaxTreatment = "STANDARD"
    tax_certificate_ref: str | None = Field(default=None, max_length=64)
    tax_certificate_expiry: date | None = None
    birthday: date | None = None
    gender: Literal["women", "men", "kids", "unisex"] | None = None
    preferred_sizes: dict[str, str] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("phone", "email", "company_name", "trn_vat_number", "address", "tax_certificate_ref", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def retail_has_no_credit(self) -> Self:
        if self.customer_type == "RETAIL" and self.credit_limit_cents > 0:
            raise ValueError("Only wholesale customers can have a credit limit.")
        return self


class RegisterCustomerPayload(CustomerWrite):
    """A customer added at the register (the `customer` sync event). The register picks the id so offline sales
    can name the customer before the server has seen it."""

    id: UUID
    created_by_id: UUID


class CustomerUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    customer_type: CustomerType | None = None
    company_name: str | None = Field(default=None, max_length=160)
    trn_vat_number: str | None = Field(default=None, max_length=32)
    price_tier: PriceTier | None = None
    credit_limit_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)
    payment_terms: PaymentTerms | None = None
    address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    whatsapp_opt_in: bool | None = None
    sms_opt_in: bool | None = None
    email_opt_in: bool | None = None
    group_id: UUID | None = None
    tax_treatment: TaxTreatment | None = None
    tax_certificate_ref: str | None = Field(default=None, max_length=64)
    tax_certificate_expiry: date | None = None
    birthday: date | None = None
    gender: Literal["women", "men", "kids", "unisex"] | None = None
    preferred_sizes: dict[str, str] | None = None
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("phone", "email", "company_name", "trn_vat_number", "address", "tax_certificate_ref", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class CustomerOut(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    code: str
    name: str
    phone: str | None
    email: str | None
    customer_type: CustomerType
    company_name: str | None
    trn_vat_number: str | None
    price_tier: PriceTier
    credit_limit_cents: int
    current_balance_cents: int
    available_credit_cents: int
    payment_terms: PaymentTerms
    address: str | None
    is_active: bool
    overdue_cents: int = 0
    open_invoice_count: int = 0
    # Uncleared cheques already credited to the balance; they come back if a cheque bounces.
    cheque_exposure_cents: int = 0
    credit_hold: bool = False
    credit_hold_reason: str | None = None
    whatsapp_opt_in: bool = False
    sms_opt_in: bool = False
    email_opt_in: bool = False
    loyalty_points: int = 0
    risk_score: int | None = None
    risk_grade: str | None = None
    group_id: UUID | None = None
    tax_treatment: TaxTreatment = "STANDARD"
    tax_certificate_ref: str | None = None
    tax_certificate_expiry: date | None = None
    birthday: date | None = None
    gender: str | None = None
    preferred_sizes: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CustomerHistoryLine(ApiModel):
    sold_at: datetime
    name: str
    size: str | None = None
    color: str | None = None
    quantity: int


class RiskFactorOut(ApiModel):
    key: str
    label: str
    points: int
    detail: str


class CreditRiskOut(ApiModel):
    customer_id: UUID
    code: str
    name: str
    score: int
    grade: str
    label: str
    recommendation: str
    suggested_limit_cents: int
    credit_limit_cents: int
    balance_cents: int
    factors: list[RiskFactorOut]
    computed_at: datetime | None


class LedgerEntryOut(ApiModel):
    id: UUID
    entry_type: LedgerEntryType
    amount_cents: int
    balance_after_cents: int
    sale_id: UUID | None
    invoice: str | None
    due_date: datetime | None
    method: str | None
    reference: str
    note: str
    created_at: datetime


class OpenInvoiceOut(ApiModel):
    sale_id: UUID
    invoice: str
    created_at: datetime
    due_date: datetime | None
    total_cents: int
    amount_paid_cents: int
    due_balance_cents: int
    days_overdue: int
    payment_status: str


class AgingOut(ApiModel):
    current: int
    days_1_30: int
    days_31_60: int
    days_61_90: int
    days_90_plus: int


class StatementOut(ApiModel):
    customer: CustomerOut
    currency: str
    entries: list[LedgerEntryOut]
    open_invoices: list[OpenInvoiceOut]
    aging: AgingOut
    total_invoiced_cents: int
    total_paid_cents: int
    generated_at: datetime


class PaymentCreate(ApiModel):
    amount_cents: int = Field(ge=1, le=10_000_000_000)
    method: Literal["cash", "card", "transfer", "cheque"]
    reference: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=255)
    cheque: ChequeDetails | None = None

    @model_validator(mode="after")
    def cheque_details(self) -> Self:
        if (self.method == "cheque") != (self.cheque is not None):
            raise ValueError("Cheque payments need the cheque number, bank and date.")
        return self


class AllocationOut(ApiModel):
    sale_id: UUID
    invoice: str
    applied_cents: int
    remaining_cents: int


class PaymentOut(ApiModel):
    entry: LedgerEntryOut
    allocations: list[AllocationOut]
    unapplied_cents: int
    customer: CustomerOut


class CreditHoldWrite(ApiModel):
    hold: bool
    reason: str = Field(default="", max_length=255)


class LedgerAdjustment(ApiModel):
    amount_cents: int = Field(ge=-10_000_000_000, le=10_000_000_000)
    note: str = Field(min_length=3, max_length=255)

    @field_validator("amount_cents")
    @classmethod
    def nonzero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Adjustment cannot be zero.")
        return value


# --- Quotes --------------------------------------------------------------------------------------


class QuotePaymentIn(ApiModel):
    id: UUID
    amount_cents: int = Field(gt=0, le=100_000_000)
    method: CollectionMethod
    reference: str = Field(default="", max_length=120)
    shift_id: UUID | None = None
    # Registers authenticate as a device, so they name the cashier taking the deposit.
    cashier_id: UUID | None = None


class QuotePayload(ApiModel):
    """Serialized lines may carry one IMEI each, or a quantity with no IMEIs yet (assigned at conversion)."""

    id: UUID
    store_id: UUID
    cashier_id: UUID
    currency: str
    sale_type: SaleType = "WHOLESALE"
    customer_id: UUID | None = None
    valid_days: int = Field(default=7, ge=1, le=90)
    subtotal_cents: int = Field(ge=0)
    tax_cents: int = Field(ge=0)
    total_cents: int = Field(ge=0)
    items: list[SaleItemPayload] = Field(min_length=1, max_length=500)
    quote_kind: QuoteKind = "QUOTE"
    deposit: QuotePaymentIn | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)

    @model_validator(mode="after")
    def layaway_rules(self) -> Self:
        if self.quote_kind == "LAYAWAY" and self.customer_id is None:
            raise ValueError("A layaway needs a customer so the goods can be released to them.")
        if self.deposit is not None and self.quote_kind != "LAYAWAY":
            raise ValueError("Only layaways take deposits.")
        return self


class QuotePaymentOut(ApiModel):
    id: UUID
    amount_cents: int
    method: str
    reference: str
    status: str
    received_by_name: str | None
    received_at: datetime


class QuoteOut(SaleOut):
    number: str
    cashier_name: str | None = None
    quote_kind: QuoteKind = "QUOTE"
    deposits_cents: int = 0
    refund_due_cents: int = 0
    payments: list[QuotePaymentOut] = Field(default_factory=list)


class QuoteStats(ApiModel):
    open_count: int
    open_value_cents: int
    converted_count: int
    converted_value_cents: int
    expired_count: int
    cancelled_count: int
    conversion_rate_bps: int
    expiring_soon_count: int


class QuoteList(ApiModel):
    currency: str
    stats: QuoteStats
    quotes: list[QuoteOut]
    # Quotes matching the status filter; `quotes` holds one page of them.
    total: int = 0


class QuoteConvert(ApiModel):
    sale_id: UUID | None = None
    payment_method: PaymentMethod
    tenders: list[SaleTenderPayload] | None = Field(default=None, max_length=6)
    credit_override: CreditOverridePayload | None = None


# --- Pricing -------------------------------------------------------------------------------------


def _check_breaks(breaks: list[VolumeBreak]) -> list[VolumeBreak]:
    quantities = [item.min_qty for item in breaks]
    if len(set(quantities)) != len(quantities):
        raise ValueError("Each volume break needs a different minimum quantity.")
    return sorted(breaks, key=lambda item: item.min_qty)


class TierPriceWrite(ApiModel):
    price_tier: PriceTier
    # None removes the tier's own price so it falls back to the next lower tier.
    price_cents: int | None = Field(default=None, ge=0)
    min_order_quantity: int = Field(default=1, ge=1, le=1_000_000)
    volume_discounts: list[VolumeBreak] = Field(default_factory=list, max_length=10)

    @field_validator("volume_discounts")
    @classmethod
    def breaks_unique(cls, value: list[VolumeBreak]) -> list[VolumeBreak]:
        return _check_breaks(value)


class ProductPricingWrite(ApiModel):
    retail_price_cents: int | None = Field(default=None, ge=0)
    min_order_quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    sellable_units: list[UnitType] | None = Field(default=None, min_length=1, max_length=8)
    tiers: list[TierPriceWrite] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def tiers_unique(self) -> Self:
        names = [tier.price_tier for tier in self.tiers]
        if len(set(names)) != len(names):
            raise ValueError("Each tier can only appear once.")
        return self


class PricingRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    brand: str | None
    category: str
    category_id: UUID | None
    is_serialized: bool
    retail_price_cents: int
    min_order_quantity: int
    sellable_units: list[UnitType]
    prices: list[ProductPriceOut]


class PricingMatrix(ApiModel):
    currency: str
    rows: list[PricingRow]
    brands: list[str]


BulkMode = Literal["set", "percent_of_retail", "adjust_percent"]


class BulkPriceUpdate(ApiModel):
    product_ids: list[UUID] | None = Field(default=None, max_length=1000)
    category_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=80)
    price_tier: PriceTier
    mode: BulkMode
    price_cents: int | None = Field(default=None, ge=0)
    # Basis points: 8500 = 85% of retail; -500 = 5% lower than the current tier price.
    percent_bps: int | None = Field(default=None, ge=-10_000, le=100_000)
    min_order_quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    volume_discounts: list[VolumeBreak] | None = Field(default=None, max_length=10)

    @field_validator("volume_discounts")
    @classmethod
    def breaks_unique(cls, value: list[VolumeBreak] | None) -> list[VolumeBreak] | None:
        return None if value is None else _check_breaks(value)

    @model_validator(mode="after")
    def target_and_amount(self) -> Self:
        if self.product_ids is None and self.category_id is None and self.brand is None:
            raise ValueError("Choose products, a category, or a brand to update.")
        if self.mode == "set" and self.price_cents is None:
            raise ValueError("Enter the new price.")
        if self.mode != "set" and self.percent_bps is None:
            raise ValueError("Enter the percentage.")
        if self.mode == "percent_of_retail" and self.percent_bps is not None and self.percent_bps <= 0:
            raise ValueError("Percent of retail must be above zero.")
        return self


class BulkPriceResult(ApiModel):
    updated: int
    skipped: int
