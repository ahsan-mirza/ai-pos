from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddonActionOut(ApiModel):
    permission: str
    label: str


class AddonModuleOut(ApiModel):
    key: str
    label: str
    entitlement: Literal["active", "expired", "suspended", "unavailable"]
    actions: list[AddonActionOut]


class AddonUserOut(ApiModel):
    user_id: UUID
    full_name: str
    username: str
    role_name: str
    is_active: bool
    store_id: UUID | None
    source: Literal["grant", "role", "revoked", "none", "inactive"]
    allowed: bool
    permissions: list[str]
    granted_by_id: UUID | None
    revoked_by_id: UUID | None
    revoked_at: datetime | None
    updated_at: datetime | None


class AssignmentChange(ApiModel):
    user_id: UUID
    module_key: str = Field(min_length=1, max_length=64)
    status: Literal["granted", "revoked"]
    permissions: list[str] = Field(default_factory=list, max_length=20)


class AssignmentBatch(ApiModel):
    changes: list[AssignmentChange] = Field(min_length=1, max_length=100)


class AssignmentOut(ApiModel):
    user_id: UUID
    module_key: str
    status: Literal["granted", "revoked"]
    permissions: list[str]


class AccessEventOut(ApiModel):
    id: UUID
    action: str
    user_name: str | None
    occurred_at: datetime
    module_key: str | None
    target_user_id: str | None
    status: str | None
    permissions: list[str]


class ConsoleAddonModuleOut(AddonModuleOut):
    assignments: int
    granted: int


class ConsoleAddonAccessOut(ApiModel):
    modules: list[ConsoleAddonModuleOut]
    history: list[AccessEventOut]
