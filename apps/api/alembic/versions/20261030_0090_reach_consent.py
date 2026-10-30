"""Separate marketing consent from receipts, and label usage as marketing or transactional.

Revision ID: 20261030_0090
Revises: 20261030_0089
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0090"
down_revision: str | None = "20261030_0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("marketing_whatsapp_opt_in", "marketing_sms_opt_in", "marketing_email_opt_in"):
        op.add_column("customers", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "reach_usage",
        sa.Column("purpose", sa.String(length=16), nullable=False, server_default="marketing"),
    )


def downgrade() -> None:
    op.drop_column("reach_usage", "purpose")
    for column in ("marketing_email_opt_in", "marketing_sms_opt_in", "marketing_whatsapp_opt_in"):
        op.drop_column("customers", column)
