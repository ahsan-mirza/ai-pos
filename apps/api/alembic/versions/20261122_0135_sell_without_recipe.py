"""Product-level prepared-item toggle for restaurant and cafe dishes.

Revision ID: 20261122_0135
Revises: 20261122_0134
Create Date: 2026-11-22

Additive. Existing products stay false, so a recipe still draws when one
exists. An empty recipe is not treated as prepared. Not applied to a
protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0135"
down_revision: str | None = "20261122_0134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("sell_without_recipe", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("products", "sell_without_recipe")
