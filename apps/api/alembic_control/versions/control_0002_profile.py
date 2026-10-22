"""Business profile on each tenant, for provisioning and listing.

Revision ID: control_0002
Revises: control_0001
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0002"
down_revision: str | None = "control_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("profile", sa.String(length=32), nullable=False, server_default="electronics_wholesale"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "profile")
