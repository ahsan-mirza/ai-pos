"""Webhook registration status on Evolution connections.

Revision ID: 20261103_0096
Revises: 20261101_0095
Create Date: 2026-11-03

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0096"
down_revision: str | None = "20261101_0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reach_connections",
        sa.Column("webhook_status", sa.String(length=24), nullable=False, server_default="pending"),
    )
    op.add_column(
        "reach_connections",
        sa.Column("webhook_registered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reach_connections", "webhook_registered_at")
    op.drop_column("reach_connections", "webhook_status")
