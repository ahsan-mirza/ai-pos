"""Users, roles, permissions, and cashier attribution.

Revision ID: 20261019_0002
Revises: 20261019_0001
Create Date: 2026-10-19
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0002"
down_revision: str | None = "20261019_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of the system roles at this revision. Later revisions own later changes.
ALL = [
    "users:create",
    "users:read",
    "users:update",
    "users:delete",
    "roles:manage",
    "pos:access",
    "pos:discount",
    "pos:refund",
    "pos:drawer_override",
    "portal:access",
    "portal:reports_read",
    "portal:inventory_manage",
    "repairs:create",
    "repairs:update",
]
CASHIER_ROLE_ID = "00000000-0000-4000-8000-0000000000a3"
SYSTEM_ROLES = [
    ("00000000-0000-4000-8000-0000000000a1", "Super Admin", "Unrestricted access across every store.", ALL),
    (
        "00000000-0000-4000-8000-0000000000a2",
        "Store Manager",
        "Runs one store: staff, registers, inventory, and reports.",
        [item for item in ALL if item not in {"users:delete", "roles:manage"}],
    ),
    (CASHIER_ROLE_ID, "Cashier", "Sells at the register and opens repair tickets.", ["pos:access", "repairs:create"]),
    (
        "00000000-0000-4000-8000-0000000000a4",
        "Technician",
        "Works repair tickets.",
        ["pos:access", "repairs:create", "repairs:update"],
    ),
]
UUID_PATTERN = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission", name="pk_role_permissions"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("hashed_pin", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("role_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("has_pos_access", sa.Boolean(), nullable=False),
        sa.Column("has_portal_access", sa.Boolean(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_users_store_id_stores"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_users_role_id_roles"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_store_id", "users", ["store_id"])
    op.create_index("ix_users_role_id", "users", ["role_id"])

    now = datetime.now(UTC)
    op.bulk_insert(
        roles,
        [
            {
                "id": role_id,
                "name": name,
                "description": description,
                "is_system": True,
                "created_at": now,
                "updated_at": now,
            }
            for role_id, name, description, _ in SYSTEM_ROLES
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_id, "permission": permission}
            for role_id, _, _, permissions in SYSTEM_ROLES
            for permission in permissions
        ],
    )

    # Existing sales carry free-text cashier ids. Give each one an inactive placeholder user so the
    # new foreign key holds without inventing credentials.
    op.execute(
        sa.text(
            "UPDATE sales SET cashier_id = md5(cashier_id)::uuid::text WHERE cashier_id !~ :pattern"
        ).bindparams(pattern=UUID_PATTERN)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO users (
                id, username, email, full_name, hashed_password, hashed_pin, is_active, store_id, role_id,
                has_pos_access, has_portal_access, failed_login_attempts, locked_until, token_version,
                last_login_at, created_at, updated_at
            )
            SELECT DISTINCT
                s.cashier_id::uuid,
                'legacy-' || left(md5(s.cashier_id), 12),
                'legacy-' || left(md5(s.cashier_id), 12) || '@legacy.invalid',
                'Legacy cashier',
                CAST(NULL AS varchar), CAST(NULL AS varchar), false, CAST(NULL AS uuid), CAST(:role_id AS uuid),
                false, false, 0, CAST(NULL AS timestamptz), 0, CAST(NULL AS timestamptz), now(), now()
            FROM sales s
            """
        ).bindparams(role_id=CASHIER_ROLE_ID)
    )
    op.alter_column(
        "sales",
        "cashier_id",
        existing_type=sa.String(length=64),
        type_=sa.Uuid(as_uuid=True),
        postgresql_using="cashier_id::uuid",
        existing_nullable=False,
    )
    op.create_foreign_key("fk_sales_cashier_id_users", "sales", "users", ["cashier_id"], ["id"])
    op.create_index("ix_sales_cashier_id", "sales", ["cashier_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_cashier_id", table_name="sales")
    op.drop_constraint("fk_sales_cashier_id_users", "sales", type_="foreignkey")
    op.alter_column(
        "sales",
        "cashier_id",
        existing_type=sa.Uuid(as_uuid=True),
        type_=sa.String(length=64),
        postgresql_using="cashier_id::text",
        existing_nullable=False,
    )
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
