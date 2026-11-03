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
    # None keeps the filter audience. An empty list means the owner selected nobody.
    customer_ids: list[UUID] | None = Field(default=None, max_length=1000)


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
    pending_count: int = 0
    processing_count: int = 0
    accepted_count: int = 0
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    credits_reserved: int = 0
    credits_consumed: int = 0
    connection_phone: str | None = None

    model_config = {"from_attributes": True}


class PreviewOut(BaseModel):
    recipients: int
    eligible: int
    suppressed: int
    estimated_cents: int
    estimated_credits: int = 0
    available_credits: int | None = None
    unknown_variables: list[str]
    sample: str = ""


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
    delivered: int = 0
    read: int = 0
    delivery_rate: float | None
    by_channel: dict[str, int]
    usage_cents: int
    transactional_cents: int = 0
    prices: dict[str, int]
    credits_available: int | None = None
    credits_reserved: int | None = None
    connection_status: str | None = None
    recent: list[CampaignOut]
    failures: list[FailureOut]


class PricesWrite(BaseModel):
    whatsapp: int = Field(default=0, ge=0)
    sms: int = Field(default=0, ge=0)
    email: int = Field(default=0, ge=0)


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ConnectionOut(BaseModel):
    id: UUID
    name: str
    instance_name: str
    phone_number: str | None
    status: str
    last_error: str | None
    qr_base64: str | None = None
    webhook_status: str = "pending"
    webhook_registered_at: datetime | None = None
    last_webhook_at: datetime | None = None

    model_config = {"from_attributes": True}


class TemplateWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: ChannelName = "whatsapp"
    body: str = Field(min_length=2, max_length=4000)
    media_kind: str | None = Field(default=None, max_length=24)


class TemplateOut(BaseModel):
    id: UUID
    name: str
    channel: str
    body: str
    media_kind: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecipientOut(BaseModel):
    id: UUID
    campaign_id: UUID
    customer_id: UUID | None
    phone: str
    status: str
    provider_message_id: str | None
    failure_reason: str | None
    submitted_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None

    model_config = {"from_attributes": True}


class CreditOut(BaseModel):
    balance: int
    reserved: int
    available: int


class CreditTransactionOut(BaseModel):
    id: UUID
    kind: str
    units: int
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditAllocate(BaseModel):
    units: int = Field(ge=1, le=1_000_000)
    note: str = Field(default="", max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=80)
