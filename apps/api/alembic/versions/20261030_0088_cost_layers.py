"""Receipt cost layers, last and default purchase cost, and the company costing method.

Revision ID: 20261030_0088
Revises: 20261030_0087
Create Date: 2026-10-30

Existing stock is not given a fabricated purchase history. New goods receipts open a layer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0088"
down_revision: str | None = "20261030_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("default_cost_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("last_purchase_cost_cents", sa.Integer(), nullable=True))
    op.add_column("inventory_levels", sa.Column("weighted_average_cost_cents", sa.Integer(), nullable=True))
    op.add_column("purchase_batches", sa.Column("goods_receipt_id", sa.Uuid(), nullable=True))
    op.add_column(
        "business_settings",
        sa.Column("inventory_costing", sa.String(length=20), nullable=False, server_default="FIFO"),
    )
    op.create_index("ix_purchase_batches_goods_receipt_id", "purchase_batches", ["goods_receipt_id"])
    op.create_foreign_key(
        "fk_purchase_batches_goods_receipt_id",
        "purchase_batches",
        "goods_receipts",
        ["goods_receipt_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_products_default_cost_nonnegative",
        "products",
        "default_cost_cents IS NULL OR default_cost_cents >= 0",
    )
    op.create_check_constraint(
        "ck_products_last_cost_nonnegative",
        "products",
        "last_purchase_cost_cents IS NULL OR last_purchase_cost_cents >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_levels_average_nonnegative",
        "inventory_levels",
        "weighted_average_cost_cents IS NULL OR weighted_average_cost_cents >= 0",
    )
    op.create_check_constraint(
        "ck_business_settings_inventory_costing",
        "business_settings",
        "inventory_costing IN ('FIFO', 'WEIGHTED_AVERAGE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_business_settings_inventory_costing", "business_settings", type_="check")
    op.drop_constraint("ck_inventory_levels_average_nonnegative", "inventory_levels", type_="check")
    op.drop_constraint("ck_products_last_cost_nonnegative", "products", type_="check")
    op.drop_constraint("ck_products_default_cost_nonnegative", "products", type_="check")
    op.drop_constraint("fk_purchase_batches_goods_receipt_id", "purchase_batches", type_="foreignkey")
    op.drop_index("ix_purchase_batches_goods_receipt_id", table_name="purchase_batches")
    op.drop_column("business_settings", "inventory_costing")
    op.drop_column("purchase_batches", "goods_receipt_id")
    op.drop_column("inventory_levels", "weighted_average_cost_cents")
    op.drop_column("products", "last_purchase_cost_cents")
    op.drop_column("products", "default_cost_cents")
