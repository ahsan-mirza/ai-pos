"""Tenant attribute definitions and the typed value stored for one product.

Display text is also copied onto ``products.specifications`` so the existing catalog,
POS cache, and product form keep reading one field. Serials, IMEIs, batches, and expiry
stay on their own tables.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

DATA_TYPES = ("text", "number", "decimal", "boolean", "date", "select", "multi_select", "measurement")


class ProductAttributeDefinition(TenantScoped, TimestampMixin, Base):
    __tablename__ = "product_attribute_definitions"
    __table_args__ = (tenant_unique("key", name="uq_product_attribute_definitions_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    data_type: Mapped[str] = mapped_column(String(16))
    unit: Mapped[str] = mapped_column(String(16), default="")
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Empty means every business type. A copied template lists the types it was offered to.
    profiles: Mapped[list[str]] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # template rows are copies of the shared catalog. custom rows belong only to this tenant.
    origin: Mapped[str] = mapped_column(String(16), default="custom")
    template_key: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ProductAttributeValue(TenantScoped, TimestampMixin, Base):
    __tablename__ = "product_attribute_values"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", "definition_id", name="uq_product_attribute_values_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_attribute_definitions.id", ondelete="CASCADE"), index=True
    )
    text_value: Mapped[str] = mapped_column(String(200), default="")
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    bool_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    date_value: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit: Mapped[str] = mapped_column(String(16), default="")
