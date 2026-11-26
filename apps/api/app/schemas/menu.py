from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

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


class ModifierTemplateOut(ApiModel):
    key: str
    name: str
    min_select: int
    max_select: int
    options: list[str]
    present: bool


class ModifierTemplateIn(ApiModel):
    key: str = Field(min_length=1, max_length=40)


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


class PriceOptionIn(ApiModel):
    """One base price of a menu item. Omitted id creates a new option."""

    id: UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    price_cents: int = Field(ge=0, le=100_000_000)
    sku: str | None = Field(default=None, max_length=64)
    is_active: bool = True
    position: int = Field(default=0, ge=0, le=1000)

    @field_validator("name", mode="before")
    @classmethod
    def named(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Option name is required.")
        return cleaned


class PriceOptionsIn(ApiModel):
    options: list[PriceOptionIn] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def labels(self) -> Self:
        seen: set[str] = set()
        active = 0
        for option in self.options:
            label = option.name.strip().casefold()
            if not label:
                raise ValueError("Option name is required.")
            if label in seen:
                raise ValueError("Two priced options on one item cannot share a name.")
            seen.add(label)
            if option.is_active:
                active += 1
        if self.options and active == 0:
            raise ValueError("At least one priced option must stay active.")
        if active == 1:
            raise ValueError("Add at least two priced options, or leave the list empty to keep the single price.")
        return self


class PriceOptionOut(ApiModel):
    id: UUID
    product_id: UUID
    name: str
    price_cents: int
    sku: str | None = None
    is_active: bool
    position: int


class RegisterMenu(ApiModel):
    """Everything a register needs to offer modifiers, meals, and priced options offline."""

    groups: list[ModifierGroupOut]
    # product_id -> ordered group ids
    products: dict[str, list[UUID]]
    # combo product_id -> its slots
    combos: dict[str, list[ComboSlotOut]] = Field(default_factory=dict)
    # product_id -> active priced options, lowest display order first
    price_options: dict[str, list[PriceOptionOut]] = Field(default_factory=dict)
