"""Modules IT support forces on or off from the console.

Revision ID: 20261021_0055
Revises: 20261021_0054
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0055"
down_revision: str | None = "20261021_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("managed_capabilities", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "managed_capabilities")
