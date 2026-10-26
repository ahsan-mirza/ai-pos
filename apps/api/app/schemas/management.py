from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.schemas.payloads import ApiModel


class PnlRow(ApiModel):
    month: str
    store_id: UUID | None
    store_code: str
    net_sales_cents: int
    returns_cents: int
    revenue_cents: int
    cogs_cents: int
    gross_profit_cents: int
    gross_margin_bps: int
    expenses: dict[str, int]
    other_purchases_cents: int
    shrinkage_cents: int
    operating_expenses_cents: int
    operating_profit_cents: int


class PnlReport(ApiModel):
    period_from: date
    period_to: date
    currency: str
    rows: list[PnlRow]
    by_store: list[PnlRow]
    total: PnlRow
    cost_estimated: bool


class ValuationRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    store_id: UUID
    store_code: str
    on_hand: int
    unit_cost_cents: int
    cost_value_cents: int
    retail_value_cents: int
    estimated: bool
    # Supplier-owned units in on_hand; cost_value_cents covers owned units only.
    consignment_units: int = 0


class ValuationGroup(ApiModel):
    key: str
    units: int
    cost_value_cents: int
    retail_value_cents: int


class ValuationReport(ApiModel):
    as_of: datetime
    currency: str
    units: int
    cost_value_cents: int
    retail_value_cents: int
    estimated_units: int
    consignment_units: int = 0
    consignment_value_cents: int = 0
    by_store: list[ValuationGroup]
    by_category: list[ValuationGroup]
    rows: list[ValuationRow]


class AgedStockRow(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    store_id: UUID
    store_code: str
    on_hand: int
    cost_value_cents: int
    last_sold_at: datetime | None
    #: Whole UTC days since the last qualifying sale. Null when the product has never had one.
    days_since_sale: int | None
    units_sold_90d: int
    cover_days: int | None
    status: Literal["SLOW", "DEAD"]
    suggestion: str
    reason: str = ""
    brand: str | None = None
    sold_by_weight: bool = False
    #: Whole UTC days since the first positive stock movement. Null when that date is unknown.
    days_in_stock: int | None = None
    # Carrying cost at the report's annual rate: per month from now, and accrued over the idle clock
    # (last qualifying sale, otherwise the first receipt). Not a fabricated age when both dates are missing.
    holding_cost_month_cents: int = 0
    holding_cost_to_date_cents: int = 0
    price_cents: int = 0
    #: Clearance price: a markdown that grows with idle time, never below the margin floor (or cost).
    #: Null when the shelf price is already at the floor, the cost is missing, or the stock is supplier-owned.
    suggested_price_cents: int | None = None
    markdown_pct: int = 0
    target_markdown_pct: int = 0
    floor_cents: int | None = None
    expected_margin_bps: int | None = None
    cost_estimated: bool = False
    review_required: bool = False
    #: The target markdown could not be applied in full because of cost or the margin floor.
    discount_limited: bool = False


class AgedStockReport(ApiModel):
    as_of: datetime
    currency: str
    slow_days: int
    dead_days: int
    slow_value_cents: int
    dead_value_cents: int
    carrying_rate_bps: int = 2500
    holding_cost_month_cents: int = 0
    holding_cost_to_date_cents: int = 0
    #: Rows matching the filters, before the page slice.
    total: int = 0
    rows: list[AgedStockRow]


class StaffSalesRow(ApiModel):
    user_id: UUID
    name: str
    sales: int
    units: int
    revenue_cents: int
    cogs_cents: int
    gross_profit_cents: int
    gross_margin_bps: int
    average_basket_cents: int
    promotion_discount_cents: int
    override_discount_cents: int
    returns: int
    returns_cents: int


class StaffSalesReport(ApiModel):
    period_from: date
    period_to: date
    currency: str
    rows: list[StaffSalesRow]


class DiscountRow(ApiModel):
    """Cashier discounts one staff member gave for one reason in the period."""

    user_id: UUID
    name: str
    reason: str
    reason_label: str
    lines: int
    discount_cents: int
    # Lines a manager approved because the discount was above the cashier's limit.
    approved_lines: int
    # Discount as a share of the same lines before it, in basis points.
    share_bps: int


class DiscountReasonTotal(ApiModel):
    reason: str
    reason_label: str
    lines: int
    discount_cents: int


class DiscountReport(ApiModel):
    period_from: date
    period_to: date
    currency: str
    total_cents: int
    rows: list[DiscountRow]
    by_reason: list[DiscountReasonTotal]
