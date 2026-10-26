from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    ColumnElement,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

if TYPE_CHECKING:
    from app.models.brand import ProductModel
    from app.models.category import Category, SubCategory
    from app.models.product_price import ProductPrice


def _compact(value: ColumnElement[str]) -> ColumnElement[str]:
    return func.replace(func.replace(value, "-", ""), " ", "")


def search_haystack(
    name: Column[str],
    model_number: Column[str],
    barcode: Column[str],
    sku: Column[str],
    category: Column[str],
    brand: Column[str],
    season: Column[str],
    collection: Column[str],
) -> ColumnElement[str]:
    """Every searchable field, space separated, then model / SKU / barcode without separators ("ga05843us")."""
    model = func.coalesce(model_number, "")
    parts: list[ColumnElement[str]] = [
        name,
        model,
        barcode,
        sku,
        category,
        func.coalesce(brand, ""),
        func.coalesce(season, ""),
        func.coalesce(collection, ""),
        _compact(model),
        _compact(sku),
        _compact(barcode),
    ]
    joined = parts[0]
    for part in parts[1:]:
        joined = joined + " " + part
    return func.lower(joined)


class Product(TenantScoped, TimestampMixin, Base):
    """Global catalog entry. Per-branch stock lives in inventory_levels; price_cents is the RETAIL price."""

    __tablename__ = "products"
    __table_args__ = (
        tenant_unique("sku", name="uq_products_sku"),
        tenant_unique("barcode", name="uq_products_barcode"),
        tenant_unique("plu_code", name="uq_products_plu_code"),
        CheckConstraint("price_cents >= 0", name="price_nonnegative"),
        CheckConstraint("min_order_quantity >= 1", name="moq_positive"),
        CheckConstraint("tare_grams >= 0", name="tare_nonnegative"),
        CheckConstraint(
            "minimum_age IS NULL OR (minimum_age >= 1 AND minimum_age <= 120)",
            name="ck_products_minimum_age",
        ),
        CheckConstraint(
            "item_type IN ('MADE_TO_ORDER', 'RAW_INGREDIENT', 'PRE_PACKAGED')",
            name="ck_products_item_type",
        ),
        # Keyset paging of the full catalog (GET /products?after=) for registers syncing tens of thousands of SKUs.
        Index("ix_products_name_id", "name", "id"),
        Index(
            "ix_products_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
        Index("ix_products_specifications", "specifications", postgresql_using="gin").ddl_if(dialect="postgresql"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(64))
    barcode: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    model_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # Denormalized category name for search and reporting; kept in step with category_id by the catalog services.
    category: Mapped[str] = mapped_column(String(80), index=True)
    # Fashion attributes, copied from the model (see fashion_attributes.copy_from_model) or set on a standalone item.
    season: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    collection: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    gender: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    material: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    care: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Lowercased search haystack (see search_terms.token_condition); Postgres serves LIKE '%word%' from a trigram index.
    search_text: Mapped[str] = mapped_column(
        Text,
        Computed(
            search_haystack(
                name.column,
                model_number.column,
                barcode.column,
                sku.column,
                category.column,
                brand.column,
                season.column,
                collection.column,
            ),
            persisted=True,
        ),
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )
    sub_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sub_categories.id"),
        nullable=True,
        index=True,
    )
    # Sub-model: a sellable variant of a model. Brand, sub-category and category follow the model when it is set.
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id"),
        nullable=True,
        index=True,
    )
    product_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_models.id"),
        nullable=True,
        index=True,
    )
    variant_attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    # Technical details that follow the category (processor, capacity, fabric). JSON on SQLite tests, JSONB in Postgres.
    specifications: Mapped[dict[str, str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    price_cents: Mapped[int] = mapped_column(Integer)
    # The price before the active markdown; null when the product is not marked down.
    compare_at_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markdown_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("markdown_events.id", ondelete="SET NULL", use_alter=True, name="fk_products_markdown_event"),
        nullable=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3))
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=False)
    min_order_quantity: Mapped[int] = mapped_column(Integer, default=1)
    tax_category: Mapped[str] = mapped_column(String(8), default="STANDARD")
    is_open_price: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fixed-price services (warranty plans, setup fees) are sold without stock.
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    # Recipes module: stocked only to make dishes; registers never sell it.
    is_ingredient: Mapped[bool] = mapped_column(Boolean, default=False)
    # MADE_TO_ORDER dishes are produced from a recipe and carry no stock of their own.
    # RAW_INGREDIENT and PRE_PACKAGED stay on the stock overview.
    item_type: Mapped[str] = mapped_column(String(20), default="PRE_PACKAGED")
    is_stock_tracked: Mapped[bool] = mapped_column(Boolean, default=True)
    sellable_units: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["PIECE"])
    # Weighed goods: stock and sale quantities count grams and price_cents is the price per kilogram.
    sold_by_weight: Mapped[bool] = mapped_column(Boolean, default=False)
    # Price-look-up code a scale prints into its EAN-13 labels (4-6 digits).
    plu_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    tare_grams: Mapped[int] = mapped_column(Integer, default=0)
    # Set only for products that need an age check at the till. Null means unrestricted. No country default.
    minimum_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Practice item loaded at signup; Go live deletes it.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sold as final sale (no refund or exchange without a manager); markdown events can set it.
    is_final_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    category_ref: Mapped[Category | None] = relationship("Category", lazy="joined")
    sub_category_ref: Mapped[SubCategory | None] = relationship("SubCategory", lazy="joined")
    product_model: Mapped[ProductModel | None] = relationship("ProductModel", lazy="joined")
    prices: Mapped[list[ProductPrice]] = relationship(
        "ProductPrice",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ProductPrice.price_tier",
    )
