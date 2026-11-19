"""Explicit pharmacist authorization for lot release. Not a licence record.

Revision ID: 20261118_0117
Revises: 20261118_0116
Create Date: 2026-11-19

No stock quantities change. Existing layers are not marked released.
Grocery rows are not updated. A role name does not insert an authorization.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0117"
down_revision: str | None = "20261118_0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def _drop_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "pharmacist_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_id", sa.Uuid(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("user_id <> granted_by_id", name="ck_pharmacist_authorizations_not_self"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_by_id IS NOT NULL",
            name="ck_pharmacist_authorizations_revoker",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_pharmacist_authorizations_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["users.id"],
            name="fk_pharmacist_authorizations_granted_by_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"],
            ["users.id"],
            name="fk_pharmacist_authorizations_revoked_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacist_authorizations"),
    )
    op.create_index("ix_pharmacist_authorizations_tenant_id", "pharmacist_authorizations", ["tenant_id"])
    op.create_index(
        "uq_pharmacist_authorizations_active",
        "pharmacist_authorizations",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    _rls("pharmacist_authorizations")


def downgrade() -> None:
    _drop_rls("pharmacist_authorizations")
    op.drop_index("uq_pharmacist_authorizations_active", table_name="pharmacist_authorizations")
    op.drop_index("ix_pharmacist_authorizations_tenant_id", table_name="pharmacist_authorizations")
    op.drop_table("pharmacist_authorizations")
