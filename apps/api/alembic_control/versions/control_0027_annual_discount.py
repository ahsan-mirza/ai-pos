"""Published annual discount for new Free, Growth, Pro AI, and Enterprise invoices.

Revision ID: control_0027
Revises: control_0026
Create Date: 2026-11-09

Lite, Standard, and Pro keep the billing-cycle discount. Issued invoices are not rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0027"
down_revision: str | None = "control_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "billing_policy",
        sa.Column("new_annual_discount_bps", sa.Integer(), nullable=False, server_default="2000"),
    )


def downgrade() -> None:
    op.drop_column("billing_policy", "new_annual_discount_bps")
