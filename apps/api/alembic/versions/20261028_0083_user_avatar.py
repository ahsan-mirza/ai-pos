"""Remember each user's profile photo key.

Revision ID: 20261028_0083
Revises: 20261028_0082
Create Date: 2026-10-28

The column is empty for every existing user. Photos are files under the tenant media folder, not bytes in this table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0083"
down_revision: str | None = "20261028_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
