"""Markdown events: a percent or a fixed price, a window, and the products they cover."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel


class MarkdownScope(ApiModel):
    model_ids: list[UUID] = Field(default_factory=list, max_length=200)
    category_ids: list[UUID] = Field(default_factory=list, max_length=200)
    product_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    season: str | None = Field(default=None, max_length=16)
    collection: str | None = Field(default=None, max_length=80)

    def empty(self) -> bool:
        return not (self.model_ids or self.category_ids or self.product_ids or self.season or self.collection)


class MarkdownCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    scope: MarkdownScope
    percent_bps: int | None = Field(default=None, ge=1, le=9000)
    price_cents: int | None = Field(default=None, ge=0)
    starts_at: datetime
    ends_at: datetime
    final_sale: bool = False

    @model_validator(mode="after")
    def one_rule(self) -> "MarkdownCreate":
        if (self.percent_bps is None) == (self.price_cents is None):
            raise ValueError("Set either a percent off or a fixed price.")
        if self.ends_at <= self.starts_at:
            raise ValueError("The markdown must end after it starts.")
        if self.scope.empty():
            raise ValueError("Choose products, a model, a category, a season or a collection.")
        return self


class MarkdownSkip(ApiModel):
    sku: str
    reason: str


class MarkdownPreview(ApiModel):
    products: int
    units: int
    retail_cents: int
    marked_cents: int
    skipped: list[MarkdownSkip]


class MarkdownEventOut(ApiModel):
    id: UUID
    name: str
    scope: MarkdownScope
    percent_bps: int | None
    price_cents: int | None
    starts_at: datetime
    ends_at: datetime
    final_sale: bool
    status: str
    applied_count: int
    skipped_count: int
    created_at: datetime
