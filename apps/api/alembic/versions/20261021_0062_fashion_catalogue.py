"""Fashion catalogue: product photos (product_images), season / collection / gender / material / fit / care on
models and variants (season and collection join the search haystack), and the sales associate on sales.

Revision ID: 20261021_0062
Revises: 20261021_0061
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0062"
down_revision: str | None = "20261021_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ATTRIBUTES = (
    ("season", 16),
    ("collection", 80),
    ("gender", 12),
    ("material", 120),
    ("fit", 40),
    ("care", 255),
)


def _compact(column: str) -> str:
    return f"replace(replace({column}, '-', ''), ' ', '')"


def _haystack(fashion: bool) -> str:
    """Same haystack as app.models.product.search_haystack (before and after this revision)."""
    parts = [
        "name",
        "coalesce(model_number, '')",
        "barcode",
        "sku",
        "category",
        "coalesce(brand, '')",
        *(["coalesce(season, '')", "coalesce(collection, '')"] if fashion else []),
        _compact("coalesce(model_number, '')"),
        _compact("sku"),
        _compact("barcode"),
    ]
    return "lower(" + " || ' ' || ".join(parts) + ")"


def _rebuild_search(fashion: bool) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.drop_index("ix_products_search_trgm", table_name="products")
    op.drop_column("products", "search_text")
    op.add_column(
        "products", sa.Column("search_text", sa.Text(), sa.Computed(_haystack(fashion), persisted=postgres or None))
    )
    if postgres:
        op.create_index(
            "ix_products_search_trgm",
            "products",
            ["search_text"],
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        )


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "product_model_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("product_models.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("attribute_key", sa.String(32), nullable=True),
        sa.Column("attribute_value", sa.String(64), nullable=True),
        sa.Column("key", sa.String(160), nullable=False, unique=True),
        sa.Column("thumb_key", sa.String(160), nullable=False, unique=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(product_id IS NOT NULL) <> (product_model_id IS NOT NULL)", name="product_image_owner_exactly_one"
        ),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])
    op.create_index("ix_product_images_product_model_id", "product_images", ["product_model_id"])

    with op.batch_alter_table("product_models") as batch:
        for name, length in ATTRIBUTES:
            batch.add_column(sa.Column(name, sa.String(length), nullable=True))
    op.create_index("ix_product_models_season", "product_models", ["season"])
    with op.batch_alter_table("products") as batch:
        for name, length in ATTRIBUTES:
            batch.add_column(sa.Column(name, sa.String(length), nullable=True))
    for name in ("season", "collection", "gender"):
        op.create_index(f"ix_products_{name}", "products", [name])
    _rebuild_search(fashion=True)

    with op.batch_alter_table("sales") as batch:
        batch.add_column(sa.Column("sales_associate_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key("fk_sales_sales_associate", "users", ["sales_associate_id"], ["id"])
    op.create_index("ix_sales_sales_associate_id", "sales", ["sales_associate_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_sales_associate_id", table_name="sales")
    with op.batch_alter_table("sales") as batch:
        batch.drop_constraint("fk_sales_sales_associate", type_="foreignkey")
        batch.drop_column("sales_associate_id")
    _rebuild_search(fashion=False)
    for name in ("season", "collection", "gender"):
        op.drop_index(f"ix_products_{name}", table_name="products")
    with op.batch_alter_table("products") as batch:
        for name, _ in ATTRIBUTES:
            batch.drop_column(name)
    op.drop_index("ix_product_models_season", table_name="product_models")
    with op.batch_alter_table("product_models") as batch:
        for name, _ in ATTRIBUTES:
            batch.drop_column(name)
    op.drop_index("ix_product_images_product_model_id", table_name="product_images")
    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_table("product_images")
