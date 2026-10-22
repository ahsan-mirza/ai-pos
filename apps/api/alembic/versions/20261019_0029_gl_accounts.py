"""Account-code overrides for the general-ledger journal export.

Revision ID: 20261019_0029
Revises: 20261019_0028
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0029"
down_revision: str | None = "20261019_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("gl_accounts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "gl_accounts")
