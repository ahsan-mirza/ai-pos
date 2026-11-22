"""Frozen checkout settings captured with a catalogue bootstrap session.

Revision ID: 20261122_0126
Revises: 20261122_0125
Create Date: 2026-11-22

Additive. Not applied to the developer, inventory acceptance, or production databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0126"
down_revision: str | None = "20261122_0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_setting_snapshots",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_bootstrap_setting_snapshots_tenant_id", "bootstrap_setting_snapshots", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_bootstrap_setting_snapshots_tenant_id", table_name="bootstrap_setting_snapshots")
    op.drop_table("bootstrap_setting_snapshots")
