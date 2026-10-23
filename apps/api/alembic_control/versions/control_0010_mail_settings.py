"""Platform mailbox used to email store users.

Revision ID: control_0010
Revises: control_0009
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0010"
down_revision: str | None = "control_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("host", sa.String(255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="465"),
        sa.Column("security", sa.String(16), nullable=False, server_default="ssl"),
        sa.Column("username", sa.String(254), nullable=False, server_default=""),
        sa.Column("password_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("from_address", sa.String(254), nullable=False, server_default=""),
        sa.Column("from_name", sa.String(120), nullable=False, server_default="AI POS"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mail_settings")
