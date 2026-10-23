"""Let a user sell open-price items even when their role does not.

Revision ID: 20261023_0069
Revises: 20261023_0068
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0069"
down_revision: str | None = "20261023_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_sell_open_price", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "can_sell_open_price")
