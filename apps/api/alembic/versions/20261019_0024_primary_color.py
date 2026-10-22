"""Admin portal primary (accent) color on business settings.

Revision ID: 20261019_0024
Revises: 20261019_0023
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0024"
down_revision: str | None = "20261019_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("primary_color", sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "primary_color")
