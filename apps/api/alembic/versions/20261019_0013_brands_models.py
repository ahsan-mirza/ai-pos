"""Brands, product models, and product variants: Category > Sub-category > Brand > Model > variant (product).

Backfills one brand per distinct product brand name and links it to the sub-categories it already sells in.

Revision ID: 20261019_0013
Revises: 20261019_0012
Create Date: 2026-10-19
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0013"
down_revision: str | None = "20261019_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _code(name: str, taken: set[str]) -> str:
    base = "-".join(re.findall(r"[A-Za-z0-9]+", name.upper()))[:28] or "BRAND"
    code, suffix = base, 2
    while code in taken:
        code = f"{base[:26]}-{suffix}"
        suffix += 1
    taken.add(code)
    return code


def upgrade() -> None:
    brands = op.create_table(
        "brands",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_brands_name"),
        sa.UniqueConstraint("code", name="uq_brands_code"),
    )
    links = op.create_table(
        "sub_category_brands",
        sa.Column("sub_category_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(
            ["sub_category_id"],
            ["sub_categories.id"],
            name="fk_sub_category_brands_sub_category_id_sub_categories",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], name="fk_sub_category_brands_brand_id_brands", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_sub_category_brands_brand_id", "sub_category_brands", ["brand_id"])
    op.create_table(
        "product_models",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sub_category_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name="fk_product_models_brand_id_brands"),
        sa.ForeignKeyConstraint(
            ["sub_category_id"], ["sub_categories.id"], name="fk_product_models_sub_category_id_sub_categories"
        ),
        sa.UniqueConstraint("brand_id", "sub_category_id", "name", name="uq_product_models_brand_sub_name"),
    )
    op.create_index("ix_product_models_brand_id", "product_models", ["brand_id"])
    op.create_index("ix_product_models_sub_category_id", "product_models", ["sub_category_id"])

    op.add_column("products", sa.Column("brand_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("products", sa.Column("product_model_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("products", sa.Column("variant_attributes", sa.JSON(), nullable=False, server_default="{}"))
    op.create_foreign_key("fk_products_brand_id_brands", "products", "brands", ["brand_id"], ["id"])
    op.create_foreign_key(
        "fk_products_product_model_id_product_models", "products", "product_models", ["product_model_id"], ["id"]
    )
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_product_model_id", "products", ["product_model_id"])

    bind = op.get_bind()
    now = datetime.now(UTC)
    names: dict[str, str] = {}
    for (name,) in bind.execute(sa.text("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL ORDER BY brand")):
        cleaned = " ".join(name.split())
        if cleaned:
            names.setdefault(cleaned.lower(), cleaned)
    taken: set[str] = set()
    for key, name in names.items():
        brand_id = uuid.uuid4()
        bind.execute(
            brands.insert().values(
                id=brand_id, name=name, code=_code(name, taken), description="", created_at=now, updated_at=now
            )
        )
        bind.execute(
            sa.text("UPDATE products SET brand_id = :id, brand = :name WHERE lower(trim(brand)) = :key"),
            {"id": brand_id, "name": name, "key": key},
        )
        subs = bind.execute(
            sa.text(
                "SELECT DISTINCT sub_category_id FROM products WHERE brand_id = :id AND sub_category_id IS NOT NULL"
            ),
            {"id": brand_id},
        )
        for (sub_id,) in subs:
            bind.execute(links.insert().values(sub_category_id=sub_id, brand_id=brand_id))


def downgrade() -> None:
    op.drop_index("ix_products_product_model_id", table_name="products")
    op.drop_index("ix_products_brand_id", table_name="products")
    op.drop_constraint("fk_products_product_model_id_product_models", "products", type_="foreignkey")
    op.drop_constraint("fk_products_brand_id_brands", "products", type_="foreignkey")
    op.drop_column("products", "variant_attributes")
    op.drop_column("products", "product_model_id")
    op.drop_column("products", "brand_id")
    op.drop_index("ix_product_models_sub_category_id", table_name="product_models")
    op.drop_index("ix_product_models_brand_id", table_name="product_models")
    op.drop_table("product_models")
    op.drop_index("ix_sub_category_brands_brand_id", table_name="sub_category_brands")
    op.drop_table("sub_category_brands")
    op.drop_table("brands")
