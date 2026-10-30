from datetime import datetime
from uuid import UUID

from app.schemas.inventory import ApiModel, PurchaseOrderStatus
from app.schemas.payloads import SaleStatus, SerialKind, SerialStatus


class ProductSaleRow(ApiModel):
    sale_id: UUID
    sale_item_id: UUID
    invoice: str
    sold_at: datetime
    store_id: UUID
    store_code: str
    store_name: str
    cashier_name: str | None
    status: SaleStatus
    currency: str
    quantity: int
    unit_price_cents: int
    tax_cents: int
    line_total_cents: int
    # Cost snapshotted when the sale posted. Null when the units had no cost layer.
    cost_cents: int | None = None
    cost_estimated: bool = False
    gross_profit_cents: int | None = None


class ProductSalesHistory(ApiModel):
    """`summary_*` cover every matching sale in `currency` (the business currency), not just the returned page."""

    currency: str
    units_sold: int
    revenue_cents: int
    average_selling_price_cents: int | None
    sale_count: int
    rows: list[ProductSaleRow]


class ProductPurchaseRow(ApiModel):
    purchase_order_id: UUID
    po_number: str
    po_status: PurchaseOrderStatus
    goods_receipt_id: UUID | None
    grn_number: str | None
    supplier_name: str
    store_id: UUID
    store_code: str
    ordered_at: datetime | None
    received_at: datetime | None
    unit_cost_cents: int
    quantity_ordered: int
    quantity_received: int
    total_cost_cents: int


class ProductPurchaseHistory(ApiModel):
    latest_unit_cost_cents: int | None
    average_unit_cost_cents: int | None
    units_received: int
    total_spend_cents: int
    rows: list[ProductPurchaseRow]


class ProductSerialRow(ApiModel):
    serial_number_id: UUID
    kind: SerialKind
    last4: str
    status: SerialStatus
    store_id: UUID
    store_code: str
    store_name: str
    sold_at: datetime | None
    sale_invoice: str | None
    updated_at: datetime


class ProductSerials(ApiModel):
    total: int
    status_counts: dict[str, int]
    rows: list[ProductSerialRow]


class CostLayerRow(ApiModel):
    batch_item_id: UUID
    batch_id: UUID
    batch_number: str
    goods_receipt_id: UUID | None
    receipt_date: datetime
    original_quantity: int
    remaining_quantity: int
    unit_cost_cents: int
    remaining_value_cents: int
    consumed_quantity: int
    source: str = "import"


class StoreCostRow(ApiModel):
    store_id: UUID
    store_code: str
    on_hand: int
    reserved: int
    available: int
    weighted_average_cost_cents: int | None
    inventory_value_cents: int
    uncosted_quantity: int


class ProductCosting(ApiModel):
    method: str
    currency: str
    default_cost_cents: int | None
    last_purchase_cost_cents: int | None
    weighted_average_cost_cents: int | None
    on_hand: int
    reserved: int
    available: int
    inventory_value_cents: int
    uncosted_quantity: int
    realized_revenue_cents: int
    realized_cogs_cents: int
    realized_profit_cents: int
    layers: list[CostLayerRow]
    stores: list[StoreCostRow]


class CostGapRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    store_id: UUID
    store_code: str
    on_hand: int
    layered_quantity: int
    uncosted_quantity: int


class CostReconciliation(ApiModel):
    """Stock with no cost layer. Opening quantities are not given a made-up purchase."""

    method: str
    rows: list[CostGapRow]
