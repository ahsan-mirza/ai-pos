"""Pharmacy product payloads. Shared commercial fields stay on the product."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.pharmacy import DISPENSING_CLASSES, DOCUMENT_KINDS, OFFLINE_POLICIES, PRICE_CONTROLS, PRODUCT_KINDS

_GTIN = {8, 12, 13, 14}


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngredientWrite(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    strength_amount: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    strength_unit: str = Field(default="", max_length=16)
    is_active_ingredient: bool = True

    @field_validator("name", "strength_unit")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


class DocumentWrite(ApiModel):
    kind: str
    title: str = Field(min_length=1, max_length=160)
    reference: str = Field(default="", max_length=120)
    storage_key: str | None = Field(default=None, max_length=160)

    @field_validator("kind")
    @classmethod
    def known_kind(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in DOCUMENT_KINDS:
            raise ValueError("Document kind must be leaflet, registration, supplier, or other.")
        return cleaned

    @field_validator("title", "reference")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


class PharmacyWrite(ApiModel):
    product_kind: str
    dispensing_class: str
    generic_name: str = Field(default="", max_length=200)
    manufacturer: str = Field(default="", max_length=160)
    marketing_authorization_holder: str = Field(default="", max_length=160)
    country_of_origin: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=2000)
    gtin: str = Field(default="", max_length=14)
    manufacturer_product_ref: str = Field(default="", max_length=80)
    dosage_form: str = Field(default="", max_length=40)
    route: str = Field(default="", max_length=40)
    strength_amount: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    strength_unit: str = Field(default="", max_length=16)
    strength_display: str = Field(default="", max_length=40)
    concentration: str = Field(default="", max_length=80)
    pack_size_label: str = Field(default="", max_length=40)
    units_per_pack: int = Field(default=1, ge=1, le=1_000_000)
    base_unit_code: str = Field(default="PIECE", min_length=1, max_length=16)
    purchase_unit_code: str = Field(default="PIECE", max_length=16)
    selling_unit_code: str = Field(default="PIECE", max_length=16)
    dispense_unit_code: str = Field(default="PIECE", max_length=16)
    fractional_dispensing_allowed: bool = False
    pharmaceutical_class: str = Field(default="", max_length=80)
    registration_number: str | None = Field(default=None, max_length=80)
    registration_authority: str | None = Field(default=None, max_length=80)
    marketing_authorization_ref: str | None = Field(default=None, max_length=80)
    storage_condition: str = Field(default="", max_length=160)
    temp_min_c: Decimal | None = Field(default=None, ge=-80, le=80)
    temp_max_c: Decimal | None = Field(default=None, ge=-80, le=80)
    cold_chain: bool = False
    handling_instructions: str = Field(default="", max_length=2000)
    warnings_text: str = Field(default="", max_length=2000)
    price_control: str = "NONE"
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    discount_eligible: bool = True
    promotion_eligible: bool = True
    offline_policy: str = "BLOCK"
    substitution_group_id: UUID | None = None
    ingredients: list[IngredientWrite] = Field(default_factory=list, max_length=24)
    documents: list[DocumentWrite] = Field(default_factory=list, max_length=12)

    @field_validator("product_kind")
    @classmethod
    def known_kind(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in PRODUCT_KINDS:
            raise ValueError("Unknown product kind.")
        return cleaned

    @field_validator("dispensing_class")
    @classmethod
    def known_class(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in DISPENSING_CLASSES:
            raise ValueError("Choose a dispensing class. It is not taken from the category.")
        return cleaned

    @field_validator("price_control")
    @classmethod
    def known_price(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in PRICE_CONTROLS:
            raise ValueError("Unknown price-control type.")
        return cleaned

    @field_validator("offline_policy")
    @classmethod
    def known_offline(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in OFFLINE_POLICIES:
            raise ValueError("Offline policy must be ALLOW or BLOCK.")
        return cleaned

    @field_validator("gtin")
    @classmethod
    def digits(cls, value: str) -> str:
        cleaned = "".join(value.split())
        if cleaned and (not cleaned.isdigit() or len(cleaned) not in _GTIN):
            raise ValueError("GTIN must be 8, 12, 13, or 14 digits.")
        return cleaned

    @field_validator(
        "generic_name",
        "manufacturer",
        "marketing_authorization_holder",
        "country_of_origin",
        "dosage_form",
        "route",
        "strength_unit",
        "strength_display",
        "concentration",
        "pack_size_label",
        "base_unit_code",
        "purchase_unit_code",
        "selling_unit_code",
        "dispense_unit_code",
        "pharmaceutical_class",
        "storage_condition",
    )
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


class IngredientOut(ApiModel):
    id: UUID
    position: int
    name: str
    strength_amount: Decimal | None
    strength_unit: str
    is_active_ingredient: bool


class DocumentOut(ApiModel):
    id: UUID
    kind: str
    title: str
    reference: str
    storage_key: str | None


class PharmacyProductOut(ApiModel):
    product_id: UUID
    name: str
    sku: str
    barcode: str
    brand: str
    category: str
    sub_category: str
    price_cents: int
    tax_category: str
    is_active: bool
    updated_at: datetime
    product_kind: str
    dispensing_class: str
    classification_source: str
    generic_name: str
    manufacturer: str
    marketing_authorization_holder: str
    country_of_origin: str
    description: str
    gtin: str
    manufacturer_product_ref: str
    dosage_form: str
    route: str
    strength_amount: Decimal | None
    strength_unit: str
    strength_display: str
    concentration: str
    pack_size_label: str
    units_per_pack: int
    base_unit_code: str
    purchase_unit_code: str
    selling_unit_code: str
    dispense_unit_code: str
    fractional_dispensing_allowed: bool
    pharmaceutical_class: str
    registration_number: str | None
    registration_authority: str | None
    marketing_authorization_ref: str | None
    storage_condition: str
    temp_min_c: Decimal | None
    temp_max_c: Decimal | None
    cold_chain: bool
    handling_instructions: str
    warnings_text: str
    price_control: str
    min_price_cents: int | None
    max_price_cents: int | None
    discount_eligible: bool
    promotion_eligible: bool
    official_price_state: str
    sale_blocked: bool
    offline_policy: str
    substitution_group_id: UUID | None
    ingredients: list[IngredientOut]
    documents: list[DocumentOut]
    lot_on_product_master: bool = False
