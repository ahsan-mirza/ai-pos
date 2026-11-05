from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectionWrite(BaseModel):
    provider: str = Field(min_length=2, max_length=32)
    market: str = Field(default="", max_length=8)
    store_id: UUID


class ProviderOut(BaseModel):
    code: str
    name: str
    kind: str
    status: str
    countries: list[str]
    capabilities: list[str]
    detail: str


class ConnectionOut(BaseModel):
    id: UUID
    provider: str
    market: str
    store_id: UUID
    status: str
    channel_id: UUID | None
    webhook_path: str | None = None
    webhook_secret: str | None = None
    last_error: str | None
    last_checked_at: datetime | None


class OrderOut(BaseModel):
    id: UUID
    number: int
    store_id: UUID
    status: str
    external_ref: str | None
    channel_status: str | None
    channel_id: UUID | None


class HealthOut(BaseModel):
    addon: str
    profile: str
    connections: int
    active_connections: int
    open_orders: int
    available_providers: int
    awaiting_partner: int
