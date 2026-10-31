"""A kitchen line can be ready while the rest of its ticket is still cooking.

Revision ID: 20261031_0091
Revises: 20261030_0090
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0091"
down_revision: str | None = "20261030_0090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("kitchen_ticket_items", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("kitchen_ticket_items", "ready_at")
