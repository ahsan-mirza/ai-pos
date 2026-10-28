"""Widen the business tax identifier and remember the signup country.

Revision ID: 20261028_0082
Revises: 20261028_0081
Create Date: 2026-10-28

Existing 15-digit TRNs still fit. Country is empty for stores created before this column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0082"
down_revision: str | None = "20261028_0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "business_settings",
        "trn",
        existing_type=sa.String(15),
        type_=sa.String(32),
        existing_nullable=True,
    )
    op.add_column("business_settings", sa.Column("country", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("business_settings", "country")
    op.alter_column(
        "business_settings",
        "trn",
        existing_type=sa.String(32),
        type_=sa.String(15),
        existing_nullable=True,
    )
