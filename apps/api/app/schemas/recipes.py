from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class RecipeLineIn(ApiModel):
    ingredient_id: UUID
    # In the ingredient's stock units: grams for one kept by weight, else pieces (or ml).
    quantity: int = Field(ge=1, le=10_000_000)


class RecipeIn(ApiModel):
    yield_quantity: int = Field(default=1, ge=1, le=1_000_000)
    notes: str | None = Field(default=None, max_length=500)
    lines: list[RecipeLineIn] = Field(min_length=1, max_length=60)


class RecipeLineOut(ApiModel):
    ingredient_id: UUID
    ingredient_name: str
    sku: str
    sold_by_weight: bool
    quantity: int
    # Per piece, or per kilogram for an ingredient kept by weight.
    unit_cost_cents: int | None
    cost_cents: int
    cost_estimated: bool


class RecipeOut(ApiModel):
    product_id: UUID
    product_name: str
    price_cents: int
    sold_by_weight: bool
    yield_quantity: int
    notes: str | None
    lines: list[RecipeLineOut]
    # The lines as written (one batch), and per dish unit sold.
    batch_cost_cents: int
    unit_cost_cents: int
    # Gross margin on the price before VAT, in basis points; null when the price is zero.
    margin_bps: int | None
    cost_estimated: bool
    updated_at: datetime | None


class ModifierIngredientIn(ApiModel):
    ingredient_id: UUID
    # Per dish unit sold; negative takes the ingredient out ("no cheese").
    quantity: int = Field(ge=-10_000_000, le=10_000_000)


class ModifierRecipeIn(ApiModel):
    lines: list[ModifierIngredientIn] = Field(default_factory=list, max_length=30)


class ModifierIngredientOut(ModifierIngredientIn):
    ingredient_name: str
    sold_by_weight: bool


class ModifierRecipeOut(ApiModel):
    option_id: UUID
    lines: list[ModifierIngredientOut]


class UsageVarianceRow(ApiModel):
    ingredient_id: UUID
    name: str
    sku: str
    sold_by_weight: bool
    # What the dishes sold should have used, what stock covered, and count / waste adjustments (signed).
    theoretical: int
    drawn: int
    adjustments: int
    # Actual usage = drawn - adjustments; variance = actual - theoretical (positive: more used than the recipes say).
    actual: int
    variance: int
    variance_cost_cents: int


class UsageVarianceReport(ApiModel):
    start: date
    end: date
    store_id: UUID | None
    rows: list[UsageVarianceRow]
