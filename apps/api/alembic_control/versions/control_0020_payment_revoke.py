"""Record when a verified payment's activation is revoked.

Revision ID: control_0020
Revises: control_0019
Create Date: 2026-10-28

The payment row stays. These columns are empty until an administrator revokes an activation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0020"
down_revision: str | None = "control_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("billing_payments", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_payments", sa.Column("revoke_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("billing_payments", "revoke_reason")
    op.drop_column("billing_payments", "revoked_at")
