"""Allow signup tax identifiers that are not a 15-digit UAE TRN.

Revision ID: control_0019
Revises: control_0018
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0019"
down_revision: str | None = "control_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "signup_requests",
        "trn",
        existing_type=sa.String(15),
        type_=sa.String(32),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "signup_requests",
        "trn",
        existing_type=sa.String(32),
        type_=sa.String(15),
        existing_nullable=True,
    )
