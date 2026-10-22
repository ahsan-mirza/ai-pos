"""Fashion catalogue: product photos and the season / collection / gender / material / fit / care attributes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

Gender = Literal["women", "men", "kids", "unisex"]
GENDERS: tuple[Gender, ...] = ("women", "men", "kids", "unisex")
ATTRIBUTE_FIELDS = ("season", "collection", "gender", "material", "fit", "care")


def _text(value: object) -> object:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return value


class FashionAttributes(ApiModel):
    """Optional on every model and standalone product; a variant always takes its model's values."""

    # Upper-cased season code, e.g. SS26 or AW25.
    season: str | None = Field(default=None, max_length=16)
    collection: str | None = Field(default=None, max_length=80)
    gender: Gender | None = None
    material: str | None = Field(default=None, max_length=120)
    fit: str | None = Field(default=None, max_length=40)
    care: str | None = Field(default=None, max_length=255)

    @field_validator("season", mode="before")
    @classmethod
    def season_code(cls, value: object) -> object:
        cleaned = _text(value)
        return cleaned.upper() if isinstance(cleaned, str) else cleaned

    @field_validator("collection", "material", "fit", "care", mode="before")
    @classmethod
    def tidy(cls, value: object) -> object:
        return _text(value)

    @field_validator("gender", mode="before")
    @classmethod
    def gender_key(cls, value: object) -> object:
        cleaned = _text(value)
        return cleaned.lower() if isinstance(cleaned, str) else cleaned


class FashionAttributesOut(ApiModel):
    season: str | None = None
    collection: str | None = None
    gender: Gender | None = None
    material: str | None = None
    fit: str | None = None
    care: str | None = None


class CatalogAttributesOut(ApiModel):
    """Values in use, for filter and form pickers."""

    seasons: list[str]
    collections: list[str]
    genders: list[Gender]
    materials: list[str]
    fits: list[str]


class ProductImageOut(ApiModel):
    id: UUID
    product_id: UUID | None
    product_model_id: UUID | None
    attribute_key: str | None
    attribute_value: str | None
    url: str
    thumb_url: str
    width: int
    height: int
    position: int
    is_primary: bool
    created_at: datetime


class ProductImageUpdate(ApiModel):
    is_primary: bool | None = None
    position: int | None = Field(default=None, ge=0, le=100)
    attribute_key: str | None = Field(default=None, max_length=32)
    attribute_value: str | None = Field(default=None, max_length=64)
