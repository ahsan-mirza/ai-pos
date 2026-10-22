from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ImportSource = Literal["EXCEL", "CSV", "PDF_INVOICE", "MANUAL"]
BatchStatus = Literal["ACTIVE", "PARTIALLY_SOLD", "EXHAUSTED", "REVERSED"]
ImportField = Literal[
    "name",
    "code",
    "quantity",
    "cost",
    "price",
    "model_number",
    "category",
    "sub_category",
    "serials",
    "expiry_date",
]
REQUIRED_FIELDS: tuple[ImportField, ...] = ("name", "code", "quantity", "cost", "price")
RowStatus = Literal["NEW", "EXISTING", "ERROR"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Suppliers and templates ---------------------------------------------------------------------


class SupplierCreate(ApiModel):
    name: str = Field(min_length=2, max_length=120)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)


class SupplierOut(ApiModel):
    id: UUID
    name: str
    code: str
    contact_name: str | None
    phone: str | None
    email: str | None
    is_active: bool
    batch_count: int


class ImportOptions(ApiModel):
    auto_generate_codes: bool = False
    update_master_price: bool = False


class TemplateWrite(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    supplier_id: UUID | None = None
    mapping: dict[ImportField, str]
    options: ImportOptions = Field(default_factory=ImportOptions)


class TemplateOut(ApiModel):
    id: UUID
    name: str
    supplier_id: UUID | None
    supplier_name: str | None
    mapping: dict[str, str]
    options: ImportOptions
    updated_at: datetime


# --- Upload, preview and commit ------------------------------------------------------------------


class UploadOut(ApiModel):
    upload_id: str
    file_name: str
    import_source: ImportSource
    headers: list[str]
    sample_rows: list[list[str]]
    total_rows: int
    suggested_mapping: dict[str, str]
    warnings: list[str]


class ImportRow(ApiModel):
    """One purchase line, as mapped from the file and possibly corrected in the preview grid."""

    row_number: int = Field(ge=1)
    include: bool = True
    name: str = Field(default="", max_length=160)
    code: str = Field(default="", max_length=64)
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    cost_cents: int | None = Field(default=None, ge=0, le=10**11)
    price_cents: int | None = Field(default=None, ge=0, le=10**11)
    model_number: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=80)
    sub_category: str = Field(default="", max_length=80)
    serials: list[str] = Field(default_factory=list, max_length=5000)
    expiry_date: date | None = None


class PreviewRequest(ApiModel):
    upload_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    store_id: UUID
    mapping: dict[ImportField, str]
    options: ImportOptions = Field(default_factory=ImportOptions)
    # Rows as edited in the preview grid; omitted, the rows are mapped fresh from the uploaded file.
    rows: list[ImportRow] | None = Field(default=None, max_length=5000)


class PreviewRow(ImportRow):
    status: RowStatus
    product_id: UUID | None
    existing_name: str | None
    existing_cost_cents: int | None
    existing_price_cents: int | None
    is_serialized: bool
    generated_code: bool
    errors: list[str]
    warnings: list[str]


class PreviewTotals(ApiModel):
    rows: int
    included: int
    new_products: int
    existing_products: int
    errors: int
    units: int
    cost_cents: int
    retail_cents: int


class PreviewOut(ApiModel):
    upload_id: str
    currency: str
    rows: list[PreviewRow]
    totals: PreviewTotals


class CommitRequest(ApiModel):
    upload_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    store_id: UUID
    supplier_id: UUID | None = None
    mapping: dict[ImportField, str]
    options: ImportOptions = Field(default_factory=ImportOptions)
    rows: list[ImportRow] = Field(min_length=1, max_length=5000)
    save_template_as: str | None = Field(default=None, min_length=2, max_length=80)
    notes: str = Field(default="", max_length=1000)
    # Supplier-owned stock, settled as it sells; needs a supplier.
    consignment: bool = False


class RowErrors(ApiModel):
    row_number: int
    errors: list[str]


# --- Batches -------------------------------------------------------------------------------------


class BatchRow(ApiModel):
    id: UUID
    batch_number: str
    store_id: UUID
    store_code: str
    store_name: str
    supplier_id: UUID | None
    supplier_name: str | None
    import_source: ImportSource
    file_name: str | None
    status: BatchStatus
    currency: str
    line_count: int
    total_items_count: int
    total_cost_amount: int
    units_remaining: int
    units_sold: int
    sold_percent: float
    revenue_cents: int
    realized_profit_cents: int
    created_by_name: str | None
    created_at: datetime
    is_consignment: bool = False


class BatchLedgerTotals(ApiModel):
    batches: int
    units: int
    cost_cents: int
    remaining_cost_cents: int
    realized_profit_cents: int


class BatchPage(ApiModel):
    rows: list[BatchRow]
    total: int
    totals: BatchLedgerTotals


class BatchItemOut(ApiModel):
    id: UUID
    position: int
    product_id: UUID
    product_name: str
    sku: str
    barcode: str
    is_serialized: bool
    quantity_imported: int
    quantity_remaining: int
    quantity_sold: int
    quantity_removed: int
    purchase_cost_per_unit: int
    selling_price_per_unit: int
    master_price_cents: int
    expiry_date: date | None
    serial_count: int
    serials_last4: list[str]
    revenue_cents: int
    cogs_cents: int
    realized_profit_cents: int
    editable_quantity: bool


class BatchSaleOut(ApiModel):
    sale_id: UUID
    sale_item_id: UUID
    product_name: str
    quantity: int
    returned: int
    unit_cost_cents: int
    unit_sale_cents: int
    profit_cents: int
    sold_at: datetime


class BatchDetail(BatchRow):
    notes: str
    mapping_template_used: dict | None
    file_url: str | None
    reversal_reason: str | None
    reversed_at: datetime | None
    reversed_by_name: str | None
    cogs_cents: int
    items: list[BatchItemOut]
    sales: list[BatchSaleOut]


class BatchItemUpdate(ApiModel):
    id: UUID
    purchase_cost_per_unit: int | None = Field(default=None, ge=0, le=10**11)
    selling_price_per_unit: int | None = Field(default=None, ge=0, le=10**11)
    quantity_imported: int | None = Field(default=None, ge=0, le=1_000_000)
    expiry_date: date | None = None
    clear_expiry: bool = False


class BatchUpdate(ApiModel):
    supplier_id: UUID | None = None
    clear_supplier: bool = False
    notes: str | None = Field(default=None, max_length=1000)
    items: list[BatchItemUpdate] = Field(default_factory=list, max_length=5000)
    apply_price_to_master: bool = False
    reason: str | None = Field(default=None, max_length=500)


class RollbackConflict(ApiModel):
    product_name: str
    sku: str
    imported: int
    sold: int
    removed: int
    remaining: int
    reversible: int
    blocked: int
    detail: str


class RollbackPreview(ApiModel):
    batch_id: UUID
    batch_number: str
    mode: Literal["DELETE", "REVERSE"]
    units_to_remove: int
    units_sold: int
    units_blocked: int
    cost_written_back_cents: int
    conflicts: list[RollbackConflict]
    can_rollback: bool


class RollbackRequest(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class RollbackResult(ApiModel):
    batch_id: UUID
    batch_number: str
    mode: Literal["DELETE", "REVERSE"]
    units_removed: int
    status: BatchStatus | Literal["DELETED"]
