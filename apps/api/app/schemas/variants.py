from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.inventory import variant_attributes
from app.schemas.payloads import ApiModel, TaxCategory

MAX_MATRIX_CELLS = 400


class MatrixAxis(ApiModel):
    key: str = Field(min_length=1, max_length=24)
    values: list[str] = Field(min_length=1, max_length=40)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        [key] = variant_attributes({value: "x"}).keys()
        return key

    @field_validator("values")
    @classmethod
    def clean_values(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            text = " ".join(raw.split())
            if len(text) > 60:
                raise ValueError("Each value is at most 60 characters.")
            if text and text.lower() not in {value.lower() for value in cleaned}:
                cleaned.append(text)
        if not cleaned:
            raise ValueError("Give each axis at least one value.")
        return cleaned


class MatrixVariantDraft(ApiModel):
    """One size/colour combination to create or update. Omitted combinations are not created."""

    attributes: dict[str, str]
    product_id: UUID | None = None
    sku: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    price_cents: int | None = Field(default=None, ge=0)
    cost_cents: int | None = Field(default=None, ge=0)
    opening_quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    min_reorder_level: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None

    @field_validator("attributes")
    @classmethod
    def normalize_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned = variant_attributes(value)
        if not cleaned:
            raise ValueError("Each variant needs its attributes.")
        return cleaned

    @field_validator("sku", "barcode")
    @classmethod
    def clean_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class MatrixWrite(ApiModel):
    """Size x colour (and optionally a third axis) for one model.

    Without `variants`, every combination is created and existing ones are left as they are.
    With `variants`, only that list is created or updated, so excluded combinations stay absent.
    """

    axes: list[MatrixAxis] = Field(min_length=1, max_length=3)
    price_cents: int = Field(ge=0)
    # Price for combinations that include a value, e.g. {"XXL": 9900}; the highest matching price wins.
    price_by_value: dict[str, int] = Field(default_factory=dict)
    sku_prefix: str | None = Field(default=None, max_length=24, pattern=r"^[A-Za-z0-9-]+$")
    tax_category: TaxCategory = "STANDARD"
    variants: list[MatrixVariantDraft] | None = Field(default=None, max_length=MAX_MATRIX_CELLS)
    opening_store_id: UUID | None = None
    specifications: dict[str, str] = Field(default_factory=dict)

    @field_validator("specifications")
    @classmethod
    def clean_specifications(cls, value: dict[str, str]) -> dict[str, str]:
        from app.schemas.inventory import specifications

        return specifications(value)

    @model_validator(mode="after")
    def bounded(self) -> "MatrixWrite":
        keys = [axis.key for axis in self.axes]
        if len(set(keys)) != len(keys):
            raise ValueError("Each axis needs its own attribute.")
        if any(price < 0 for price in self.price_by_value.values()):
            raise ValueError("Prices cannot be negative.")
        if self.variants is not None:
            if not self.variants:
                raise ValueError("Include at least one combination.")
            if len(self.variants) > MAX_MATRIX_CELLS:
                raise ValueError(
                    f"A matrix can have at most {MAX_MATRIX_CELLS} combinations; this one has {len(self.variants)}."
                )
            expected = set(keys)
            seen: set[tuple[tuple[str, str], ...]] = set()
            for draft in self.variants:
                if set(draft.attributes) != expected:
                    raise ValueError("Each combination must use the same attributes as the axes.")
                identity = tuple(sorted((key, value.lower()) for key, value in draft.attributes.items()))
                if identity in seen:
                    raise ValueError("That size and color combination is listed twice.")
                seen.add(identity)
            needs_store = any(
                (draft.opening_quantity or 0) > 0
                or (draft.min_reorder_level or 0) > 0
                or draft.cost_cents is not None
                for draft in self.variants
            )
            if needs_store and self.opening_store_id is None:
                raise ValueError("Choose the store that holds the opening stock.")
            return self
        cells = 1
        for axis in self.axes:
            cells *= len(axis.values)
        if cells > MAX_MATRIX_CELLS:
            raise ValueError(f"A matrix can have at most {MAX_MATRIX_CELLS} combinations; this one has {cells}.")
        return self


class MatrixCell(ApiModel):
    attributes: dict[str, str]
    product_id: UUID
    sku: str
    barcode: str
    name: str
    price_cents: int
    price_source: str = "override"
    is_active: bool = True
    cost_cents: int | None = None
    on_hand: int
    sold_90d: int
    by_store: dict[str, int]


class MatrixOut(ApiModel):
    model_id: UUID
    model_name: str
    axes: list[MatrixAxis]
    cells: list[MatrixCell]
    on_hand: int
    sold_90d: int
    created: int = 0
    skipped: int = 0


class MatrixPreview(ApiModel):
    possible: int
    existing: int
    creating: int
    inactive: int
    duplicates: int
    over_limit: bool


class MatrixBulk(ApiModel):
    product_ids: list[UUID] = Field(min_length=1, max_length=MAX_MATRIX_CELLS)
    price_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    store_id: UUID | None = None
    min_reorder_level: int | None = Field(default=None, ge=0, le=1_000_000)
    assign_missing_barcodes: bool = False
    # Leave a variant's own price or reorder level alone. Only fill ones still on the model default or zero.
    only_unset: bool = False

    @model_validator(mode="after")
    def has_action(self) -> "MatrixBulk":
        if (
            self.price_cents is None
            and self.is_active is None
            and self.min_reorder_level is None
            and not self.assign_missing_barcodes
        ):
            raise ValueError("Choose a price, a status, a reorder level, or barcode assignment.")
        if self.min_reorder_level is not None and self.store_id is None:
            raise ValueError("Choose a store for the reorder level.")
        return self


class MatrixBulkResult(ApiModel):
    updated: int
    skipped: list[UUID]
