from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel


class ChecklistItem(ApiModel):
    key: str
    label: str
    hint: str
    done: bool
    href: str
    action: str
    optional: bool = False
    skipped: bool = False
    blocked: str | None = None
    secondary_href: str | None = None
    secondary_label: str | None = None
    # The optional action inside this step (inviting staff), not the step itself.
    skippable: bool = False


class Checklist(ApiModel):
    version: int
    practice_mode: bool
    live_at: datetime | None
    store_name: str
    # Units "Keep opening stock" would carry: real products, with practice sales put back.
    opening_stock_units: int
    # trial, pending_review, active, grace, restricted, or unbilled.
    subscription_state: str
    next_key: str | None
    items: list[ChecklistItem]


class OnboardingSkip(ApiModel):
    key: str = Field(min_length=1, max_length=40)


class GoLiveRequest(ApiModel):
    # The store name typed back, so nobody wipes practice data by accident.
    confirm: str = Field(min_length=1, max_length=120)
    mode: Literal["keep", "fresh"]
    # Required for keep. Fresh always resets stock.
    opening_stock: Literal["keep", "reset"] | None = None
    # The owner has seen that practice tax stamps will be destroyed.
    tax_acknowledged: bool = False


class GoLiveResult(ApiModel):
    live_at: datetime
    mode: Literal["keep", "fresh"]
    opening_stock: Literal["keep", "reset"]
    sales_removed: int
    sample_products_removed: int
    sample_customers_removed: int
