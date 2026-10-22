"""Time clock entries, and the staff / payroll permissions.

Revision ID: 20261020_0035
Revises: 20261020_0034
Create Date: 2026-10-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0035"
down_revision: str | None = "20261020_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
GRANTS = {SUPER_ADMIN_ROLE_ID: ("staff:manage", "payroll:manage"), STORE_MANAGER_ROLE_ID: ("staff:manage",)}


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id, permissions in GRANTS.items():
        if bind.execute(sa.select(roles.c.id).where(roles.c.id == role_id)).first() is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
            )
        }
        missing = [{"role_id": role_id, "permission": item} for item in permissions if item not in held]
        if missing:
            op.bulk_insert(role_permissions, missing)


def upgrade() -> None:
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("clock_in_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("clock_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("break_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(10), nullable=False, server_default="register"),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN", index=True),
        sa.Column("edited_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("edit_note", sa.String(255), nullable=False, server_default=""),
        sa.Column("approved_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("break_minutes >= 0", name="time_entry_break_nonnegative"),
    )
    _grant(op.get_bind())


def downgrade() -> None:
    op.drop_table("time_entries")
    op.execute("DELETE FROM role_permissions WHERE permission IN ('staff:manage', 'payroll:manage')")
