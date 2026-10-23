"""Store a one-time password-reset code on the portal user.

Revision ID: 20261023_0068
Revises: 20261023_0067
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0068"
down_revision: str | None = "20261023_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("reset_code_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("reset_code_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reset_code_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reset_code_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "reset_code_attempts")
    op.drop_column("users", "reset_code_sent_at")
    op.drop_column("users", "reset_code_expires_at")
    op.drop_column("users", "reset_code_hash")
