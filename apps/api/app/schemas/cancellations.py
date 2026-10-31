from datetime import date, datetime
from uuid import UUID

from app.schemas.payloads import ApiModel


class CancellationItem(ApiModel):
    name: str
    quantity: int
    sku: str


class CancellationRow(ApiModel):
    kind: str
    order_id: UUID
    number: str
    store_id: UUID
    order_type: str
    full: bool
    status: str
    reason_code: str
    reason_label: str
    initiator: str
    note: str
    cancelled_value_cents: int
    created_at: datetime
    cancelled_at: datetime | None
    employee_name: str | None
    employee_role: str | None
    approver_id: UUID | None
    items: list[CancellationItem]


class CancellationReasonCount(ApiModel):
    code: str
    label: str
    initiator: str
    count: int


class CancellationReport(ApiModel):
    start: date
    end: date
    created_orders: int
    fully_cancelled: int
    partially_cancelled: int
    full_cancellation_rate: float
    partial_cancellation_rate: float
    cancelled_value_cents: int
    customer_requested: int
    employee_initiated: int
    average_hours_to_cancel: float | None
    reasons: list[CancellationReasonCount]
    total: int
    rows: list[CancellationRow]
