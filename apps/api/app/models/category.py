from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class Category(TenantScoped, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        tenant_unique("name", name="uq_categories_name"),
        tenant_unique("code", name="uq_categories_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(255), default="")
    sub_categories: Mapped[list[SubCategory]] = relationship(
        "SubCategory",
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="SubCategory.name",
        lazy="selectin",
    )


class SubCategory(TenantScoped, TimestampMixin, Base):
    __tablename__ = "sub_categories"
    __table_args__ = (
        tenant_unique("category_id", "name", name="uq_sub_categories_category_name"),
        tenant_unique("category_id", "code", name="uq_sub_categories_category_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[Category] = relationship("Category", back_populates="sub_categories")
