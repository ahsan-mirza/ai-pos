"""Store-code recovery challenges. Existing users and passwords are left unchanged.

Revision ID: control_0018
Revises: control_0017
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0018"
down_revision: str | None = "control_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recovery_challenges",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("purpose", "email", name="uq_recovery_challenges_purpose_email"),
    )
    op.create_index("ix_recovery_challenges_email", "recovery_challenges", ["email"])


def downgrade() -> None:
    op.drop_index("ix_recovery_challenges_email", table_name="recovery_challenges")
    op.drop_table("recovery_challenges")
