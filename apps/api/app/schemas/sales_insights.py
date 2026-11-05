"""Sales Insights responses. Amounts are integer cents in the business currency."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InsightWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    timezone: str
    currency: str


class InsightCompare(BaseModel):
    model_config = ConfigDict(extra="forbid")

    net_sales_cents: int
    transactions: int
    # Basis points versus the previous window of the same length. Null when that window had no sales.
    net_change_bps: int | None


class SalesSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: InsightWindow
    gross_sales_cents: int
    discount_cents: int
    tax_cents: int
    # Amount charged on completed receipts (tax included), before refunds.
    charged_cents: int
    refund_cents: int
    # charged_cents minus refunds recorded in the same window.
    net_sales_cents: int
    transactions: int
    items_sold: int
    average_transaction_cents: int
    average_items_per_transaction_bps: int
    voided: int
    compare: InsightCompare


class ProductPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name: str
    sku: str
    category: str
    quantity: int
    gross_cents: int
    discount_cents: int
    net_cents: int
    transactions: int
    contribution_bps: int
    cost_cents: int | None = None


class StaffPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cashier_id: str | None
    name: str
    transactions: int
    items_sold: int
    gross_cents: int
    discount_cents: int
    net_cents: int
    average_cents: int


class CategoryPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    quantity: int
    net_cents: int
    transactions: int
    contribution_bps: int


class PaymentSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    amount_cents: int
    transactions: int


class TrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    charged_cents: int
    transactions: int


class TransactionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    invoice_number: str | None
    created_at: datetime
    cashier: str
    items: int
    gross_cents: int
    discount_cents: int
    net_cents: int
    tax_cents: int
    payment_method: str
    status: str
