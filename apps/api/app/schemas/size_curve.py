"""Sell-through of a size grid, and the broken size runs a transfer would fix."""

from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class SizeCell(ApiModel):
    product_id: UUID
    sku: str
    attributes: dict[str, str] = Field(default_factory=dict)
    size: str
    color: str | None
    received: int
    sold: int
    on_hand: int
    sell_through_bps: int
    sales_share_bps: int
    stock_share_bps: int


class BrokenRun(ApiModel):
    store_id: UUID
    store_name: str
    size: str
    color: str | None
    suggest_from_store_id: UUID | None
    suggest_from_name: str | None
    quantity: int


class SizeCurveReport(ApiModel):
    cells: list[SizeCell]
    broken_runs: list[BrokenRun]
