"""Pharmacy product extension. Lot numbers and expiry stay off this master."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, utcnow

PRODUCT_KINDS = (
    "MEDICINE",
    "DEVICE",
    "SUPPLY",
    "SUPPLEMENT",
    "PERSONAL_CARE",
    "COSMETIC",
    "NUTRITION",
    "VETERINARY",
    "ACCESSORY",
)
DISPENSING_CLASSES = (
    "OTC",
    "PRESCRIPTION",
    "CONTROLLED",
    "SEMI_CONTROLLED",
    "RESTRICTED",
    "SPECIAL_HANDLING",
)
PRICE_CONTROLS = ("NONE", "MINIMUM", "MAXIMUM", "FIXED")
OFFLINE_POLICIES = ("ALLOW", "BLOCK")
CLASSIFICATION_SOURCES = ("TENANT_DECLARED", "AUTHORITY_CONFIRMED")
DOCUMENT_KINDS = ("leaflet", "registration", "supplier", "other")


class SubstitutionGroup(TenantScoped, TimestampMixin, Base):
    """Products that share a generic, strength, form, and route. The register never swaps them."""

    __tablename__ = "substitution_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(120))


class ProductDocument(TenantScoped, TimestampMixin, Base):
    __tablename__ = "product_documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('leaflet', 'registration', 'supplier', 'other')",
            name="kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(160))
    reference: Mapped[str] = mapped_column(String(120), default="")
    storage_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PharmacyProductDetails(TenantScoped, TimestampMixin, Base):
    __tablename__ = "pharmacy_product_details"
    __table_args__ = (
        CheckConstraint(
            "product_kind IN ('MEDICINE', 'DEVICE', 'SUPPLY', 'SUPPLEMENT', 'PERSONAL_CARE', "
            "'COSMETIC', 'NUTRITION', 'VETERINARY', 'ACCESSORY')",
            name="kind",
        ),
        CheckConstraint(
            "dispensing_class IN ('OTC', 'PRESCRIPTION', 'CONTROLLED', 'SEMI_CONTROLLED', "
            "'RESTRICTED', 'SPECIAL_HANDLING')",
            name="class",
        ),
        CheckConstraint(
            "price_control IN ('NONE', 'MINIMUM', 'MAXIMUM', 'FIXED')",
            name="price_control",
        ),
        CheckConstraint(
            "offline_policy IN ('ALLOW', 'BLOCK')",
            name="offline",
        ),
        CheckConstraint(
            "classification_source IN ('TENANT_DECLARED', 'AUTHORITY_CONFIRMED')",
            name="source",
        ),
        CheckConstraint("units_per_pack >= 1", name="pack"),
        CheckConstraint(
            "min_price_cents IS NULL OR min_price_cents >= 0",
            name="min_price",
        ),
        CheckConstraint(
            "max_price_cents IS NULL OR max_price_cents >= 0",
            name="max_price",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    product_kind: Mapped[str] = mapped_column(String(20))
    generic_name: Mapped[str] = mapped_column(String(200), default="")
    manufacturer: Mapped[str] = mapped_column(String(160), default="")
    marketing_authorization_holder: Mapped[str] = mapped_column(String(160), default="")
    country_of_origin: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    gtin: Mapped[str] = mapped_column(String(14), default="")
    manufacturer_product_ref: Mapped[str] = mapped_column(String(80), default="")
    dosage_form: Mapped[str] = mapped_column(String(40), default="")
    route: Mapped[str] = mapped_column(String(40), default="")
    strength_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    strength_unit: Mapped[str] = mapped_column(String(16), default="")
    strength_display: Mapped[str] = mapped_column(String(40), default="")
    concentration: Mapped[str] = mapped_column(String(80), default="")
    pack_size_label: Mapped[str] = mapped_column(String(40), default="")
    units_per_pack: Mapped[int] = mapped_column(Integer, default=1)
    base_unit_code: Mapped[str] = mapped_column(String(16), default="PIECE")
    purchase_unit_code: Mapped[str] = mapped_column(String(16), default="PIECE")
    selling_unit_code: Mapped[str] = mapped_column(String(16), default="PIECE")
    dispense_unit_code: Mapped[str] = mapped_column(String(16), default="PIECE")
    fractional_dispensing_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    dispensing_class: Mapped[str] = mapped_column(String(20))
    classification_source: Mapped[str] = mapped_column(String(24), default="TENANT_DECLARED")
    pharmaceutical_class: Mapped[str] = mapped_column(String(80), default="")
    registration_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_authority: Mapped[str | None] = mapped_column(String(80), nullable=True)
    marketing_authorization_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    storage_condition: Mapped[str] = mapped_column(String(160), default="")
    temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cold_chain: Mapped[bool] = mapped_column(Boolean, default=False)
    handling_instructions: Mapped[str] = mapped_column(Text, default="")
    warnings_text: Mapped[str] = mapped_column(Text, default="")
    leaflet_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_documents.id"), nullable=True
    )
    price_control: Mapped[str] = mapped_column(String(16), default="NONE")
    min_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    promotion_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    offline_policy: Mapped[str] = mapped_column(String(8), default="BLOCK")
    substitution_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("substitution_groups.id"), nullable=True
    )
    ingredients: Mapped[list[ProductIngredient]] = relationship(
        "ProductIngredient",
        cascade="all, delete-orphan",
        order_by="ProductIngredient.position",
        lazy="selectin",
    )


class ProductIngredient(TenantScoped, Base):
    __tablename__ = "product_ingredients"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint(
            "strength_amount IS NULL OR strength_amount >= 0",
            name="strength",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pharmacy_product_details.product_id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(160))
    strength_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    strength_unit: Mapped[str] = mapped_column(String(16), default="")
    is_active_ingredient: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
