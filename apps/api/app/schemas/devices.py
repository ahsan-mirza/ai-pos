from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class DeviceCreate(ApiModel):
    store_id: UUID
    code: str = Field(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9]+$")
    name: str = Field(min_length=1, max_length=80)


class DeviceOut(ApiModel):
    id: UUID
    store_id: UUID
    store_code: str
    code: str
    name: str
    key_hint: str
    invoice_prefix: str
    last_invoice_value: int
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    # active, offline, pending, or revoked. Pending means the till has not connected yet.
    activation_status: str
    machine_name: str | None = None


class ActivationPreflight(ApiModel):
    """Signing readiness for a new till. `public_key` is the Ed25519 verify key, never the seed."""

    ready: bool
    code: str | None = None
    message: str
    key_id: str = ""
    public_key: str = ""


class RegisterCapacity(ApiModel):
    """Package seats. `limit` and `available` are null when the plan does not cap registers."""

    used: int
    limit: int | None
    available: int | None


class DeviceKeyOut(ApiModel):
    """The plaintext key is returned exactly once; put it in the register's DEVICE_KEY."""

    device: DeviceOut
    key: str


class ActivationKeyOut(ApiModel):
    """Shown once in the portal; the cashier types the subdomain and this key on the new register."""

    device_id: UUID
    activation_key: str
    expires_at: datetime
    tenant_domain: str


class PosEnrollRequest(ApiModel):
    """A public demo code. Tenant and register identity are chosen by the server."""

    business_code: str = Field(min_length=1, max_length=32)


class PosEnrollResponse(ApiModel):
    enrollment_ticket: str
    expires_in: int
    business_code: str


class PosExchangeRequest(ApiModel):
    enrollment_ticket: str = Field(min_length=12, max_length=180)
    machine_name: str = Field(default="", max_length=120)


class LocalActivationContext(ApiModel):
    """Identity already stored on the register. Empty fields mean this machine has not been activated."""

    tenant_id: str = Field(default="", max_length=80)
    store_id: str = Field(default="", max_length=80)
    register_id: str = Field(default="", max_length=80)
    device_public_key: str = Field(default="", max_length=128)
    pending_sales: int = Field(default=0, ge=0, le=100000)
    pending_returns: int = Field(default=0, ge=0, le=100000)
    pending_cash_movements: int = Field(default=0, ge=0, le=100000)


class TerminalActivationPreflight(ApiModel):
    """Look up an activation. The key is not consumed."""

    store_code: str = Field(default="", max_length=80)
    activation_key: str = Field(default="", max_length=32)
    local: LocalActivationContext = LocalActivationContext()


class ActivationDecision(ApiModel):
    decision: str
    kind: str
    same_tenant: bool
    same_store: bool
    same_branch: bool
    device_registered: bool
    register_valid: bool
    within_plan: bool
    blocked: bool
    pending_sales: int
    pending_returns: int
    pending_cash_movements: int
    server_pending: int
    signing_ready: bool
    signing_code: str | None = None
    code: str
    message: str


class TerminalActivate(ApiModel):
    activation_key: str = Field(min_length=8, max_length=32)
    machine_name: str = Field(default="", max_length=120)
    # Standard base64 of the register's 32-byte Ed25519 public key. Empty keeps the O1 token-only exchange.
    device_public_key: str = Field(default="", max_length=128)


class SignedEntitlement(ApiModel):
    """The exact payload string is what was signed. Clients verify those bytes and do not re-encode them."""

    schema_version: int
    key_id: str
    payload: str
    signature: str


class EntitlementRequest(ApiModel):
    device_public_key: str = Field(min_length=1, max_length=128)


class TerminalActivation(ApiModel):
    """Everything the register stores (encrypted) after activation."""

    tenant_slug: str
    tenant_name: str
    tenant_domain: str
    tenant_url: str
    tenant_id: str = ""
    store_id: UUID
    store_code: str
    store_name: str
    register_id: UUID
    register_code: str
    register_name: str
    device_token: str
    entitlement: SignedEntitlement | None = None


class DeviceSeries(ApiModel):
    doc_type: str
    prefix: str
    last_value: int


class DeviceSelfOut(ApiModel):
    """What a register needs to number documents offline and resume after a reinstall."""

    id: UUID
    code: str
    name: str
    store_id: UUID
    store_code: str
    series: list[DeviceSeries]
