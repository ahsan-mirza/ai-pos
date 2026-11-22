"""Staff provisioning events. Not a change to the sales queue.

Revision ID: 20261122_0128
Revises: 20261122_0127
Create Date: 2026-11-22

Additive. Not applied to the developer, inventory acceptance, or production databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0128"
down_revision: str | None = "20261122_0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_provisioning_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("safe_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_staff_provisioning_event"),
    )


def downgrade() -> None:
    op.drop_table("staff_provisioning_events")
