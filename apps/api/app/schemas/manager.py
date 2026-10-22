from datetime import datetime
from uuid import UUID

from app.schemas.payloads import ApiModel


class BranchToday(ApiModel):
    store_id: UUID
    store_code: str
    store_name: str
    sales: int
    revenue_cents: int
    refunds_cents: int
    net_cents: int
    average_basket_cents: int
    last_sale_at: datetime | None


class TopProduct(ApiModel):
    product_id: UUID
    name: str
    quantity: int
    revenue_cents: int


class Attention(ApiModel):
    approvals: int
    timesheets: int | None
    credit_holds: int | None
    cheques_to_deposit: int | None


class ManagerDashboard(ApiModel):
    currency: str
    as_of: datetime
    net_cents: int
    sales: int
    yesterday_net_cents: int
    hourly_cents: list[int]
    branches: list[BranchToday]
    top_products: list[TopProduct]
    attention: Attention


class PendingTimeEntry(ApiModel):
    id: UUID
    user_name: str
    store_code: str
    clock_in_at: datetime
    clock_out_at: datetime
    break_minutes: int
    worked_minutes: int


class CreditHoldRow(ApiModel):
    customer_id: UUID
    name: str
    balance_cents: int
    credit_limit_cents: int
    reason: str | None
    manual: bool
