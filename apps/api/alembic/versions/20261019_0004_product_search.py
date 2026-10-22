"""Product model number and brand for universal search.

Revision ID: 20261019_0004
Revises: 20261019_0003
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0004"
down_revision: str | None = "20261019_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("model_number", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("brand", sa.String(length=80), nullable=True))
    op.create_index("ix_products_model_number", "products", ["model_number"])
    op.create_index("ix_products_brand", "products", ["brand"])


def downgrade() -> None:
    op.drop_index("ix_products_brand", table_name="products")
    op.drop_index("ix_products_model_number", table_name="products")
    op.drop_column("products", "brand")
    op.drop_column("products", "model_number")
