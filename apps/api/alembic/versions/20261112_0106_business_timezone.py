"""Tenant reporting timezone. Stored instants stay UTC.

Revision ID: 20261112_0106
Revises: 20261112_0105
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0106"
down_revision: str | None = "20261112_0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_settings",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Dubai"),
    )


def downgrade() -> None:
    op.drop_column("business_settings", "timezone")
