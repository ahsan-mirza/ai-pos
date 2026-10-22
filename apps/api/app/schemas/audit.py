from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

AuditActionType = Literal[
    "CREATE",
    "UPDATE",
    "DELETE",
    "MANUAL_STOCK_ADJUSTMENT",
    "PRICE_OVERRIDE",
    "CREDIT_LIMIT_OVERRIDE",
    "ROLE_CHANGE",
    "REFUND_PROCESSED",
    "MANAGER_OVERRIDE",
    "LOGIN_PIN",
    "LOGIN_PASSWORD",
    "EXPORT_DATA",
    "DRAWER_OPEN",
    "CASH_DROP",
    "ITEM_VOID",
    "EXPIRED_STOCK_SOLD",
]
ClientDevice = Literal["web", "desktop", "api", "system"]

# What a register may report. Catalog edits and exports only ever originate on the server.
DesktopActionType = Literal[
    "LOGIN_PIN",
    "MANAGER_OVERRIDE",
    "PRICE_OVERRIDE",
    "DRAWER_OPEN",
    "CASH_DROP",
    "ITEM_VOID",
    "REFUND_PROCESSED",
]
# Item voids carry the voided line in `details`; manager approvals carry the permission that was granted.
REASON_REQUIRED: frozenset[str] = frozenset({"PRICE_OVERRIDE", "DRAWER_OPEN", "CASH_DROP"})


class AuditLogRow(ApiModel):
    id: UUID
    occurred_at: datetime
    created_at: datetime
    user_id: UUID | None
    user_name: str | None
    user_role: str | None
    approver_id: UUID | None
    approver_name: str | None
    store_id: UUID | None
    store_code: str | None
    store_name: str | None
    action_type: AuditActionType
    action: str
    target_entity: str
    target_entity_id: UUID | None
    reason_notes: str | None
    client_device: ClientDevice
    ip_address: str | None
    changed_fields: list[str]
    sensitive: bool


class AuditLogDetail(AuditLogRow):
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    details: dict[str, Any]
    request_path: str | None
    client_event_id: UUID | None


class AuditLogPage(ApiModel):
    total: int
    limit: int
    offset: int
    rows: list[AuditLogRow]


class ActiveStaff(ApiModel):
    user_id: UUID
    user_name: str
    user_role: str | None
    store_code: str | None
    client_device: ClientDevice
    last_login_at: datetime


class AuditSummary(ApiModel):
    since: datetime
    total_actions: int
    sensitive_overrides: int
    active_staff_sessions: int
    session_window_minutes: int
    active_staff: list[ActiveStaff]
    by_action_type: dict[str, int]


class AuditFacetUser(ApiModel):
    id: UUID
    name: str
    role: str | None


class AuditFacets(ApiModel):
    users: list[AuditFacetUser]
    entities: list[str]
    action_types: list[str]


class DesktopAuditEvent(ApiModel):
    id: UUID
    occurred_at: datetime
    action_type: DesktopActionType
    action: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9_.]+$")
    user_id: UUID
    approver_id: UUID | None = None
    store_id: UUID
    target_entity: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z]+$")
    target_entity_id: UUID | None = None
    reason_notes: str | None = Field(default=None, max_length=1000)
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason_notes")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class DesktopAuditBatch(ApiModel):
    device_id: str = Field(min_length=1, max_length=64)
    events: list[DesktopAuditEvent] = Field(min_length=1, max_length=500)


class DesktopAuditRejection(ApiModel):
    id: UUID
    reason: str


class DesktopAuditResult(ApiModel):
    accepted: list[UUID]
    duplicates: list[UUID]
    rejected: list[DesktopAuditRejection]
