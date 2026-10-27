import re
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

EntityType = Literal[
    "store",
    "product",
    "serial_number",
    "sale",
    "repair_ticket",
    "sale_return",
    "register_shift",
    "cash_movement",
    "time_entry",
    "customer",
    "open_order",
]
PaymentMethod = Literal[
    "cash",
    "card",
    "transfer",
    "cheque",
    "store_credit",
    "on_account",
    "deposit",
    "qr",
    "loyalty",
    "trade_in",
    # Paid through a delivery app, which settles with the business later.
    "channel",
    # Buy now, pay later (Tabby, Tamara): the provider pays the business and collects instalments.
    "bnpl",
    # A gift card (GIFT_CARD store credit) spent as payment.
    "gift_card",
]
TaxCategory = Literal["STANDARD", "ZERO", "EXEMPT"]
Emirate = Literal["AUH", "DXB", "SHJ", "AJM", "UAQ", "RAK", "FUJ"]
SerialKind = Literal["imei", "serial"]
SerialStatus = Literal[
    "in_stock", "reserved", "in_transit", "sold", "defective", "repair", "quarantine", "scrapped", "reversed"
]
SaleStatus = Literal["draft", "completed", "voided", "partially_refunded", "refunded", "quote"]
CustomerType = Literal["RETAIL", "WHOLESALE"]
PriceTier = Literal["RETAIL", "TIER_1", "TIER_2", "DISTRIBUTOR"]
PaymentTerms = Literal["DUE_ON_RECEIPT", "NET_15", "NET_30", "NET_60"]
PaymentStatus = Literal["PAID", "PARTIAL", "ON_ACCOUNT_UNPAID"]
SaleType = Literal["RETAIL", "WHOLESALE"]
QuoteStatus = Literal["OPEN", "CONVERTED", "EXPIRED", "CANCELLED"]
# Pack codes as stored on products (sellable_units) and sale lines (unit_type): the built-in PIECE, BOX_10 and
# CARTON_100, or a business's own (units_of_measure), e.g. CASE_24. Factors live in app.services.uom_service.
UnitType = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,15}$")]
RefundMethod = Literal["cash", "original_card", "original_bnpl", "store_credit"]
# Keys from the business's returns policy (app.schemas.pos_policy), e.g. "tags_attached" or "open_box".
ReturnCondition = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")]
ReturnReason = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")]
OverrideReason = Literal["no_refund_permission", "outside_window", "fee_waived", "final_sale"]
RepairStatus = Literal[
    "intake", "diagnosing", "awaiting_approval", "in_repair", "waiting_parts", "ready", "closed", "cancelled"
]
RepairPriority = Literal["LOW", "NORMAL", "HIGH", "URGENT"]
AnalyticsTimeframe = Literal["all_time", "weekly", "monthly"]


def _currency(value: str) -> str:
    code = value.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code) is None:
        raise ValueError("currency must be a 3-letter ISO code.")
    return code


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitOption(ApiModel):
    """A pack as a register needs it: what to call it and how many base units it holds."""

    code: str
    name: str
    short_name: str
    factor: int


class StorePayload(ApiModel):
    id: UUID
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    currency: str
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    emirate: Emirate | None = None
    is_warehouse: bool = False
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)


class ProductPayload(ApiModel):
    """Catalog upsert. store_id and stock_quantity only set opening stock when the product is created;
    after that, stock changes exclusively through inventory movements."""

    id: UUID
    store_id: UUID
    sku: str = Field(min_length=1, max_length=64)
    barcode: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    model_number: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    category_id: UUID | None = None
    sub_category: str | None = Field(default=None, max_length=80)
    sub_category_id: UUID | None = None
    brand_id: UUID | None = None
    product_model_id: UUID | None = None
    price_cents: int = Field(ge=0)
    currency: str
    is_serialized: bool
    stock_quantity: int = Field(ge=0)
    # Portal-owned; registers never send these, and a register upsert never edits an existing product.
    tax_category: TaxCategory | None = None
    is_open_price: bool | None = None

    @model_validator(mode="after")
    def open_price_rules(self) -> Self:
        if self.is_open_price and self.is_serialized:
            raise ValueError("Serialized products cannot be open-price.")
        return self

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)

    @field_validator("model_number", "brand", "sub_category")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SerialPayload(ApiModel):
    id: UUID
    product_id: UUID
    store_id: UUID
    kind: SerialKind
    value: str = Field(min_length=1, max_length=64)
    status: SerialStatus


class PriceOverridePayload(ApiModel):
    approved_by_id: UUID
    note: str = Field(default="", max_length=255)


class ModifierChoice(ApiModel):
    """One menu modifier picked for a line. Names are informational; the server prices from its own catalogue."""

    group_id: UUID
    option_id: UUID
    group: str | None = Field(default=None, max_length=80)
    option: str | None = Field(default=None, max_length=80)
    price_delta_cents: int = Field(ge=-1_000_000, le=1_000_000)


class ComboChoice(ApiModel):
    """One meal component picked for a combo line. Names and surcharges are informational; the server prices them."""

    slot_id: UUID
    product_id: UUID
    slot: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, max_length=200)
    surcharge_cents: int = Field(default=0, ge=0, le=1_000_000)


class AgeCheckPayload(ApiModel):
    """Cashier confirmation, or a manager override with a reason. No identity document is stored."""

    confirmed: bool = False
    override_by_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=200)


class SaleItemPayload(ApiModel):
    """quantity and unit_price_cents are per piece; unit_type records the pack the cashier sold in.
    Sold-by-weight products count grams and price per kilogram (app.services.weighed)."""

    id: UUID
    product_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)
    unit_price_cents: int = Field(ge=0)
    tax_cents: int = Field(ge=0)
    line_total_cents: int = Field(ge=0)
    serial_value: str | None = None
    serial_kind: SerialKind | None = None
    unit_type: UnitType = "PIECE"
    list_price_cents: int | None = Field(default=None, ge=0)
    price_override: PriceOverridePayload | None = None
    # Open-price items carry what was sold, e.g. "Screen protector fitting".
    description: str | None = Field(default=None, max_length=160)
    below_floor_override: PriceOverridePayload | None = None
    # Promotion discount on unit_price_cents * quantity; VAT and line_total_cents are on the discounted amount.
    discount_cents: int = Field(default=0, ge=0)
    promotion_id: UUID | None = None
    # Menu modifiers; unit_price_cents and list_price_cents include their price deltas.
    modifiers: list[ModifierChoice] = Field(default_factory=list, max_length=30)
    components: list[ComboChoice] = Field(default_factory=list, max_length=20)
    # Cashier discount after any promotion, before VAT, with a reason from pos_policy; discount_override names the
    # manager who approved it when it is above the cashier's own limit.
    manual_discount_cents: int = Field(default=0, ge=0)
    discount_reason: str | None = Field(default=None, max_length=32)
    discount_override: PriceOverridePayload | None = None
    # Selling a gift card: the code the register generated (GIFT_CARD_CODE); the line amount loads the card.
    gift_card_code: str | None = Field(default=None, pattern=r"^GC-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
    # Required when the product has a minimum age. Absent or unconfirmed sales are rejected.
    age_check: AgeCheckPayload | None = None

    @model_validator(mode="after")
    def serial_fields_match(self) -> Self:
        if (self.serial_value is None) != (self.serial_kind is None):
            raise ValueError("serial_value and serial_kind must be provided together.")
        if (self.discount_cents > 0) != (self.promotion_id is not None):
            raise ValueError("A line discount must name its promotion, and a promotion must give a discount.")
        if (self.manual_discount_cents > 0) != (self.discount_reason is not None):
            raise ValueError("A cashier discount needs a reason, and a reason needs a discount.")
        # An upper bound for weighed lines (price per kg x grams); price_lines checks the exact value.
        if self.discount_cents + self.manual_discount_cents > self.unit_price_cents * self.quantity:
            raise ValueError("The discount cannot exceed the line's value.")
        if self.gift_card_code is not None and (
            self.quantity != 1 or self.discount_cents or self.manual_discount_cents or self.serial_value
        ):
            raise ValueError("A gift card line is one card at its face value.")
        return self


class ChequeDetails(ApiModel):
    cheque_number: str = Field(min_length=1, max_length=32)
    bank: str = Field(min_length=1, max_length=80)
    cheque_date: date


STORE_CREDIT_CODE = r"^SC-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"
GIFT_CARD_CODE = r"^GC-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"


class SaleTenderPayload(ApiModel):
    """amount_cents is always in the business currency; foreign tenders also record what was handed over."""

    method: PaymentMethod
    amount_cents: int = Field(ge=1)
    reference: str = Field(default="", max_length=64)
    cheque: ChequeDetails | None = None
    store_credit_code: str | None = Field(default=None, pattern=STORE_CREDIT_CODE)
    gift_card_code: str | None = Field(default=None, pattern=GIFT_CARD_CODE)
    trade_in_id: UUID | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    foreign_amount_cents: int | None = Field(default=None, ge=1)
    rate_micros: int | None = Field(default=None, ge=1)
    # Business-currency change handed back when the customer paid in a foreign currency.
    change_cents: int | None = Field(default=None, ge=0)
    payment_intent_id: UUID | None = None
    # A card taken on a standalone machine at a store whose terminals are integrated: the manager who allowed it.
    manual_override: PriceOverridePayload | None = None

    @model_validator(mode="after")
    def method_details(self) -> Self:
        if self.payment_intent_id is not None and self.method not in ("qr", "card", "bnpl"):
            raise ValueError("Only QR, card and pay-later tenders reference a provider payment.")
        if self.method == "bnpl" and self.payment_intent_id is None:
            raise ValueError("Pay-later tenders must reference the provider payment.")
        if self.manual_override is not None and (self.method != "card" or self.payment_intent_id is not None):
            raise ValueError("Only card tenders taken without the terminal carry a manual approval.")
        if (self.method == "cheque") != (self.cheque is not None):
            raise ValueError("Cheque details are required for cheque tenders and only for them.")
        if self.store_credit_code is not None and self.method != "store_credit":
            raise ValueError("Only store credit tenders carry a voucher code.")
        if (self.method == "gift_card") != (self.gift_card_code is not None):
            raise ValueError("Gift card tenders carry the card code, and only they do.")
        if self.trade_in_id is not None and self.method != "trade_in":
            raise ValueError("Only trade-in tenders reference a trade-in.")
        foreign = (self.currency, self.foreign_amount_cents, self.rate_micros)
        if any(value is not None for value in foreign) and any(value is None for value in foreign):
            raise ValueError("Foreign tenders need currency, foreign_amount_cents, and rate_micros together.")
        return self


class CreditOverridePayload(ApiModel):
    approved_by_id: UUID
    note: str = Field(default="", max_length=255)


class SalePayload(ApiModel):
    """Older registers send one payment_method and no tenders; that is read as a single fully paid tender."""

    id: UUID
    store_id: UUID
    cashier_id: UUID
    currency: str
    payment_method: PaymentMethod
    subtotal_cents: int = Field(ge=0)
    tax_cents: int = Field(ge=0)
    total_cents: int = Field(ge=0)
    client_sale_id: str = Field(min_length=1, max_length=64)
    items: list[SaleItemPayload] = Field(min_length=1, max_length=500)
    sale_type: SaleType = "RETAIL"
    customer_id: UUID | None = None
    # Up to 12 so a table can split one bill between its guests, each paying their own way.
    tenders: list[SaleTenderPayload] | None = Field(default=None, max_length=12)
    credit_override: CreditOverridePayload | None = None
    # When the register rang the sale up; defaults to the sync event's occurred_at.
    sold_at: datetime | None = None
    # The register's own invoice series (e.g. DT-01-R01-000123); the API numbers sales that omit it.
    invoice_number: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[A-Z0-9-]+$")
    shift_id: UUID | None = None
    loyalty_points_redeemed: int | None = Field(default=None, ge=1)
    coupon_code: str | None = Field(default=None, min_length=2, max_length=32)
    # The restaurant tab this sale pays, and which of its lines (all unpaid lines when empty).
    order_id: UUID | None = None
    order_item_ids: list[UUID] = Field(default_factory=list, max_length=200)
    # Service charge is revenue and part of total_cents (its VAT is in tax_cents when taxable).
    service_charge_cents: int = Field(default=0, ge=0)
    service_charge_tax_cents: int = Field(default=0, ge=0)
    # A tip is owed to staff: not revenue, never taxed, outside total_cents; tenders cover total + tip.
    tip_cents: int = Field(default=0, ge=0)
    # Who the tip is for (defaults to the cashier).
    tip_user_id: UUID | None = None
    # The stylist who served the customer, when it is not the cashier; commissions credit them.
    sales_associate_id: UUID | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)

    @field_validator("sold_at")
    @classmethod
    def sold_at_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("sold_at must include a timezone.")
        return value

    @model_validator(mode="after")
    def tenders_cover_total(self) -> Self:
        if self.tenders is None:
            if self.tip_cents:
                raise ValueError("A tip needs explicit tenders.")
            return self
        if sum(tender.amount_cents for tender in self.tenders) != self.total_cents + self.tip_cents:
            raise ValueError("Tenders must add up to the sale total plus the tip.")
        if self.payment_method not in {tender.method for tender in self.tenders}:
            raise ValueError("payment_method must be one of the tenders.")
        if sum(1 for tender in self.tenders if tender.method == "on_account") > 1:
            raise ValueError("Only one on-account tender is allowed.")
        return self

    def resolved_tenders(self) -> list[SaleTenderPayload]:
        if self.tenders is not None:
            return self.tenders
        if self.total_cents == 0:
            return []
        return [SaleTenderPayload(method=self.payment_method, amount_cents=self.total_cents)]


class RepairPayload(ApiModel):
    id: UUID
    store_id: UUID
    # customer: the owner's device. internal: equipment the shop owns. Older registers omit this.
    ownership: Literal["customer", "internal"] = "customer"
    product_id: UUID | None = None
    customer_name: str = Field(default="", max_length=120)
    customer_phone: str = Field(default="", max_length=40)
    device_model: str = Field(default="", max_length=120)
    identifier_kind: SerialKind
    identifier_value: str = Field(min_length=1, max_length=64)
    issue: str = Field(min_length=1, max_length=2000)
    status: RepairStatus
    estimated_cost_cents: int = Field(ge=0)
    currency: str
    customer_id: UUID | None = None
    # Intake details from the register's wizard; older registers omit them.
    technician_id: UUID | None = None
    priority: RepairPriority | None = None
    promised_at: datetime | None = None
    passcode: str | None = Field(default=None, max_length=64)
    intake_checklist: dict[str, bool | str] | None = None
    accessories: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def classify_ownership(self) -> Self:
        from app.services.phone_numbers import normalize_phone

        if self.ownership == "internal":
            self.customer_name = self.customer_name.strip() or "Shop equipment"
            self.customer_phone = self.customer_phone.strip()
            if self.product_id is None:
                raise ValueError("Select the shop device from inventory.")
            if not self.device_model.strip():
                self.device_model = "Shop device"
            return self
        if not self.customer_name.strip():
            raise ValueError("Enter the customer name.")
        if not self.device_model.strip():
            raise ValueError("Enter the device.")
        normalized = normalize_phone(self.customer_phone, required=True)
        if normalized is None:
            raise ValueError("Enter a phone number.")
        self.customer_phone = normalized
        return self

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)

    @field_validator("intake_checklist")
    @classmethod
    def small_checklist(cls, value: dict[str, bool | str] | None) -> dict[str, bool | str] | None:
        if value is not None and (len(value) > 40 or any(len(key) > 40 for key in value)):
            raise ValueError("The intake checklist has at most 40 short items.")
        if value is not None and any(isinstance(item, str) and len(item) > 200 for item in value.values()):
            raise ValueError("Checklist notes are at most 200 characters.")
        return value


class ReturnItemPayload(ApiModel):
    id: UUID
    sale_item_id: UUID
    product_id: UUID
    quantity: int = Field(ge=1, le=10_000)
    unit_price_cents: int = Field(ge=0)
    tax_refund_cents: int = Field(ge=0)
    restocking_fee_cents: int = Field(ge=0)
    refund_cents: int = Field(ge=0)
    condition_status: ReturnCondition
    reason_code: ReturnReason
    serial_value: str | None = None
    serial_kind: SerialKind | None = None

    @model_validator(mode="after")
    def serial_fields_match(self) -> Self:
        if (self.serial_value is None) != (self.serial_kind is None):
            raise ValueError("serial_value and serial_kind must be provided together.")
        return self


class ReturnTenderPayload(ApiModel):
    method: RefundMethod
    amount_cents: int = Field(ge=1)
    store_credit_code: str | None = Field(default=None, pattern=STORE_CREDIT_CODE)

    @model_validator(mode="after")
    def credit_code_matches_method(self) -> Self:
        if (self.method == "store_credit") != (self.store_credit_code is not None):
            raise ValueError("A store credit code is required for store credit and only for store credit.")
        return self


class ReturnOverridePayload(ApiModel):
    approved_by_id: UUID
    reasons: list[OverrideReason] = Field(min_length=1, max_length=3)
    note: str = Field(default="", max_length=500)


class ReturnPayload(ApiModel):
    id: UUID
    original_sale_id: UUID
    store_id: UUID
    cashier_id: UUID
    currency: str
    processed_at: datetime
    subtotal_cents: int = Field(ge=0)
    tax_refund_cents: int = Field(ge=0)
    restocking_fee_cents: int = Field(ge=0)
    total_refund_cents: int = Field(ge=0)
    reason_notes: str = Field(default="", max_length=1000)
    items: list[ReturnItemPayload] = Field(min_length=1, max_length=500)
    tenders: list[ReturnTenderPayload] = Field(min_length=1, max_length=3)
    override: ReturnOverridePayload | None = None
    credit_note_number: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[A-Z0-9-]+$")
    shift_id: UUID | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return _currency(value)

    @field_validator("processed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at must include a timezone.")
        return value


class SyncEventIn(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9:_.-]+$")
    entity_type: EntityType
    operation: Literal["upsert"]
    payload: dict[str, object]
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone.")
        return value


class SyncPushRequest(ApiModel):
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_.-]+$")
    events: list[SyncEventIn] = Field(min_length=1, max_length=1000)


class SyncPushResult(ApiModel):
    idempotency_key: str
    status: Literal["applied", "duplicate"]


class SyncPushResponse(ApiModel):
    results: list[SyncPushResult]


class StoreOut(StorePayload):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    created_at: datetime
    updated_at: datetime


class VolumeBreak(ApiModel):
    min_qty: int = Field(ge=2, le=1_000_000)
    price_cents: int = Field(ge=0)


class ProductPriceOut(ApiModel):
    price_tier: PriceTier
    price_cents: int
    min_order_quantity: int
    volume_discounts: list[VolumeBreak]


class PriceListEntryOut(ApiModel):
    """One price list's item for one product, with the list's scope and validity: what a resolver needs."""

    price_list_id: UUID | None
    scope: Literal["customer", "group", "store", "global"]
    scope_id: UUID | None
    valid_from: datetime | None
    valid_to: datetime | None
    priority: int
    is_active: bool
    price_cents: int | None
    discount_bps: int | None
    min_qty: int
    volume_breaks: list[VolumeBreak] = Field(default_factory=list)


class ProductOut(ApiModel):
    """Catalog row plus stock at `store_id`, or consolidated across all branches when store_id is null.
    price_cents is the RETAIL price; `prices` holds the other tiers and any volume breaks."""

    id: UUID
    store_id: UUID | None
    sku: str
    barcode: str
    name: str
    model_number: str | None
    brand: str | None
    category: str
    category_id: UUID | None
    sub_category: str | None
    sub_category_id: UUID | None
    brand_id: UUID | None = None
    product_model_id: UUID | None = None
    model_name: str | None = None
    variant_attributes: dict[str, str] = Field(default_factory=dict)
    specifications: dict[str, str] = Field(default_factory=dict)
    price_cents: int
    compare_at_cents: int | None = None
    currency: str
    is_serialized: bool
    stock_quantity: int
    quantity_reserved: int
    min_order_quantity: int = 1
    sellable_units: list[UnitType] = Field(default_factory=lambda: ["PIECE"])
    # The packs in sellable_units with their names and factors, so registers need no unit list of their own.
    unit_options: list[UnitOption] = Field(default_factory=list)
    prices: list[ProductPriceOut] = Field(default_factory=list)
    tax_category: TaxCategory = "STANDARD"
    is_open_price: bool = False
    is_service: bool = False
    # Weighed goods: stock_quantity counts grams and price_cents is per kilogram.
    sold_by_weight: bool = False
    plu_code: str | None = None
    tare_grams: int = 0
    minimum_age: int | None = None
    # Soonest expiry among the batches still holding stock at store_id (expiry-first stock module).
    nearest_expiry: date | None = None
    # Recipes module: a dish drawn from its ingredients (no stock of its own), and ingredients registers never sell.
    has_recipe: bool = False
    is_ingredient: bool = False
    item_type: str = "PRE_PACKAGED"
    is_stock_tracked: bool = True
    # Business-wide and this branch's price-list entries (customer and group lists come per customer).
    price_lists: list[PriceListEntryOut] = Field(default_factory=list)
    # Cover photo: the variant's own, else its model's photo for this colour, else the model's primary photo.
    image_url: str | None = None
    thumb_url: str | None = None
    # Fashion attributes (from the model for variants).
    season: str | None = None
    collection: str | None = None
    gender: str | None = None
    material: str | None = None
    fit: str | None = None
    care: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductSearchHit(ApiModel):
    product: ProductOut
    match: Literal["identifier", "exact", "text"]
    serial_kind: SerialKind | None = None
    serial_status: SerialStatus | None = None


class SaleItemOut(ApiModel):
    id: UUID
    sale_id: UUID
    product_id: UUID
    serial_number_id: UUID | None
    serial_value: str | None
    quantity: int
    unit_price_cents: int
    tax_cents: int
    line_total_cents: int
    unit_type: UnitType = "PIECE"
    list_price_cents: int | None = None
    price_override_by_id: UUID | None = None
    tax_rate_bps: int | None = None
    description: str | None = None
    cost_cents: int | None = None


class SaleTenderOut(ApiModel):
    method: PaymentMethod
    amount_cents: int
    reference: str
    currency: str | None = None
    foreign_amount_cents: int | None = None


class SaleOut(ApiModel):
    id: UUID
    store_id: UUID
    cashier_id: UUID
    sales_associate_id: UUID | None = None
    status: SaleStatus
    currency: str
    payment_method: PaymentMethod
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    client_sale_id: str
    invoice_number: str | None = None
    items: list[SaleItemOut]
    sale_type: SaleType = "RETAIL"
    customer_id: UUID | None = None
    customer_name: str | None = None
    is_quote_proforma: bool = False
    quote_expiry_date: datetime | None = None
    quote_status: QuoteStatus | None = None
    converted_sale_id: UUID | None = None
    payment_status: PaymentStatus = "PAID"
    amount_paid_cents: int = 0
    due_balance_cents: int = 0
    due_date: datetime | None = None
    tenders: list[SaleTenderOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RepairOut(ApiModel):
    id: UUID
    store_id: UUID
    customer_name: str
    customer_phone: str
    device_model: str
    identifier_kind: SerialKind
    identifier_value: str
    issue: str
    status: RepairStatus
    estimated_cost_cents: int
    currency: str
    created_at: datetime
    updated_at: datetime
    ownership: Literal["customer", "internal"] = "customer"
    product_id: UUID | None = None
    reference: str = ""
    technician_name: str | None = None
    promised_at: datetime | None = None
    deposit_held_cents: int = 0
    warranty_status: str | None = None
    overdue: bool = False
    # Parts and labour totals. Null unless the caller may see internal cost.
    parts_cents: int | None = None
    labour_cents: int | None = None


class CategorySlice(ApiModel):
    category: str
    units: int
    revenue_cents: int


class PaymentSplit(ApiModel):
    method: PaymentMethod
    revenue_cents: int


class AnalyticsSummary(ApiModel):
    timeframe: AnalyticsTimeframe
    currency: str
    net_revenue_cents: int
    units_sold: int
    average_ticket_cents: int
    units_growth_bps: int | None
    revenue_series: list[int]
    categories: list[CategorySlice]
    payment_split: list[PaymentSplit]
    wholesale_revenue_cents: int = 0
    retail_revenue_cents: int = 0
    receivables_cents: int = 0
    cogs_cents: int = 0
    gross_margin_cents: int = 0


class ReturnConditionOut(ApiModel):
    key: str
    label: str
    restock: bool
    fee_bps: int
    serial_status: SerialStatus


class ReturnReasonOut(ApiModel):
    key: str
    label: str


class ReturnPolicyOut(ApiModel):
    window_days: int
    # Refunds older than window_days and within window_days + exchange_window_days go to an exchange voucher only.
    exchange_window_days: int = 0
    open_box_fee_bps: int
    serial_status_by_condition: dict[str, SerialStatus]
    preset: str = "electronics"
    conditions: list[ReturnConditionOut] = Field(default_factory=list)
    reasons: list[ReturnReasonOut] = Field(default_factory=list)


class ReceiptItemOut(ApiModel):
    sale_item_id: UUID
    product_id: UUID
    sku: str
    name: str
    category: str
    is_serialized: bool
    serial_kind: SerialKind | None
    serial_last4: str | None
    quantity: int
    returned_quantity: int
    unit_price_cents: int
    tax_cents: int
    refunded_tax_cents: int
    line_total_cents: int
    warranty_expires_at: datetime | None = None
    # Weighed lines: quantity counts grams and unit_price_cents is per kilogram.
    sold_by_weight: bool = False
    # Promotion plus cashier discount on the whole line (before VAT); returned units carry their share.
    discount_cents: int = 0
    # Final-sale lines return only with a manager; gift card lines never return (void the card instead).
    final_sale: bool = False
    gift_card: bool = False
    variant: str | None = None


class ReceiptOut(ApiModel):
    sale_id: UUID
    invoice: str
    store_id: UUID
    cashier_id: UUID
    status: SaleStatus
    currency: str
    payment_method: PaymentMethod
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    refunded_cents: int
    card_refundable_cents: int
    created_at: datetime
    policy: ReturnPolicyOut
    items: list[ReceiptItemOut]


class ReturnItemOut(ApiModel):
    id: UUID
    sale_item_id: UUID
    product_id: UUID
    serial_number_id: UUID | None
    quantity: int
    unit_price_cents: int
    tax_refund_cents: int
    restocking_fee_cents: int
    refund_cents: int
    condition_status: ReturnCondition
    reason_code: ReturnReason


class ReturnTenderOut(ApiModel):
    method: RefundMethod
    amount_cents: int
    store_credit_code: str | None


class ReturnOut(ApiModel):
    id: UUID
    original_sale_id: UUID
    store_id: UUID
    cashier_id: UUID
    approved_by_id: UUID | None
    currency: str
    subtotal_cents: int
    tax_refund_cents: int
    restocking_fee_cents: int
    total_refund_cents: int
    refund_method: RefundMethod
    reason_notes: str
    items: list[ReturnItemOut]
    tenders: list[ReturnTenderOut]
    credit_note_number: str | None = None
    created_at: datetime


class ConditionSlice(ApiModel):
    condition: ReturnCondition
    units: int


class TenderSlice(ApiModel):
    method: RefundMethod
    amount_cents: int


class ReturnedProductRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    units_sold: int
    units_returned: int
    defective_units: int
    return_rate_bps: int
    refund_cents: int
    last_returned_at: datetime


class CashierReturnRow(ApiModel):
    cashier_id: UUID
    full_name: str
    role_name: str
    return_count: int
    refund_cents: int
    override_count: int
    outside_window_count: int
    last_return_at: datetime
    flagged: bool


class OverrideLogRow(ApiModel):
    id: UUID
    return_id: UUID
    created_at: datetime
    cashier_name: str
    approver_name: str | None
    reasons: list[OverrideReason]
    refund_cents: int
    note: str


class ReturnsAnalytics(ApiModel):
    timeframe: AnalyticsTimeframe
    currency: str
    return_count: int
    units_returned: int
    units_sold: int
    return_rate_bps: int
    refund_cents: int
    restocking_fee_cents: int
    defective_units: int
    defective_rate_bps: int
    override_count: int
    refund_series: list[int]
    conditions: list[ConditionSlice]
    tenders: list[TenderSlice]
    top_products: list[ReturnedProductRow]
    cashiers: list[CashierReturnRow]
    overrides: list[OverrideLogRow]
