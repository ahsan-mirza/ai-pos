from datetime import datetime

from pydantic import Field

from app.schemas.payloads import ApiModel


class ChecklistItem(ApiModel):
    key: str
    label: str
    hint: str
    done: bool
    href: str


class Checklist(ApiModel):
    practice_mode: bool
    live_at: datetime | None
    store_name: str
    items: list[ChecklistItem]


class GoLiveRequest(ApiModel):
    # The store name typed back, so nobody wipes practice data by accident.
    confirm: str = Field(min_length=1, max_length=120)


class GoLiveResult(ApiModel):
    live_at: datetime
    sales_removed: int
    sample_products_removed: int
    sample_customers_removed: int
