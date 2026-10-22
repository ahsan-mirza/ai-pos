"""Business-wide settings (currency) and the settings:manage permission.

Revision ID: 20261019_0006
Revises: 20261019_0005
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0006"
down_revision: str | None = "20261019_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTINGS_ID = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


def upgrade() -> None:
    settings = op.create_table(
        "business_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_business_settings_updated_by_id_users"),
    )
    bind = op.get_bind()
    current = bind.execute(sa.text("SELECT currency FROM stores ORDER BY created_at LIMIT 1")).scalar()
    now = datetime.now(UTC)
    op.bulk_insert(
        settings,
        [
            {
                "id": SETTINGS_ID,
                "currency": current or "USD",
                "updated_by_id": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid(as_uuid=True)),
        sa.column("permission", sa.String(length=64)),
    )
    has_role = bind.execute(sa.select(roles.c.id).where(roles.c.id == SUPER_ADMIN_ROLE_ID)).first() is not None
    granted = bind.execute(
        sa.select(role_permissions.c.role_id).where(
            role_permissions.c.role_id == SUPER_ADMIN_ROLE_ID,
            role_permissions.c.permission == "settings:manage",
        )
    ).first()
    if has_role and granted is None:
        op.bulk_insert(role_permissions, [{"role_id": SUPER_ADMIN_ROLE_ID, "permission": "settings:manage"}])


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission = 'settings:manage'")
    op.drop_table("business_settings")
