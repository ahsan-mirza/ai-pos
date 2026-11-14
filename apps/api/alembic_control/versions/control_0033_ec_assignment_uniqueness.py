"""One active register and one live serial per EC assignment.

Revision ID: control_0033
Revises: control_0032
Create Date: 2026-11-14

Application checks can both pass under two concurrent requests. These partial
indexes reject the second writer. Blank serials and returned units are excluded.
Downgrade drops the indexes and leaves the assignment rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "control_0033"
down_revision: str | None = "control_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

_REGISTER = (
    "CREATE UNIQUE INDEX uq_hardware_assignments_active_register "
    "ON hardware_assignments (register_id) "
    "WHERE register_id IS NOT NULL AND status = 'active'"
)
_SERIAL = (
    "CREATE UNIQUE INDEX uq_hardware_assignments_active_serial "
    "ON hardware_assignments (serial) "
    "WHERE serial <> '' AND status <> 'returned'"
)


def upgrade() -> None:
    op.execute(_REGISTER)
    op.execute(_SERIAL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_hardware_assignments_active_serial")
    op.execute("DROP INDEX IF EXISTS uq_hardware_assignments_active_register")
