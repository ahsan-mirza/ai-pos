"""Console controls for future Pro AI trials and the commercial revision.

Revision ID: control_0026
Revises: control_0025
Create Date: 2026-11-09

Existing promotional_trials rows are not rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0026"
down_revision: str | None = "control_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "billing_policy",
        sa.Column("pro_ai_trial_days", sa.Integer(), nullable=False, server_default="14"),
    )
    op.add_column(
        "billing_policy",
        sa.Column(
            "pro_ai_trial_plans",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("""'["FREE", "GROWTH"]'::json"""),
        ),
    )
    op.add_column(
        "billing_policy",
        sa.Column("commercial_revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("billing_policy", "commercial_revision")
    op.drop_column("billing_policy", "pro_ai_trial_plans")
    op.drop_column("billing_policy", "pro_ai_trial_days")
