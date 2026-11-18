"""Contracts for the public hardware catalogue. Prices are integer fils. extra is forbidden."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

StockStatus = Literal["in_stock", "limited", "out_of_stock", "on_request"]
PackageType = Literal["hardware_only", "hardware_software", "all_in_one", "custom"]
EnquiryStatus = Literal["new", "contacted", "quoted", "converted", "closed"]
EnquiryType = Literal["product", "package", "custom", "installation"]
BusinessType = Literal["restaurant", "cafe", "supermarket", "electronics", "fashion", "wholesale", "other"]


class SpecIn(ApiModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=240)


class ReasonIn(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class CategoryIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    slug: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=2000)
    image_alt: str = Field(default="", max_length=160)
    display_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True
    reason: str = Field(min_length=3, max_length=500)


class CategoryOut(ApiModel):
    id: UUID
    name: str
    slug: str
    description: str
    image_url: str | None
    thumb_url: str | None
    image_alt: str
    display_order: int
    is_active: bool
    updated_at: datetime


class ImageOut(ApiModel):
    id: UUID
    url: str
    thumb_url: str
    alt: str
    position: int
    is_primary: bool
    width: int
    height: int


class ImageOrderIn(ApiModel):
    ids: list[UUID] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=3, max_length=500)


class ProductIn(ApiModel):
    category_id: UUID
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(default="", max_length=80)
    sku: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,31}$")
    short_description: str = Field(default="", max_length=300)
    full_description: str = Field(default="", max_length=8000)
    brand: str = Field(default="", max_length=80)
    model_number: str = Field(default="", max_length=80)
    manufacturer: str = Field(default="", max_length=80)
    specifications: list[SpecIn] = Field(default_factory=list, max_length=40)
    purchase_price_fils: int | None = Field(default=None, ge=0, le=100_000_000)
    display_price_fils: int | None = Field(default=None, ge=0, le=100_000_000)
    currency: str = Field(default="AED", min_length=3, max_length=3)
    warranty_months: int = Field(default=0, ge=0, le=120)
    stock_status: StockStatus = "on_request"
    compatibility: str = Field(default="", max_length=2000)
    display_order: int = Field(default=0, ge=0, le=10000)
    is_featured: bool = False
    is_active: bool = True
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("currency")
    @classmethod
    def aed(cls, value: str) -> str:
        code = value.strip().upper()
        if code != "AED":
            raise ValueError("Hardware catalogue prices are in AED.")
        return code


class ProductOut(ApiModel):
    id: UUID
    category_id: UUID
    category_name: str
    category_slug: str
    name: str
    slug: str
    sku: str
    short_description: str
    full_description: str
    brand: str
    model_number: str
    manufacturer: str
    specifications: list[SpecIn]
    purchase_price_fils: int | None
    display_price_fils: int | None
    currency: str
    warranty_months: int
    stock_status: str
    compatibility: str
    display_order: int
    is_featured: bool
    is_published: bool
    is_active: bool
    archived: bool
    published_at: datetime | None
    images: list[ImageOut]
    updated_at: datetime


class PackageItemIn(ApiModel):
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)
    is_optional: bool = False
    display_order: int = Field(default=0, ge=0, le=1000)


class PackageItemOut(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str
    product_slug: str
    sku: str
    quantity: int
    is_optional: bool
    display_order: int
    display_price_fils: int | None
    currency: str
    is_published: bool
    archived: bool
    thumb_url: str | None


class PlanRefOut(ApiModel):
    id: UUID
    code: str
    name: str
    monthly_fils: int
    included_registers: int
    active: bool


class PackageIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(default="", max_length=80)
    short_description: str = Field(default="", max_length=300)
    full_description: str = Field(default="", max_length=8000)
    display_price_fils: int | None = Field(default=None, ge=0, le=100_000_000)
    currency: str = Field(default="AED", min_length=3, max_length=3)
    billing_plan_id: UUID | None = None
    package_type: PackageType = "hardware_only"
    display_order: int = Field(default=0, ge=0, le=10000)
    is_featured: bool = False
    is_active: bool = True
    items: list[PackageItemIn] = Field(default_factory=list, max_length=30)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("currency")
    @classmethod
    def aed(cls, value: str) -> str:
        code = value.strip().upper()
        if code != "AED":
            raise ValueError("Hardware catalogue prices are in AED.")
        return code


class PackageOut(ApiModel):
    id: UUID
    name: str
    slug: str
    short_description: str
    full_description: str
    display_price_fils: int | None
    currency: str
    billing_plan_id: UUID | None
    plan: PlanRefOut | None
    package_type: str
    display_order: int
    is_featured: bool
    is_published: bool
    is_active: bool
    published_at: datetime | None
    items: list[PackageItemOut]
    images: list[ImageOut]
    component_value_fils: int | None
    savings_fils: int | None
    updated_at: datetime


class EnquiryNoteIn(ApiModel):
    body: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=3, max_length=500)


class EnquiryNoteOut(ApiModel):
    id: UUID
    body: str
    operator_name: str
    created_at: datetime


class EnquiryStatusIn(ApiModel):
    status: EnquiryStatus
    reason: str = Field(min_length=3, max_length=500)


class EnquiryOut(ApiModel):
    id: UUID
    enquiry_reference: str
    customer_name: str
    business_name: str
    email: str
    phone: str
    country: str
    business_type: str
    enquiry_type: str
    product_id: UUID | None
    package_id: UUID | None
    product_label: str
    package_label: str
    quantity: int
    message: str
    status: str
    source: str
    notes: list[EnquiryNoteOut]
    created_at: datetime
    updated_at: datetime


class PublicEnquiryIn(ApiModel):
    customer_name: str = Field(min_length=2, max_length=120)
    business_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=6, max_length=254)
    phone: str = Field(min_length=7, max_length=32)
    country: str = Field(default="", max_length=80)
    business_type: BusinessType
    enquiry_type: EnquiryType = "custom"
    product_slug: str = Field(default="", max_length=80)
    package_slug: str = Field(default="", max_length=80)
    quantity: int = Field(default=1, ge=1, le=999)
    message: str = Field(min_length=10, max_length=2000)
    source: str = Field(default="/hardware", max_length=200)
    website: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned) is None:
            raise ValueError("Enter a valid email address.")
        return cleaned


class PublicEnquiryOut(ApiModel):
    reference: str
    message: str


class OverviewOut(ApiModel):
    categories: int
    products: int
    published_products: int
    draft_products: int
    archived_products: int
    packages: int
    published_packages: int
    new_enquiries: int
    converted_enquiries: int


class PublicCategoryOut(ApiModel):
    slug: str
    name: str
    description: str
    image_url: str | None
    image_alt: str
    display_order: int


class PublicImageOut(ApiModel):
    url: str
    thumb_url: str
    alt: str
    is_primary: bool


class PublicProductOut(ApiModel):
    slug: str
    name: str
    sku: str
    brand: str
    model_number: str
    manufacturer: str
    short_description: str
    full_description: str
    currency: str
    display_price_fils: int | None
    warranty_months: int
    stock_status: str
    compatibility: str
    is_featured: bool
    category_slug: str
    category_name: str
    specifications: list[SpecIn]
    images: list[PublicImageOut]
    packages: list["PublicPackageCard"]


class PublicPackageCard(ApiModel):
    slug: str
    name: str
    short_description: str
    display_price_fils: int | None
    currency: str
    package_type: str
    is_featured: bool
    thumb_url: str | None


class PublicComponentOut(ApiModel):
    slug: str
    name: str
    quantity: int
    is_optional: bool
    display_price_fils: int | None
    thumb_url: str | None


class PublicPlanOut(ApiModel):
    code: str
    name: str
    monthly_fils: int
    included_registers: int


class PublicPackageOut(ApiModel):
    slug: str
    name: str
    short_description: str
    full_description: str
    display_price_fils: int | None
    currency: str
    package_type: str
    is_featured: bool
    images: list[PublicImageOut]
    plan: PublicPlanOut | None
    items: list[PublicComponentOut]
    component_value_fils: int | None
    savings_fils: int | None


PublicProductOut.model_rebuild()
