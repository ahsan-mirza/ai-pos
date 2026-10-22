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


class MatrixWrite(ApiModel):
    """Size x colour (and optionally a third axis) for one model. Existing combinations are left as they are."""

    axes: list[MatrixAxis] = Field(min_length=1, max_length=3)
    price_cents: int = Field(ge=0)
    # Price for combinations that include a value, e.g. {"XXL": 9900}; the highest matching price wins.
    price_by_value: dict[str, int] = Field(default_factory=dict)
    sku_prefix: str | None = Field(default=None, max_length=24, pattern=r"^[A-Za-z0-9-]+$")
    tax_category: TaxCategory = "STANDARD"

    @model_validator(mode="after")
    def bounded(self) -> "MatrixWrite":
        keys = [axis.key for axis in self.axes]
        if len(set(keys)) != len(keys):
            raise ValueError("Each axis needs its own attribute.")
        cells = 1
        for axis in self.axes:
            cells *= len(axis.values)
        if cells > MAX_MATRIX_CELLS:
            raise ValueError(f"A matrix can have at most {MAX_MATRIX_CELLS} combinations; this one has {cells}.")
        if any(price < 0 for price in self.price_by_value.values()):
            raise ValueError("Prices cannot be negative.")
        return self


class MatrixCell(ApiModel):
    attributes: dict[str, str]
    product_id: UUID
    sku: str
    barcode: str
    name: str
    price_cents: int
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
