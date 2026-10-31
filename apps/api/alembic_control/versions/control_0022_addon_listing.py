"""Marketplace copy and price history on the existing add-on catalogue.

Revision ID: control_0022
Revises: control_0021
Create Date: 2026-10-31

Does not rewrite invoices or subscription items. Apply on the control database only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0022"
down_revision: str | None = "control_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("billing_addons", sa.Column("listing", sa.JSON(), nullable=True))
    op.add_column("billing_addons", sa.Column("price_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("billing_addons", "price_history")
    op.drop_column("billing_addons", "listing")
