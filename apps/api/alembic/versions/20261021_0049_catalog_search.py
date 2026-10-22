"""Catalog search at supermarket scale: a generated search_text column with a trigram index (Postgres), and a
(name, id) index for keyset paging of GET /products.

Revision ID: 20261021_0049
Revises: 20261021_0048
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0049"
down_revision: str | None = "20261021_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _compact(column: str) -> str:
    return f"replace(replace({column}, '-', ''), ' ', '')"


# Same haystack as app.models.product.search_haystack.
HAYSTACK = "lower(" + " || ' ' || ".join(
    [
        "name",
        "coalesce(model_number, '')",
        "barcode",
        "sku",
        "category",
        "coalesce(brand, '')",
        _compact("coalesce(model_number, '')"),
        _compact("sku"),
        _compact("barcode"),
    ]
) + ")"


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # SQLite can only add virtual generated columns to an existing table; reads behave the same.
    op.add_column("products", sa.Column("search_text", sa.Text(), sa.Computed(HAYSTACK, persisted=postgres or None)))
    op.create_index("ix_products_name_id", "products", ["name", "id"])
    if postgres:
        op.create_index(
            "ix_products_search_trgm",
            "products",
            ["search_text"],
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_products_search_trgm", table_name="products")
    op.drop_index("ix_products_name_id", table_name="products")
    op.drop_column("products", "search_text")
