import re
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.catalogue import FashionAttributes, FashionAttributesOut
from app.schemas.payloads import Emirate, SerialKind, SerialStatus, TaxCategory, UnitType

MovementType = Literal[
    "PURCHASE_IN",
    "SALE_OUT",
    "RETURN_IN",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "DAMAGE_SHRINKAGE",
    "AUDIT_ADJUSTMENT",
    "PURCHASE_REVERSAL",
    "RECIPE_OUT",
]
StockStatus = Literal["ok", "low", "out", "over", "unavailable"]
ItemType = Literal["MADE_TO_ORDER", "RAW_INGREDIENT", "PRE_PACKAGED"]
MenuStatus = Literal["available", "unavailable", "no_recipe", "meal"]
StockView = Literal["stock", "menu"]
PurchaseOrderStatus = Literal["draft", "ordered", "partially_received", "received", "cancelled"]
TransferStatus = Literal["requested", "in_transit", "received", "cancelled"]
CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,31}")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if CODE.fullmatch(normalized) is None:
        raise ValueError("code must be 1-32 characters: letters, digits, and dashes.")
    return normalized


def _name(value: str) -> str:
    stripped = " ".join(value.split())
    if len(stripped) < 2:
        raise ValueError("name must be at least 2 characters.")
    return stripped


# --- Categories ----------------------------------------------------------------------------------


class SubCategoryOut(ApiModel):
    id: UUID
    category_id: UUID
    name: str
    code: str
    description: str
    product_count: int


class CategoryOut(ApiModel):
    id: UUID
    name: str
    code: str
    description: str
    product_count: int
    created_at: datetime
    sub_categories: list[SubCategoryOut]


class CategoryWrite(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    code: str | None = Field(default=None, max_length=32)
    description: str = Field(default="", max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _name(value)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return _code(value)


class CategoryUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    code: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else _name(value)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return _code(value)


# --- Brands, models, and variants ----------------------------------------------------------------

MAX_VARIANT_ATTRIBUTES = 8
ATTRIBUTE_KEY = re.compile(r"[a-z][a-z0-9_]{0,23}")


def variant_attributes(value: dict[str, str] | None) -> dict[str, str]:
    """Keys are short snake_case names (storage, ram, color, ...); blank values are dropped."""
    cleaned: dict[str, str] = {}
    for key, raw in (value or {}).items():
        name = key.strip().lower().replace(" ", "_")
        if ATTRIBUTE_KEY.fullmatch(name) is None:
            raise ValueError(f"Attribute '{key}' must be 1-24 letters, digits, or underscores.")
        text = " ".join(str(raw).split())
        if len(text) > 60:
            raise ValueError(f"Attribute '{key}' must be at most 60 characters.")
        if text:
            cleaned[name] = text
    if len(cleaned) > MAX_VARIANT_ATTRIBUTES:
        raise ValueError(f"Use at most {MAX_VARIANT_ATTRIBUTES} variant attributes.")
    return cleaned


MAX_SPECIFICATIONS = 16


def specifications(value: dict[str, str] | None) -> dict[str, str]:
    """Category technical details. Blank values are dropped. Keys stay short snake_case names."""
    cleaned: dict[str, str] = {}
    for key, raw in (value or {}).items():
        name = key.strip().lower().replace(" ", "_")
        if ATTRIBUTE_KEY.fullmatch(name) is None:
            raise ValueError(f"Specification '{key}' must be 1-24 letters, digits, or underscores.")
        text = " ".join(str(raw).split())
        if len(text) > 80:
            raise ValueError(f"Specification '{key}' must be at most 80 characters.")
        if text:
            cleaned[name] = text
    if len(cleaned) > MAX_SPECIFICATIONS:
        raise ValueError(f"Use at most {MAX_SPECIFICATIONS} specifications.")
    return cleaned


class BrandOut(ApiModel):
    id: UUID
    name: str
    code: str
    description: str
    sub_category_ids: list[UUID]
    model_count: int
    product_count: int
    created_at: datetime


class BrandWrite(CategoryWrite):
    sub_category_ids: list[UUID] = Field(default_factory=list, max_length=200)


class ProductModelOut(FashionAttributesOut):
    id: UUID
    brand_id: UUID
    brand_name: str
    category_id: UUID
    category_name: str
    sub_category_id: UUID
    sub_category_name: str
    name: str
    code: str | None
    release_year: int | None
    description: str
    variant_count: int


class ProductModelWrite(FashionAttributes):
    brand_id: UUID
    sub_category_id: UUID
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=32)
    release_year: int | None = Field(default=None, ge=1980, le=2100)
    description: str = Field(default="", max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("name is required.")
        return stripped

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return _code(value) if value and value.strip() else None


class ProductModelUpdate(FashionAttributes):
    """Attribute fields that are sent replace the model's value (null clears it) and are copied to its variants."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=32)
    release_year: int | None = Field(default=None, ge=1980, le=2100)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else ProductModelWrite.normalize_name(value)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return _code(value) if value and value.strip() else None


# --- Stock ---------------------------------------------------------------------------------------


class StockRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    brand: str | None
    model_number: str | None
    is_serialized: bool
    category: str
    category_id: UUID | None
    sub_category: str | None
    sub_category_id: UUID | None
    brand_id: UUID | None = None
    product_model_id: UUID | None = None
    model_name: str | None = None
    store_id: UUID | None
    store_code: str | None
    store_name: str | None
    store_count: int
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    min_reorder_level: int
    max_stock_level: int | None
    aisle_shelf_location: str | None
    thumb_url: str | None = None
    status: StockStatus
    # Quantities of weighed products count grams.
    sold_by_weight: bool = False
    item_type: ItemType = "PRE_PACKAGED"
    # Menu view: how many portions ingredient stock can still make, and why.
    max_portions: int | None = None
    limiting_ingredient: str | None = None
    availability_note: str | None = None
    menu_status: MenuStatus | None = None


class StockSummary(ApiModel):
    consolidated: bool
    store_id: UUID | None
    rows: list[StockRow]
    units_on_hand: int
    low_count: int
    out_count: int
    view: StockView = "stock"


class LevelUpdate(ApiModel):
    min_reorder_level: int | None = Field(default=None, ge=0, le=1_000_000)
    max_stock_level: int | None = Field(default=None, ge=0, le=1_000_000)
    clear_max: bool = False
    aisle_shelf_location: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.clear_max and self.max_stock_level is not None:
            raise ValueError("Use either max_stock_level or clear_max, not both.")
        if (
            self.max_stock_level is not None
            and self.min_reorder_level is not None
            and self.max_stock_level < self.min_reorder_level
        ):
            raise ValueError("max_stock_level must be at least min_reorder_level.")
        return self


class SerialInput(ApiModel):
    kind: SerialKind
    value: str = Field(min_length=4, max_length=64)


AdjustmentReason = Literal[
    "PHYSICAL_COUNT_AUDIT",
    "DAMAGED_OR_EXPIRED",
    "STOLEN_SHRINKAGE",
    "SUPPLIER_SAMPLE_IN",
    "INCORRECT_ENTRY_CORRECTION",
    "INTERNAL_DEMO_USE",
    "OTHER",
]
AdjustmentMode = Literal["add", "remove", "set"]
NOTE_MIN_LENGTH = 10


class ManualAdjustment(ApiModel):
    """add/remove move `quantity` units; set reconciles the branch on-hand to exactly `quantity`."""

    adjustment_id: UUID
    product_id: UUID
    store_id: UUID
    mode: AdjustmentMode
    quantity: int = Field(ge=0, le=100_000)
    reason_code: AdjustmentReason
    note: str = Field(max_length=1000)
    new_serials: list[SerialInput] = Field(default_factory=list, max_length=1000)
    remove_serial_ids: list[UUID] = Field(default_factory=list, max_length=1000)

    @field_validator("note")
    @classmethod
    def explained(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if len(stripped) < NOTE_MIN_LENGTH:
            raise ValueError(f"Explain the adjustment in at least {NOTE_MIN_LENGTH} characters.")
        return stripped

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.mode in {"add", "remove"} and self.quantity < 1:
            raise ValueError("Adjust by at least one unit.")
        keys = [(serial.kind, serial.value.strip().upper()) for serial in self.new_serials]
        if len(set(keys)) != len(keys):
            raise ValueError("The same IMEI or serial number is listed twice.")
        return self


class StoreSerial(ApiModel):
    id: UUID
    kind: SerialKind
    value: str
    status: SerialStatus
    updated_at: datetime


class MovementOut(ApiModel):
    id: UUID
    product_id: UUID
    sku: str
    product_name: str
    store_id: UUID
    store_code: str
    serial_number_id: UUID | None
    movement_type: MovementType
    quantity: int
    quantity_after: int
    reference_type: str
    reference_id: UUID | None
    reason_code: AdjustmentReason | None = None
    user_name: str | None
    note: str
    created_at: datetime


class ManualAdjustmentOut(ApiModel):
    adjustment_id: UUID
    duplicate: bool
    quantity_change: int
    row: StockRow
    movements: list[MovementOut]


class BranchStock(ApiModel):
    store_id: UUID
    store_code: str
    store_name: str
    is_warehouse: bool
    address: str | None
    phone: str | None
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    aisle_shelf_location: str | None


class ProductBrief(ApiModel):
    id: UUID
    sku: str
    name: str
    is_serialized: bool


class SerialLocation(ApiModel):
    serial_number_id: UUID
    kind: SerialKind
    last4: str
    status: SerialStatus
    store_id: UUID
    store_code: str
    store_name: str
    is_warehouse: bool
    aisle_shelf_location: str | None


class AvailabilityOut(ApiModel):
    product: ProductBrief
    branches: list[BranchStock]
    serial: SerialLocation | None


class TransferBrief(ApiModel):
    id: UUID
    number: str
    status: TransferStatus
    source_store_code: str
    destination_store_code: str
    shipped_at: datetime | None
    received_at: datetime | None


class SerialTraceOut(ApiModel):
    product: ProductBrief
    location: SerialLocation
    history: list[MovementOut]
    transfers: list[TransferBrief]


# --- Purchasing ----------------------------------------------------------------------------------


class PurchaseOrderLineIn(ApiModel):
    product_id: UUID
    quantity_ordered: int = Field(ge=1, le=100_000)
    unit_cost_cents: int = Field(default=0, ge=0)


class PurchaseOrderCreate(ApiModel):
    supplier_name: str = Field(min_length=2, max_length=120)
    destination_store_id: UUID
    expected_at: datetime | None = None
    notes: str = Field(default="", max_length=2000)
    lines: list[PurchaseOrderLineIn] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_products(self) -> Self:
        ids = [line.product_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Each product can appear only once per purchase order.")
        return self


class ReceiveLineIn(ApiModel):
    purchase_order_line_id: UUID
    quantity: int = Field(ge=1, le=100_000)
    serials: list[SerialInput] = Field(default_factory=list, max_length=1000)
    aisle_shelf_location: str | None = Field(default=None, max_length=64)


class ReceiveRequest(ApiModel):
    note: str = Field(default="", max_length=255)
    lines: list[ReceiveLineIn] = Field(min_length=1, max_length=200)


class PurchaseOrderLineOut(ApiModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    is_serialized: bool
    quantity_ordered: int
    quantity_received: int
    unit_cost_cents: int


class GoodsReceiptLineOut(ApiModel):
    purchase_order_line_id: UUID
    product_id: UUID
    quantity: int


class GoodsReceiptOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    received_by_name: str | None
    note: str
    created_at: datetime
    lines: list[GoodsReceiptLineOut]


class PurchaseOrderOut(ApiModel):
    id: UUID
    number: str
    supplier_name: str
    destination_store_id: UUID
    destination_store_code: str
    destination_store_name: str
    status: PurchaseOrderStatus
    notes: str
    expected_at: datetime | None
    ordered_at: datetime | None
    received_at: datetime | None
    created_at: datetime
    created_by_name: str | None
    total_cost_cents: int
    lines: list[PurchaseOrderLineOut]
    receipts: list[GoodsReceiptOut]


# --- Transfers -----------------------------------------------------------------------------------


class TransferLineIn(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100_000)


class TransferCreate(ApiModel):
    source_store_id: UUID
    destination_store_id: UUID
    note: str = Field(default="", max_length=255)
    lines: list[TransferLineIn] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.source_store_id == self.destination_store_id:
            raise ValueError("Source and destination must be different stores.")
        ids = [line.product_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Each product can appear only once per transfer.")
        return self


class TransferShipLine(ApiModel):
    transfer_line_id: UUID
    serials: list[SerialInput] = Field(min_length=1, max_length=1000)


class TransferShip(ApiModel):
    serial_lines: list[TransferShipLine] = Field(default_factory=list, max_length=200)


class TransferLineOut(ApiModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    is_serialized: bool
    quantity: int


class TransferSerialOut(ApiModel):
    serial_number_id: UUID
    transfer_line_id: UUID
    kind: SerialKind
    last4: str
    status: SerialStatus


class TransferOut(ApiModel):
    id: UUID
    number: str
    source_store_id: UUID
    source_store_code: str
    source_store_name: str
    destination_store_id: UUID
    destination_store_code: str
    destination_store_name: str
    status: TransferStatus
    note: str
    requested_by_name: str | None
    shipped_by_name: str | None
    received_by_name: str | None
    created_at: datetime
    shipped_at: datetime | None
    received_at: datetime | None
    lines: list[TransferLineOut]
    serials: list[TransferSerialOut]


# --- Products and stores (portal writes) ---------------------------------------------------------


class ProductCreate(FashionAttributes):
    sku: str = Field(min_length=1, max_length=64)
    barcode: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    model_number: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=80)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    product_model_id: UUID | None = None
    variant_attributes: dict[str, str] = Field(default_factory=dict)
    specifications: dict[str, str] = Field(default_factory=dict)
    price_cents: int = Field(ge=0)
    is_serialized: bool = False
    tax_category: TaxCategory = "STANDARD"
    is_open_price: bool = False
    # Weighed goods: price_cents is per kilogram and opening_quantity counts grams.
    sold_by_weight: bool = False
    plu_code: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    tare_grams: int = Field(default=0, ge=0, le=100_000)
    # Recipes module: kept in stock for dishes only; registers do not sell it.
    is_ingredient: bool = False
    # Prepared dishes are not stocked. Ingredients and packaged goods are.
    item_type: ItemType | None = None
    # Packs it sells in besides the piece (units of measure), e.g. ["CASE_24"].
    sellable_units: list[UnitType] = Field(default_factory=lambda: ["PIECE"], max_length=8)
    opening_store_id: UUID | None = None
    opening_quantity: int = Field(default=0, ge=0, le=1_000_000_000)
    min_reorder_level: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("variant_attributes")
    @classmethod
    def normalize_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        return variant_attributes(value)

    @field_validator("specifications")
    @classmethod
    def normalize_specifications(cls, value: dict[str, str]) -> dict[str, str]:
        return specifications(value)

    @model_validator(mode="after")
    def opening_stock(self) -> Self:
        if self.category_id is None and self.product_model_id is None:
            raise ValueError("Choose a category or a model.")
        if self.opening_quantity and self.opening_store_id is None:
            raise ValueError("Choose the store that holds the opening stock.")
        if self.opening_quantity and self.is_serialized:
            raise ValueError("Serialized stock is added by receiving IMEIs on a purchase order.")
        if self.sold_by_weight and (self.is_serialized or self.is_open_price):
            raise ValueError("Weighed products cannot be serialized or open-price.")
        if self.plu_code and not self.sold_by_weight:
            raise ValueError("Only weighed products carry a scale PLU code.")
        return self


class ProductUpdate(FashionAttributes):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    model_number: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=80)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    clear_sub_category: bool = False
    product_model_id: UUID | None = Field(default=None, description="Send null to detach the product from its model.")
    variant_attributes: dict[str, str] | None = None
    specifications: dict[str, str] | None = None
    price_cents: int | None = Field(default=None, ge=0)
    tax_category: TaxCategory | None = None
    is_open_price: bool | None = None
    sold_by_weight: bool | None = None
    # Send null to clear the PLU.
    plu_code: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    tare_grams: int | None = Field(default=None, ge=0, le=100_000)
    is_ingredient: bool | None = None
    item_type: ItemType | None = None
    sellable_units: list[UnitType] | None = Field(default=None, max_length=8)

    @field_validator("variant_attributes")
    @classmethod
    def normalize_attributes(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return None if value is None else variant_attributes(value)

    @field_validator("specifications")
    @classmethod
    def normalize_specifications(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return None if value is None else specifications(value)


class StoreUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    emirate: Emirate | None = None
    is_warehouse: bool | None = None
    is_active: bool | None = None
