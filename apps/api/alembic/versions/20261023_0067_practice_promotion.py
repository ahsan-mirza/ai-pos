"""Remember which live stores were promoted out of practice mode.

Revision ID: 20261023_0067
Revises: 20261022_0066
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0067"
down_revision: str | None = "20261022_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_settings",
        sa.Column("promoted_from_practice", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("business_settings", "promoted_from_practice")
