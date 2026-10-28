import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.currency import SUPPORTED_CURRENCIES
from app.schemas.module_settings import ModuleSettings
from app.schemas.pos_policy import PosPolicy
from app.tenancy.countries import COUNTRY_CURRENCIES


class BusinessSettingsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    # Canonical tenant store code used at sign-in. Read-only; it is not a branch code.
    store_code: str = ""
    # ISO country recorded at signup. Null for stores created before it was stored.
    country: str | None = None
    # City or area of the business. Null until someone records it.
    location: str | None = None
    supported_currencies: list[str]
    updated_at: datetime
    updated_by_name: str | None
    vat_registered: bool = False
    trn: str | None = None
    legal_name: str | None = None
    legal_name_ar: str | None = None
    prices_include_vat: bool = False
    standard_rate_bps: int = 500
    primary_color: str | None = None
    business_profile: str = "electronics_wholesale"
    capabilities: list[str] = Field(default_factory=list)
    planned_capabilities: list[str] = Field(default_factory=list)
    # Bumps whenever business settings change. Registers compare it with the copy they stored.
    entitlement_revision: int = 1
    # Module keys granted by a verified add-on. Empty when none are paid for.
    purchased_capabilities: list[str] = Field(default_factory=list)
    # Paid modules remain usable offline until this moment. Null when nothing was purchased.
    entitlement_until: datetime | None = None
    # Subset of capabilities the Windows register implements. Admin-only modules are left out.
    register_capabilities: list[str] = Field(default_factory=list)
    onboarded: bool = True
    # A self-service store before Go live: sample data and practice sales, kept out of the books by Go live.
    practice_mode: bool = False
    # Live store whose e-invoice authority has no production credential yet. Practice stamps were not copied.
    tax_portal_pending: bool = False
    tax_authority: str = "fta"
    module_settings: ModuleSettings = Field(default_factory=ModuleSettings)
    pos_policy: PosPolicy = Field(default_factory=PosPolicy)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_profile: str
    # Explicit module selection; null keeps the profile preset.
    capabilities: list[str] | None = Field(default=None, max_length=64)
    complete_onboarding: bool = False


class AppearanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "#RRGGBB"; null restores the brand default.
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("primary_color")
    @classmethod
    def upper(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class TaxSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vat_registered: bool
    trn: str | None = Field(default=None, max_length=32)
    legal_name: str | None = Field(default=None, max_length=160)
    legal_name_ar: str | None = Field(default=None, max_length=160)
    prices_include_vat: bool
    standard_rate_bps: int = Field(ge=0, le=5000)
    # "fta" (UAE) or "zatca" (Saudi Arabia); decides invoice kinds, QR codes and e-invoicing.
    tax_authority: Literal["fta", "zatca"] = "fta"
    # When set, the tax authority follows this country. Omitted leaves the stored country alone.
    country: str | None = None
    location: str | None = Field(default=None, max_length=120)

    @field_validator("trn")
    @classmethod
    def _clean_trn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    @field_validator("country")
    @classmethod
    def _country(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        code = value.strip().upper()
        if code not in COUNTRY_CURRENCIES:
            raise ValueError("Choose a country from the list.")
        return code

    @field_validator("location")
    @classmethod
    def _location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def registered_needs_trn(self) -> "TaxSettingsUpdate":
        if self.vat_registered and not self.trn:
            raise ValueError("A tax-registered business needs its tax registration number.")
        if self.tax_authority == "zatca":
            saudi = self.trn is not None and len(self.trn) == 15 and self.trn.isdigit()
            if self.trn and not (saudi and self.trn.startswith("3") and self.trn.endswith("3")):
                raise ValueError("A Saudi VAT number is 15 digits that start and end with 3.")
        elif self.trn and self.trn.isdigit() and len(self.trn) != 15:
            raise ValueError("A UAE TRN is 15 digits. Leave it blank if the business is not VAT-registered.")
        elif self.trn and not re.fullmatch(r"[A-Z0-9][A-Z0-9 \-]{0,30}[A-Z0-9]", self.trn):
            raise ValueError("Enter the tax registration number, or leave it blank.")
        return self


class CurrencyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str

    @field_validator("currency")
    @classmethod
    def supported(cls, value: str) -> str:
        code = value.strip().upper()
        if code not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}.")
        return code
