"""Restaurant and cafe products may omit a SKU.

Revision ID: 20261125_0137
Revises: 20261123_0136
Create Date: 2026-11-25

Existing SKUs stay as they are. A missing SKU is stored as null so more than
one menu item can exist without a code. Search still matches the product name.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_0137"
down_revision: str | None = "20261123_0136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _compact(column: str) -> str:
    return f"replace(replace({column}, '-', ''), ' ', '')"


def _haystack() -> str:
    parts = [
        "name",
        "coalesce(model_number, '')",
        "barcode",
        "coalesce(sku, '')",
        "category",
        "coalesce(brand, '')",
        "coalesce(season, '')",
        "coalesce(collection, '')",
        _compact("coalesce(model_number, '')"),
        _compact("coalesce(sku, '')"),
        _compact("barcode"),
        "coalesce(generic_name, '')",
        "coalesce(gtin, '')",
        _compact("coalesce(gtin, '')"),
    ]
    return "lower(" + " || ' ' || ".join(parts) + ")"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("products") as batch:
            batch.alter_column("sku", existing_type=sa.String(length=64), nullable=True)
        return
    op.alter_column("products", "sku", existing_type=sa.String(length=64), nullable=True)
    op.drop_index("ix_products_search_trgm", table_name="products")
    op.drop_column("products", "search_text")
    op.add_column("products", sa.Column("search_text", sa.Text(), sa.Computed(_haystack(), persisted=True)))
    op.create_index(
        "ix_products_search_trgm",
        "products",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.execute("UPDATE products SET sku = substr(replace(cast(id as varchar), '-', ''), 1, 64) WHERE sku IS NULL")
    op.alter_column("products", "sku", existing_type=sa.String(length=64), nullable=False)
