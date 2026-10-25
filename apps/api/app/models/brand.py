from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


def _active_tenant_id() -> uuid.UUID:
    from app.tenancy.scoping import active_tenant_id

    return active_tenant_id()


if TYPE_CHECKING:
    from app.models.category import SubCategory

sub_category_brands = Table(
    "sub_category_brands",
    Base.metadata,
    Column("tenant_id", Uuid(as_uuid=True), primary_key=True, default=_active_tenant_id),
    Column(
        "sub_category_id",
        Uuid(as_uuid=True),
        ForeignKey("sub_categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("brand_id", Uuid(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Brand(TenantScoped, TimestampMixin, Base):
    """Global manufacturer list; a brand is linked to every sub-category it sells in."""

    __tablename__ = "brands"
    __table_args__ = (
        tenant_unique("name", name="uq_brands_name"),
        tenant_unique("code", name="uq_brands_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(255), default="")
    sub_categories: Mapped[list[SubCategory]] = relationship(
        "SubCategory",
        secondary=sub_category_brands,
        order_by="SubCategory.name",
        lazy="selectin",
    )


class ProductModel(TenantScoped, TimestampMixin, Base):
    """A brand's model within one sub-category (e.g. Apple iPhone 16 Pro); its sellable variants are products."""

    __tablename__ = "product_models"
    __table_args__ = (tenant_unique("brand_id", "sub_category_id", "name", name="uq_product_models_brand_sub_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("brands.id"), index=True)
    sub_category_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sub_categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    # Fashion attributes; copied onto every variant (Product) so search, filters and reports need no join.
    season: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    collection: Mapped[str | None] = mapped_column(String(80), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(12), nullable=True)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    care: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[Brand] = relationship("Brand", lazy="joined")
    sub_category: Mapped[SubCategory] = relationship("SubCategory", lazy="joined")
