"""Record an approved commercial price revision.

Revision ID: control_0036
Revises: control_0035
Create Date: 2026-11-14

The table records that a price revision was applied. The prices themselves
live in the commercial manifest and are written by the application once.
This migration does not change plans, add-ons, subscriptions, or invoices.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0036"
down_revision: str | None = "control_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commercial_catalog_releases",
        sa.Column("revision", sa.String(length=64), primary_key=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("commercial_catalog_releases")
