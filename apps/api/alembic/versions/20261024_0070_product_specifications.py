"""Store category-specific product details in JSONB.

Revision ID: 20261024_0070
Revises: 20261023_0069
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0070"
down_revision: str | None = "20261023_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("specifications", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_products_specifications",
        "products",
        ["specifications"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_products_specifications", table_name="products")
    op.drop_column("products", "specifications")
