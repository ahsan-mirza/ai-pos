from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

ApprovalKind = Literal["PRICE_OVERRIDE", "BELOW_FLOOR", "CREDIT_LIMIT", "REFUND"]
ApprovalStatus = Literal["PENDING", "APPROVED", "DECLINED", "CANCELLED", "EXPIRED"]


class ApprovalCreate(ApiModel):
    kind: ApprovalKind
    requested_by_id: UUID
    title: str = Field(min_length=3, max_length=160)
    details: list[str] = Field(default_factory=list, max_length=6)
    amount_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)
    store_id: UUID | None = None


class ApprovalDecision(ApiModel):
    note: str = Field(default="", max_length=250)


class ApproverOut(ApiModel):
    """Same shape as the register's cashier profile, so an approval from a phone slots in for a typed PIN."""

    id: UUID
    username: str
    full_name: str
    store_id: UUID | None
    role_name: str
    permissions: list[str]


class ApprovalOut(ApiModel):
    id: UUID
    kind: ApprovalKind
    status: ApprovalStatus
    store_id: UUID | None
    store_code: str | None
    requested_by_name: str | None
    title: str
    details: list[str]
    amount_cents: int | None
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by_name: str | None
    note: str
    approver: ApproverOut | None = None
