from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.payloads import ApiModel

Channel = Literal["whatsapp", "sms", "email"]
OutboundStatus = Literal["QUEUED", "SENT", "FAILED", "SKIPPED"]


class MessagingSettingsOut(ApiModel):
    providers: dict[str, str]
    available: dict[str, list[str]]
    events: dict[str, bool]


class MessagingSettingsWrite(ApiModel):
    providers: dict[str, str] = Field(default_factory=dict)
    events: dict[str, bool] = Field(default_factory=dict)


class TemplateOut(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    key: str
    name: str
    subject: str
    body: str
    is_active: bool


class TemplateWrite(ApiModel):
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=3, max_length=1000)
    is_active: bool = True


class OutboundOut(ApiModel):
    id: UUID
    channel: str
    to_address: str
    customer_name: str | None
    template_key: str | None
    subject: str
    body: str
    status: OutboundStatus
    provider: str | None
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class TestMessage(ApiModel):
    channel: Channel
    to: str = Field(min_length=3, max_length=254)


class JobOut(ApiModel):
    name: str
    description: str
    schedule: str
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_status: str | None
    last_result: str | None
    run_count: int
    running: bool
