"""Reset cursor and the reset_failed status for production demo tenants.

Revision ID: control_0039
Revises: control_0038
Create Date: 2026-11-18

The control database and the operational database do not share a transaction.
demo_reset_operation_id and demo_reset_phase are the durable cursor a crashed
reset reads when it resumes. Downgrade drops only these columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0039"
down_revision: str | None = "control_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUS = "demo_status IS NULL OR demo_status IN ('active', 'disabled', 'resetting')"
_NEW_STATUS = "demo_status IS NULL OR demo_status IN ('active', 'disabled', 'resetting', 'reset_failed')"


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column("tenants", sa.Column("demo_reset_operation_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("tenants", sa.Column("demo_reset_phase", sa.String(length=16), nullable=True))
    # SQLite cannot replace a check constraint with ALTER. create_all uses the model.
    if _postgres():
        op.drop_constraint("ck_tenants_demo_status_known", "tenants", type_="check")
        op.create_check_constraint("ck_tenants_demo_status_known", "tenants", _NEW_STATUS)


def downgrade() -> None:
    if _postgres():
        op.drop_constraint("ck_tenants_demo_status_known", "tenants", type_="check")
        op.create_check_constraint("ck_tenants_demo_status_known", "tenants", _OLD_STATUS)
    op.drop_column("tenants", "demo_reset_phase")
    op.drop_column("tenants", "demo_reset_operation_id")
