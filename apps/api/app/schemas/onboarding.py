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


class Checklist(ApiModel):
    practice_mode: bool
    live_at: datetime | None
    store_name: str
    # Units "Keep opening stock" would carry: real products, with practice sales put back.
    opening_stock_units: int
    items: list[ChecklistItem]


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
