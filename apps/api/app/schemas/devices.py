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


class TerminalActivate(ApiModel):
    activation_key: str = Field(min_length=8, max_length=32)
    machine_name: str = Field(default="", max_length=120)


class TerminalActivation(ApiModel):
    """Everything the register stores (encrypted) after activation."""

    tenant_slug: str
    tenant_name: str
    tenant_domain: str
    tenant_url: str
    store_id: UUID
    store_code: str
    store_name: str
    register_id: UUID
    register_code: str
    register_name: str
    device_token: str


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
