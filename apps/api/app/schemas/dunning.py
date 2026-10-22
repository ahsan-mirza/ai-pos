from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class StatementSend(ApiModel):
    """No ids: every active wholesale account with a balance."""

    customer_ids: list[UUID] | None = Field(default=None, max_length=500)


class DunningResult(ApiModel):
    queued: int
    skipped: int
