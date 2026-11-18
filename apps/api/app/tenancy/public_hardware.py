"""Public marketing catalogue. Platform records on the registry connection.

These tables do not use tenant_id. A store's own products, stock, and registers stay on the
operational models. The commercial lease catalogue (hardware_items) is a different table.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.tenancy.models import ControlBase, _now

STOCK_STATUSES = ("in_stock", "limited", "out_of_stock", "on_request")
PACKAGE_TYPES = ("hardware_only", "hardware_software", "all_in_one", "custom")
ENQUIRY_STATUSES = ("new", "contacted", "quoted", "converted", "closed")
ENQUIRY_TYPES = ("product", "package", "custom", "installation")


class PublicHardwareCategory(ControlBase):
    __tablename__ = "public_hardware_categories"
    __table_args__ = (UniqueConstraint("slug", name="uq_public_hardware_categories_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    image_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    thumb_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_alt: Mapped[str] = mapped_column(String(160), default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PublicHardwareProduct(ControlBase):
    __tablename__ = "public_hardware_products"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_public_hardware_products_slug"),
        UniqueConstraint("sku", name="uq_public_hardware_products_sku"),
        CheckConstraint(
            "stock_status IN ('in_stock', 'limited', 'out_of_stock', 'on_request')",
            name="stock_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_categories.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    sku: Mapped[str] = mapped_column(String(32))
    short_description: Mapped[str] = mapped_column(String(300), default="")
    full_description: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(80), default="")
    model_number: Mapped[str] = mapped_column(String(80), default="")
    manufacturer: Mapped[str] = mapped_column(String(80), default="")
    specifications: Mapped[list] = mapped_column(JSON, default=list)
    purchase_price_fils: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_price_fils: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    warranty_months: Mapped[int] = mapped_column(Integer, default=0)
    stock_status: Mapped[str] = mapped_column(String(16), default="on_request")
    compatibility: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PublicHardwarePackage(ControlBase):
    __tablename__ = "public_hardware_packages"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_public_hardware_packages_slug"),
        CheckConstraint(
            "package_type IN ('hardware_only', 'hardware_software', 'all_in_one', 'custom')",
            name="package_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    short_description: Mapped[str] = mapped_column(String(300), default="")
    full_description: Mapped[str] = mapped_column(Text, default="")
    display_price_fils: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    billing_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    package_type: Mapped[str] = mapped_column(String(24), default="hardware_only")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PublicHardwarePackageItem(ControlBase):
    __tablename__ = "public_hardware_package_items"
    __table_args__ = (
        UniqueConstraint("package_id", "product_id", name="uq_public_hardware_package_items_product"),
        CheckConstraint("quantity >= 1 AND quantity <= 99", name="quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_packages.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_products.id"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class PublicHardwareImage(ControlBase):
    """A WebP already stored under media/platform/catalog. The row points at the key; the bytes are not here."""

    __tablename__ = "public_hardware_product_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("public_hardware_products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("public_hardware_packages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(80))
    thumb_key: Mapped[str] = mapped_column(String(80))
    alt: Mapped[str] = mapped_column(String(160), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PublicHardwareEnquiry(ControlBase):
    __tablename__ = "public_hardware_enquiries"
    __table_args__ = (
        UniqueConstraint("enquiry_reference", name="uq_public_hardware_enquiries_reference"),
        CheckConstraint("status IN ('new', 'contacted', 'quoted', 'converted', 'closed')", name="status"),
        CheckConstraint("enquiry_type IN ('product', 'package', 'custom', 'installation')", name="enquiry_type"),
        CheckConstraint("quantity >= 1 AND quantity <= 999", name="quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enquiry_reference: Mapped[str] = mapped_column(String(24))
    customer_name: Mapped[str] = mapped_column(String(120))
    business_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(80), default="")
    business_type: Mapped[str] = mapped_column(String(32))
    enquiry_type: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_packages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_label: Mapped[str] = mapped_column(String(120), default="")
    package_label: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PublicHardwareEnquiryNote(ControlBase):
    """Operator note. Never returned by the public enquiry API."""

    __tablename__ = "public_hardware_enquiry_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enquiry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_hardware_enquiries.id", ondelete="CASCADE"), index=True
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("operators.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
