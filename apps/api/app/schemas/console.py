from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.governance import ChangeRequestOut, OverrideState
from app.schemas.payloads import ApiModel

OperatorRole = Literal["SUPPORT", "ADMIN"]
TenantStatus = Literal["active", "suspended"]


class ConsoleLogin(ApiModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=8)


class OperatorOut(ApiModel):
    id: UUID
    email: str
    full_name: str
    role: OperatorRole
    is_active: bool
    last_login_at: datetime | None


class ConsoleSession(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    operator: OperatorOut


class TenantStatsOut(ApiModel):
    onboarded: bool | None = None
    business_profile: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)
    stores: int = 0
    registers: int = 0
    users: int = 0
    customers: int = 0
    products: int = 0
    sales_30d_count: int = 0
    sales_30d_cents: int = 0
    currency: str | None = None
    last_sale_at: datetime | None = None
    db_size_bytes: int | None = None
    collected_at: datetime | None = None


class TenantRow(ApiModel):
    id: UUID
    slug: str
    name: str
    domain: str
    status: TenantStatus
    business_profile: str
    profile_label: str
    plan: str
    owner_email: str | None
    created_at: datetime
    stats: TenantStatsOut
    pending_requests: int = 0


class ModuleState(ApiModel):
    key: str
    label: str
    available: bool
    # On for the tenant right now (after overrides).
    enabled: bool
    # Part of the business type's preset, or of the tenant's own selection.
    selected: bool
    fits_type: bool
    override: OverrideState | None = None


class OperatorAuditOut(ApiModel):
    id: UUID
    operator_email: str | None
    action: str
    before: dict | None
    after: dict | None
    reason: str | None
    created_at: datetime


class TenantDetail(ApiModel):
    tenant: TenantRow
    modules: list[ModuleState]
    change_requests: list[ChangeRequestOut]
    audit: list[OperatorAuditOut]
    # Set when the store's database could not be read (modules then come from the last snapshot).
    unreachable: str | None = None


class ModuleOverridesIn(ApiModel):
    # module -> "on" | "off" to force it, null to hand it back to the business type / the tenant.
    overrides: dict[str, OverrideState | None] = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=3, max_length=500)


class TenantUpdate(ApiModel):
    status: TenantStatus | None = None
    plan: str | None = Field(default=None, min_length=1, max_length=32)
    owner_email: str | None = Field(default=None, max_length=254)
    reason: str = Field(min_length=3, max_length=500)


class MigrationCheck(ApiModel):
    code: str
    message: str
    count: int


class MigrationPreflight(ApiModel):
    tenant_id: UUID
    current_profile: str
    target_profile: str
    gained: list[str]
    lost: list[str]
    blockers: list[MigrationCheck]
    warnings: list[MigrationCheck]
    # Send back with the migration; it expires and is tied to this exact diff.
    preflight_token: str
    expires_at: datetime


class MigrationIn(ApiModel):
    target_profile: str = Field(min_length=1, max_length=32)
    preflight_token: str = Field(min_length=10, max_length=512)
    # Typed by the operator: the tenant's subdomain, so the wrong store is never migrated.
    confirm_slug: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=3, max_length=500)
    change_request_id: UUID | None = None


class PreflightIn(ApiModel):
    target_profile: str = Field(min_length=1, max_length=32)


class ResolveIn(ApiModel):
    notes: str = Field(min_length=3, max_length=1000)


class ConsoleChangeRequest(ChangeRequestOut):
    tenant_slug: str
    tenant_name: str


class CustomerRow(ApiModel):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    customer_type: str
    balance_cents: int
    created_at: datetime | None
