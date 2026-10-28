"""Guided trial progress that is not already a business record.

Revision ID: 20261028_0081
Revises: 20261028_0080
Create Date: 2026-10-28

Catalogue, registers, and go-live stay derived from those tables. This column only
remembers that the portal was opened and which optional actions were skipped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0081"
down_revision: str | None = "20261028_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("guided_onboarding", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "guided_onboarding")
