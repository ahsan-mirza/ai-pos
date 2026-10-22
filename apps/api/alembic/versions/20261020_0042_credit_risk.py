"""Latest credit risk score, grade and explanation on each customer.

Revision ID: 20261020_0042
Revises: 20261020_0041
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0042"
down_revision: str | None = "20261020_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("risk_score", sa.Integer(), nullable=True))
    op.add_column("customers", sa.Column("risk_grade", sa.String(length=1), nullable=True))
    op.add_column("customers", sa.Column("risk_detail", sa.JSON(), nullable=True))
    op.add_column("customers", sa.Column("risk_computed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_customers_risk_grade", "customers", ["risk_grade"])


def downgrade() -> None:
    op.drop_index("ix_customers_risk_grade", table_name="customers")
    for column in ("risk_computed_at", "risk_detail", "risk_grade", "risk_score"):
        op.drop_column("customers", column)
