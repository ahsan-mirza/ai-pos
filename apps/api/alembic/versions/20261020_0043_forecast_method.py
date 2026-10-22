"""Forecast method, backtest accuracy and trend on replenishment suggestions.

Revision ID: 20261020_0043
Revises: 20261020_0042
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0043"
down_revision: str | None = "20261020_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("replenishment_suggestions", sa.Column("forecast_method", sa.String(length=16), nullable=True))
    op.add_column("replenishment_suggestions", sa.Column("forecast_accuracy_bps", sa.Integer(), nullable=True))
    op.add_column("replenishment_suggestions", sa.Column("trend_pct_week", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("trend_pct_week", "forecast_accuracy_bps", "forecast_method"):
        op.drop_column("replenishment_suggestions", column)
