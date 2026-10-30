import uuid

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel
from app.tenancy.countries import COUNTRY_CURRENCIES


class BranchTaxUpdate(ApiModel):
    country: str
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=80)
    registered: bool
    registration_number: str | None = Field(default=None, max_length=32)
    secondary_registration_number: str | None = Field(default=None, max_length=32)
    legal_name: str | None = Field(default=None, max_length=160)
    legal_name_local: str | None = Field(default=None, max_length=160)
    prices_include_vat: bool
    standard_rate_bps: int = Field(ge=0, le=5000)
    confirm_country_change: bool = False

    @field_validator("country")
    @classmethod
    def _country(cls, value: str) -> str:
        code = value.strip().upper()
        if code not in COUNTRY_CURRENCIES:
            raise ValueError("Choose a country from the list.")
        return code

    @field_validator(
        "registration_number",
        "secondary_registration_number",
        "legal_name",
        "legal_name_local",
        "city",
        "region",
    )
    @classmethod
    def _blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class TaxPreviewIn(ApiModel):
    amount_cents: int = Field(ge=0)
    category: str = "STANDARD"


class BranchTaxOut(ApiModel):
    store_id: uuid.UUID
    country: str | None
    city: str | None
    region: str | None
    own: bool
    registered: bool
    registration_number: str | None
    secondary_registration_number: str | None
    legal_name: str | None
    legal_name_local: str | None
    prices_include_vat: bool
    standard_rate_bps: int
    tax_authority: str
    version: int
    rate_confirmed: bool
    configuration_required: bool
    legal_entity_id: uuid.UUID | None
    country_tax: dict[str, object]
