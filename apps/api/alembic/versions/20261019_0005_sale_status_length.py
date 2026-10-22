"""Widen sales.status to fit partially_refunded.

Revision ID: 20261019_0005
Revises: 20261019_0004
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0005"
down_revision: str | None = "20261019_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("sales", "status", type_=sa.String(length=24), existing_type=sa.String(length=16))


def downgrade() -> None:
    op.execute("UPDATE sales SET status = 'completed' WHERE status = 'partially_refunded'")
    op.alter_column("sales", "status", type_=sa.String(length=16), existing_type=sa.String(length=24))
