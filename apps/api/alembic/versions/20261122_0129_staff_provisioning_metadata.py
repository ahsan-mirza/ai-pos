"""Staff provisioning metadata. Not a change to the sales queue.

Revision ID: 20261122_0129
Revises: 20261122_0128
Create Date: 2026-11-22

Additive. Not applied to the developer, inventory acceptance, or production databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0129"
down_revision: str | None = "20261122_0128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("staff_provisioning_events", sa.Column("origin_terminal_id", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("staff_provisioning_events", sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("staff_provisioning_events", sa.Column("base_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("staff_provisioning_events", "base_version")
    op.drop_column("staff_provisioning_events", "schema_version")
    op.drop_column("staff_provisioning_events", "origin_terminal_id")
