"""Stock counts can be limited to one product model (a size grid).

Revision ID: 20261021_0064
Revises: 20261021_0063
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0064"
down_revision: str | None = "20261021_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stock_counts", sa.Column("product_model_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_stock_counts_product_model", "stock_counts", "product_models", ["product_model_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_stock_counts_product_model", "stock_counts", type_="foreignkey")
    op.drop_column("stock_counts", "product_model_id")
