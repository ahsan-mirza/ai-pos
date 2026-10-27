from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel, PaymentMethod, RepairOut, RepairPriority, RepairStatus, SaleTenderPayload

RepairLineKind = Literal["PART", "LABOUR"]
ApprovalStatus = Literal["PENDING", "APPROVED", "DECLINED"]
AttachmentKind = Literal["INTAKE", "DIAGNOSIS", "AFTER"]
DepositMethod = Literal["cash", "card", "transfer"]


class RepairStatusChange(ApiModel):
    status: RepairStatus
    note: str = Field(default="", max_length=500)


class RepairLineCreate(ApiModel):
    """Parts need product_id (a stocked product). Labour may omit it to use the open-price labour product."""

    kind: RepairLineKind
    product_id: UUID | None = None
    description: str = Field(default="", max_length=160)
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_price_cents: int | None = Field(default=None, ge=0)


class RepairInvoiceCreate(ApiModel):
    payment_method: PaymentMethod = "cash"
    tenders: list[SaleTenderPayload] | None = Field(default=None, max_length=6)


class RepairAssign(ApiModel):
    technician_id: UUID | None = None
    clear_technician: bool = False
    priority: RepairPriority | None = None
    promised_at: datetime | None = None
    clear_promise: bool = False
    repair_warranty_days: int | None = Field(default=None, ge=0, le=730)


class ApprovalRequest(ApiModel):
    # Defaults to the parts and labour on the ticket, else the booking estimate.
    amount_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=300)
    send_link: bool = True


class ApprovalDecision(ApiModel):
    decision: Literal["approve", "decline"]
    channel: Literal["in_store", "phone"] = "in_store"
    note: str = Field(default="", max_length=300)


class DepositCreate(ApiModel):
    amount_cents: int = Field(ge=1, le=100_000_000)
    method: DepositMethod = "cash"
    reference: str = Field(default="", max_length=64)
    shift_id: UUID | None = None


class PickupRequest(ApiModel):
    note: str = Field(default="", max_length=300)


class RepairEventOut(ApiModel):
    from_status: str | None
    to_status: str
    note: str
    source: str
    user_name: str | None
    occurred_at: datetime


class RepairLineOut(ApiModel):
    id: UUID
    kind: RepairLineKind
    product_id: UUID
    sku: str
    description: str
    quantity: int
    unit_price_cents: int
    line_cents: int
    reserved_quantity: int = 0


class RepairAttachmentOut(ApiModel):
    id: UUID
    kind: AttachmentKind
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class RepairDepositOut(ApiModel):
    id: UUID
    amount_cents: int
    method: str
    reference: str
    status: Literal["HELD", "APPLIED", "REFUNDED"]
    received_at: datetime
    received_by_name: str | None


class RepairWarrantyOut(ApiModel):
    id: UUID
    starts_at: datetime
    expires_at: datetime
    status: str


class RepairDetail(RepairOut):
    customer_id: UUID | None
    warranty_status: str | None
    sale_id: UUID | None
    invoice_number: str | None
    events: list[RepairEventOut]
    lines: list[RepairLineOut]
    parts_cents: int
    labour_cents: int
    total_cents: int
    reference: str = ""
    technician_id: UUID | None = None
    technician_name: str | None = None
    priority: RepairPriority = "NORMAL"
    promised_at: datetime | None = None
    has_passcode: bool = False
    intake_checklist: dict[str, bool | str] | None = None
    accessories: str = ""
    approval_status: ApprovalStatus | None = None
    approval_amount_cents: int | None = None
    approval_requested_at: datetime | None = None
    approval_decided_at: datetime | None = None
    approval_channel: str | None = None
    approval_note: str = ""
    repair_warranty_days: int = 90
    tracking_url: str | None = None
    picked_up_at: datetime | None = None
    attachments: list[RepairAttachmentOut] = Field(default_factory=list)
    deposits: list[RepairDepositOut] = Field(default_factory=list)
    deposit_held_cents: int = 0
    balance_due_cents: int = 0
    parts_short: bool = False
    repair_warranty: RepairWarrantyOut | None = None
    selling_price_cents: int | None = None
    purchase_cost_cents: int | None = None
    market_value: str = "Market value not configured"
    value_warning: str | None = None


class RepairDeviceHit(ApiModel):
    product_id: UUID
    name: str
    sku: str
    selling_price_cents: int
    purchase_cost_cents: int | None
    serial_status: str | None
    available: bool
    warning: str | None
    market_value: str = "Market value not configured"


class ApprovalSent(ApiModel):
    ticket: RepairDetail
    # The link the customer opens (also returned so staff can share it by hand).
    approval_url: str | None
    message_status: str | None


class BoardCard(ApiModel):
    id: UUID
    reference: str
    device_model: str
    customer_name: str
    issue: str
    status: RepairStatus
    priority: RepairPriority
    technician_id: UUID | None
    technician_name: str | None
    promised_at: datetime | None
    overdue: bool
    approval_status: ApprovalStatus | None
    parts_short: bool
    deposit_held_cents: int
    estimated_cost_cents: int
    currency: str
    updated_at: datetime


class BoardColumn(ApiModel):
    status: RepairStatus
    cards: list[BoardCard]


class RepairBoard(ApiModel):
    columns: list[BoardColumn]
    technicians: list[dict]


class AttachmentUpload(ApiModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"]
    data_base64: str = Field(min_length=1, max_length=12_000_000)
    file_name: str = Field(default="photo", max_length=160)
    kind: AttachmentKind = "INTAKE"


class JobCardFile(ApiModel):
    filename: str
    pdf_base64: str


class PasscodeOut(ApiModel):
    passcode: str


class TrackingOut(ApiModel):
    reference: str
    device_model: str
    status: RepairStatus
    status_label: str
    store_name: str
    promised_at: datetime | None
    approval_status: ApprovalStatus | None
    total_cents: int
    balance_due_cents: int
    currency: str
    updated_at: datetime
    steps: list[dict]
