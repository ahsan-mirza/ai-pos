"""Pro AI promotional modules on the store, with the moment they stop.

Revision ID: 20261109_0100
Revises: 20261105_0099
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0100"
down_revision: str | None = "20261105_0099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("promotional_capabilities", sa.JSON(), nullable=True))
    op.add_column("business_settings", sa.Column("promotional_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "promotional_until")
    op.drop_column("business_settings", "promotional_capabilities")
