from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ChannelName = Literal["whatsapp", "sms", "email"]


class ChannelOut(BaseModel):
    channel: ChannelName
    enabled: bool
    provider: str
    providers: list[str]
    public_config: dict[str, str]
    secret_set: bool
    secret_hint: str | None
    status: str
    last_error: str | None
    last_checked_at: datetime | None = None


class ChannelWrite(BaseModel):
    channel: ChannelName
    enabled: bool
    provider: str = Field(min_length=1, max_length=24)
    public_config: dict[str, str] = Field(default_factory=dict)
    secret: str | None = Field(default=None, max_length=4000)


class Audience(BaseModel):
    inactive_days: int = Field(default=0, ge=0, le=3650)
    min_loyalty_points: int = Field(default=0, ge=0)
    min_spend_cents: int = Field(default=0, ge=0)
    customer_type: str | None = None


class ChannelContent(BaseModel):
    body: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=200)


class CampaignWrite(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    objective: str = Field(default="promotion", max_length=40)
    channels: list[ChannelName] = Field(min_length=1, max_length=3)
    audience: Audience = Field(default_factory=Audience)
    content: dict[str, ChannelContent]
    store_id: UUID | None = None
    scheduled_at: datetime | None = None


class CampaignOut(BaseModel):
    id: UUID
    name: str
    description: str
    objective: str
    status: str
    channels: list[str]
    eligible_count: int
    suppressed_count: int
    queued_count: int
    scheduled_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreviewOut(BaseModel):
    recipients: int
    eligible: int
    suppressed: int
    estimated_cents: int
    unknown_variables: list[str]


class FailureOut(BaseModel):
    id: UUID
    channel: str
    to_address: str
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OverviewOut(BaseModel):
    campaigns: int
    active: int
    sent: int
    failed: int
    delivery_rate: float | None
    by_channel: dict[str, int]
    usage_cents: int
    transactional_cents: int = 0
    prices: dict[str, int]
    recent: list[CampaignOut]
    failures: list[FailureOut]


class PricesWrite(BaseModel):
    whatsapp: int = Field(default=0, ge=0)
    sms: int = Field(default=0, ge=0)
    email: int = Field(default=0, ge=0)
