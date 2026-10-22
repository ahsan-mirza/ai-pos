from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, TaxCategory


class ModifierOptionIn(ApiModel):
    # Existing option to update; omitted creates a new one.
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    price_delta_cents: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    is_default: bool = False
    is_active: bool = True


class ModifierGroupIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    min_select: int = Field(default=0, ge=0, le=20)
    max_select: int = Field(default=1, ge=1, le=20)
    position: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True
    options: list[ModifierOptionIn] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def counts(self) -> Self:
        if self.max_select < self.min_select:
            raise ValueError("A group cannot require more choices than it allows.")
        active = [option for option in self.options if option.is_active]
        if len(active) < self.min_select:
            raise ValueError("A required group needs at least that many active options.")
        if sum(1 for option in active if option.is_default) > self.max_select:
            raise ValueError("More default options than the group allows.")
        return self


class ModifierOptionOut(ApiModel):
    id: UUID
    name: str
    price_delta_cents: int
    is_default: bool
    is_active: bool
    position: int


class ModifierGroupOut(ApiModel):
    id: UUID
    name: str
    min_select: int
    max_select: int
    position: int
    is_active: bool
    options: list[ModifierOptionOut]
    product_ids: list[UUID] = Field(default_factory=list)


class ProductGroupsIn(ApiModel):
    group_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ComboOptionIn(ApiModel):
    product_id: UUID
    surcharge_cents: int = Field(default=0, ge=0, le=1_000_000)
    is_default: bool = False


class ComboSlotIn(ApiModel):
    name: str = Field(min_length=1, max_length=60)
    min_select: int = Field(default=1, ge=0, le=10)
    max_select: int = Field(default=1, ge=1, le=10)
    options: list[ComboOptionIn] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def counts(self) -> Self:
        if self.max_select < self.min_select:
            raise ValueError(f"{self.name} cannot require more choices than it allows.")
        if len(self.options) < self.min_select:
            raise ValueError(f"{self.name} needs at least {self.min_select} options.")
        if sum(1 for option in self.options if option.is_default) > self.max_select:
            raise ValueError(f"{self.name} has more default options than it allows.")
        if len({option.product_id for option in self.options}) != len(self.options):
            raise ValueError(f"{self.name} lists the same item twice.")
        return self


class ComboIn(ApiModel):
    """A meal: a menu item sold at one price whose parts the cashier picks slot by slot."""

    name: str = Field(min_length=1, max_length=200)
    # A category id, or a category name (created when new); the meal routes nowhere itself, its components do.
    category_id: UUID | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    price_cents: int = Field(ge=0, le=100_000_000)
    tax_category: TaxCategory = "STANDARD"
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    slots: list[ComboSlotIn] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def has_category(self) -> Self:
        if self.category_id is None and self.category is None:
            raise ValueError("Choose a category for the meal.")
        return self


class ComboOptionOut(ApiModel):
    product_id: UUID
    name: str
    category: str
    price_cents: int
    surcharge_cents: int
    is_default: bool
    position: int


class ComboSlotOut(ApiModel):
    id: UUID
    name: str
    min_select: int
    max_select: int
    position: int
    options: list[ComboOptionOut]


class ComboOut(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    category_id: UUID | None
    price_cents: int
    tax_category: str
    slots: list[ComboSlotOut]


class RegisterMenu(ApiModel):
    """Everything a register needs to offer modifiers and meals offline."""

    groups: list[ModifierGroupOut]
    # product_id -> ordered group ids
    products: dict[str, list[UUID]]
    # combo product_id -> its slots
    combos: dict[str, list[ComboSlotOut]] = Field(default_factory=dict)
