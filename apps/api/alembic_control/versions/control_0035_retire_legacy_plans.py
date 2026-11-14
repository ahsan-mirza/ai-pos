"""Retire Lite, Standard, and Pro from sale.

Revision ID: control_0035
Revises: control_0034
Create Date: 2026-11-14

The three rows stay in billing_plans. Subscriptions, invoices, payments, and
plan-change history point at those rows or store the plan code as text, and
neither is rewritten. active = false removes them from checkout and from the
public catalog. Downgrade marks the same three codes active again. It does not
recreate a row that was never there, and it does not restore a price or a
module list.

This migration does not change tenant subscriptions or invoice amounts.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0035"
down_revision: str | None = "control_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.execute(
        sa.text("UPDATE billing_plans SET active = :active WHERE code IN ('LITE', 'STANDARD', 'PRO')").bindparams(
            active=False
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE billing_plans SET active = :active WHERE code IN ('LITE', 'STANDARD', 'PRO')").bindparams(
            active=True
        )
    )
