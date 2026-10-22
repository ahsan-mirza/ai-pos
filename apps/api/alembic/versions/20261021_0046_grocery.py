"""Grocery modules: expiry flags on batch draws, per-module settings, and weighed products.

Revision ID: 20261021_0046
Revises: 20261021_0045
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0046"
down_revision: str | None = "20261021_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_allocations", sa.Column("expired", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("business_settings", sa.Column("module_settings", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("sold_by_weight", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("products", sa.Column("plu_code", sa.String(6), nullable=True))
    op.add_column("products", sa.Column("tare_grams", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_products_plu_code", "products", ["plu_code"])
    op.create_check_constraint("ck_products_tare_nonnegative", "products", "tare_grams >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_products_tare_nonnegative", "products", type_="check")
    op.drop_constraint("uq_products_plu_code", "products", type_="unique")
    op.drop_column("products", "tare_grams")
    op.drop_column("products", "plu_code")
    op.drop_column("products", "sold_by_weight")
    op.drop_column("business_settings", "module_settings")
    op.drop_column("batch_allocations", "expired")
