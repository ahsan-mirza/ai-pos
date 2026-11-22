"""Order-line choice to skip recipe ingredient consumption.

Revision ID: 20261122_0134
Revises: 20261122_0133
Create Date: 2026-11-22

Additive. Existing rows stay false, which keeps the current recipe draw.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0134"
down_revision: str | None = "20261122_0133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("sale_items", "open_order_items", "kitchen_ticket_items"):
        op.add_column(
            table,
            sa.Column("skip_recipe", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for table in ("kitchen_ticket_items", "open_order_items", "sale_items"):
        op.drop_column(table, "skip_recipe")
