"""Paid add-on modules on the store, and the revision each register has applied.

Revision ID: 20261028_0079
Revises: 20261027_0078
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0079"
down_revision: str | None = "20261027_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("purchased_capabilities", sa.JSON(), nullable=True))
    op.add_column("business_settings", sa.Column("entitlement_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("entitlement_revision", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("entitlement_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "entitlement_synced_at")
    op.drop_column("devices", "entitlement_revision")
    op.drop_column("business_settings", "entitlement_until")
    op.drop_column("business_settings", "purchased_capabilities")
