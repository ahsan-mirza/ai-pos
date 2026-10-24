"""Cards the kitchen brief shows a restaurant or cafe manager."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

KitchenKind = Literal[
    "order",
    "use_first",
    "push_today",
    "write_off",
    "cannot_make",
    "prep",
    "transfer",
    "waste",
    "margin",
    "overstock",
]
KitchenSeverity = Literal["high", "medium", "low"]
KitchenActionName = Literal["draft_purchase", "draft_transfer", "write_off"]


class KitchenCard(ApiModel):
    id: str
    kind: KitchenKind
    severity: KitchenSeverity
    title: str
    body: str
    product_id: UUID | None = None
    batch_item_id: UUID | None = None
    store_id: UUID | None = None
    source_store_id: UUID | None = None
    quantity: int | None = None
    supplier_name: str | None = None
    action: KitchenActionName | None = None
    href: str | None = None


class KitchenBrief(ApiModel):
    generated_at: datetime
    store_id: UUID | None
    cards: list[KitchenCard]


class KitchenActionIn(ApiModel):
    action: KitchenActionName
    product_id: UUID | None = None
    store_id: UUID | None = None
    source_store_id: UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=100_000)
    batch_item_id: UUID | None = None
    supplier_name: str | None = Field(default=None, max_length=120)


class KitchenActionOut(ApiModel):
    action: KitchenActionName
    reference: str
    href: str
