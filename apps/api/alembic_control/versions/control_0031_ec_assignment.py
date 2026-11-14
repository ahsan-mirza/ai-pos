"""Branch and register assignment on a delivered EC machine.

Revision ID: control_0031
Revises: control_0030
Create Date: 2026-11-14

Adds assignment fields only. Existing orders, serials, and invoices are left in place.
Downgrade drops the new columns and the assignment history stored in them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0031"
down_revision: str | None = "control_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("hardware_assignments", sa.Column("label", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("hardware_assignments", sa.Column("register_id", sa.Uuid(), nullable=True))
    op.add_column("hardware_assignments", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hardware_assignments", sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "hardware_assignments",
        sa.Column("assignment_history", sa.JSON(), nullable=True),
    )
    op.create_index("ix_hardware_assignments_register_id", "hardware_assignments", ["register_id"])


def downgrade() -> None:
    op.drop_index("ix_hardware_assignments_register_id", table_name="hardware_assignments")
    op.drop_column("hardware_assignments", "assignment_history")
    op.drop_column("hardware_assignments", "assigned_by_user_id")
    op.drop_column("hardware_assignments", "assigned_at")
    op.drop_column("hardware_assignments", "register_id")
    op.drop_column("hardware_assignments", "label")
