from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

ChangeKind = Literal["BUSINESS_TYPE", "MODULE"]
ChangeStatus = Literal["PENDING", "RESOLVED", "REJECTED"]
OverrideState = Literal["on", "off"]


class TenantModulesOut(ApiModel):
    """What the Business profile page may show: the locked business type and the modules that fit it."""

    tenant_name: str
    business_profile: str
    profile_label: str
    # True once onboarding is done: the business type then only changes through IT support.
    locked: bool
    enabled: list[str]
    # Fit this business type and can be switched on by the tenant.
    available: list[str]
    planned: list[str]
    # Set by IT support; the tenant cannot change these.
    managed: dict[str, OverrideState] = Field(default_factory=dict)
    support_email: str


class ChangeRequestIn(ApiModel):
    kind: ChangeKind
    # A business profile id for BUSINESS_TYPE, a module id for MODULE.
    requested_value: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=3, max_length=1000)


class ChangeRequestOut(ApiModel):
    id: UUID
    tenant_id: UUID
    kind: ChangeKind
    requested_value: str
    current_value: str | None
    reason: str
    snapshot: dict
    status: ChangeStatus
    requested_by_email: str | None
    requested_by_name: str | None
    resolution_notes: str | None
    created_at: datetime
    resolved_at: datetime | None
