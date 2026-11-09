"""Modules included by the store's current plan, beside the business-type preset.

Revision ID: 20261109_0101
Revises: 20261109_0100
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0101"
down_revision: str | None = "20261109_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("plan_capabilities", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "plan_capabilities")
