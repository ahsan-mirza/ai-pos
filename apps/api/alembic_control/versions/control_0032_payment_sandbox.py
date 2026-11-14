"""Mark commercial payments as live or sandbox. Sandbox rows cannot settle an invoice.

Revision ID: control_0032
Revises: control_0031
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0032"
down_revision: str | None = "control_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "commercial_payments",
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="live"),
    )
    op.add_column(
        "commercial_payments",
        sa.Column("scenario", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "commercial_payments",
        sa.Column("provider_reference", sa.String(length=80), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("commercial_payments", "provider_reference")
    op.drop_column("commercial_payments", "scenario")
    op.drop_column("commercial_payments", "environment")
