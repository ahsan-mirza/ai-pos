"""Two-person pharmacist appointment and governance officers.

Revision ID: 20261118_0118
Revises: 20261118_0117
Create Date: 2026-11-19

Existing pharmacist rows, if any, stay active and are marked LEGACY.
A pending row is not created here. No stock quantity changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0118"
down_revision: str | None = "20261118_0117"
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
    op.add_column("pharmacist_authorizations", sa.Column("requested_by_id", sa.Uuid(), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("approved_by_id", sa.Uuid(), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("rejected_by_id", sa.Uuid(), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("status", sa.String(length=16), nullable=True))
    op.add_column("pharmacist_authorizations", sa.Column("approval_basis", sa.String(length=16), nullable=True))
    op.execute(
        sa.text(
            "UPDATE pharmacist_authorizations SET "
            "requested_by_id = granted_by_id, "
            "approved_by_id = granted_by_id, "
            "requested_at = granted_at, "
            "approved_at = granted_at, "
            "status = CASE WHEN revoked_at IS NULL THEN 'ACTIVE' ELSE 'REVOKED' END, "
            "approval_basis = 'LEGACY'"
        )
    )
    op.alter_column("pharmacist_authorizations", "requested_by_id", nullable=False)
    op.alter_column("pharmacist_authorizations", "requested_at", nullable=False)
    op.alter_column("pharmacist_authorizations", "status", nullable=False)
    op.alter_column("pharmacist_authorizations", "approval_basis", nullable=False)
    op.create_foreign_key(
        "fk_pharmacist_authorizations_requested_by_id_users",
        "pharmacist_authorizations",
        "users",
        ["requested_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_pharmacist_authorizations_approved_by_id_users",
        "pharmacist_authorizations",
        "users",
        ["approved_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_pharmacist_authorizations_rejected_by_id_users",
        "pharmacist_authorizations",
        "users",
        ["rejected_by_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_not_requester",
        "pharmacist_authorizations",
        "user_id <> requested_by_id",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_approver_not_target",
        "pharmacist_authorizations",
        "approved_by_id IS NULL OR approved_by_id <> user_id",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_two_person",
        "pharmacist_authorizations",
        "approved_by_id IS NULL OR approved_by_id <> requested_by_id OR approval_basis = 'LEGACY'",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_status",
        "pharmacist_authorizations",
        "status IN ('PENDING', 'ACTIVE', 'REJECTED', 'REVOKED')",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_basis",
        "pharmacist_authorizations",
        "approval_basis IN ('TWO_PERSON', 'LEGACY')",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_active_approver",
        "pharmacist_authorizations",
        "status <> 'ACTIVE' OR approved_by_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_pending_open",
        "pharmacist_authorizations",
        "status <> 'PENDING' OR approved_by_id IS NULL",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_revoked",
        "pharmacist_authorizations",
        "status <> 'REVOKED' OR (revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_pharmacist_authorizations_rejected",
        "pharmacist_authorizations",
        "status <> 'REJECTED' OR (rejected_at IS NOT NULL AND rejected_by_id IS NOT NULL)",
    )
    op.drop_index("uq_pharmacist_authorizations_active", table_name="pharmacist_authorizations")
    op.create_index(
        "uq_pharmacist_authorizations_active",
        "pharmacist_authorizations",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
        sqlite_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )
    op.create_table(
        "pharmacy_governance_officers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("user_id <> requested_by_id", name="ck_pharmacy_governance_officers_not_requester"),
        sa.CheckConstraint(
            "approved_by_id IS NULL OR (approved_by_id <> user_id AND approved_by_id <> requested_by_id)",
            name="ck_pharmacy_governance_officers_two_person",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'REJECTED', 'REVOKED')",
            name="ck_pharmacy_governance_officers_status",
        ),
        sa.CheckConstraint(
            "status <> 'ACTIVE' OR approved_by_id IS NOT NULL",
            name="ck_pharmacy_governance_officers_active_approver",
        ),
        sa.CheckConstraint(
            "status <> 'PENDING' OR approved_by_id IS NULL",
            name="ck_pharmacy_governance_officers_pending_open",
        ),
        sa.CheckConstraint(
            "status <> 'REVOKED' OR (revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL)",
            name="ck_pharmacy_governance_officers_revoked",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pharmacy_governance_officers_user_id_users"),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["users.id"], name="fk_pharmacy_governance_officers_requested_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"], ["users.id"], name="fk_pharmacy_governance_officers_approved_by_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"], ["users.id"], name="fk_pharmacy_governance_officers_revoked_by_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacy_governance_officers"),
    )
    op.create_index("ix_pharmacy_governance_officers_tenant_id", "pharmacy_governance_officers", ["tenant_id"])
    op.create_index(
        "uq_pharmacy_governance_officers_open",
        "pharmacy_governance_officers",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
        sqlite_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )
    _rls("pharmacy_governance_officers")


def downgrade() -> None:
    # A pending or rejected row must not become a release authority when status disappears.
    op.execute(
        sa.text(
            "UPDATE pharmacist_authorizations SET "
            "revoked_at = CURRENT_TIMESTAMP, "
            "revoked_by_id = COALESCE(rejected_by_id, requested_by_id), "
            "revocation_reason = COALESCE(revocation_reason, 'Closed on downgrade before approval') "
            "WHERE status IN ('PENDING', 'REJECTED') AND revoked_at IS NULL"
        )
    )
    _drop_rls("pharmacy_governance_officers")
    op.drop_index("uq_pharmacy_governance_officers_open", table_name="pharmacy_governance_officers")
    op.drop_index("ix_pharmacy_governance_officers_tenant_id", table_name="pharmacy_governance_officers")
    op.drop_table("pharmacy_governance_officers")
    op.drop_index("uq_pharmacist_authorizations_active", table_name="pharmacist_authorizations")
    op.create_index(
        "uq_pharmacist_authorizations_active",
        "pharmacist_authorizations",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    for name in (
        "ck_pharmacist_authorizations_rejected",
        "ck_pharmacist_authorizations_revoked",
        "ck_pharmacist_authorizations_pending_open",
        "ck_pharmacist_authorizations_active_approver",
        "ck_pharmacist_authorizations_basis",
        "ck_pharmacist_authorizations_status",
        "ck_pharmacist_authorizations_two_person",
        "ck_pharmacist_authorizations_approver_not_target",
        "ck_pharmacist_authorizations_not_requester",
    ):
        op.drop_constraint(name, "pharmacist_authorizations", type_="check")
    op.drop_constraint("fk_pharmacist_authorizations_rejected_by_id_users", "pharmacist_authorizations", type_="foreignkey")
    op.drop_constraint("fk_pharmacist_authorizations_approved_by_id_users", "pharmacist_authorizations", type_="foreignkey")
    op.drop_constraint("fk_pharmacist_authorizations_requested_by_id_users", "pharmacist_authorizations", type_="foreignkey")
    for column in (
        "approval_basis",
        "status",
        "rejection_reason",
        "rejected_at",
        "approved_at",
        "requested_at",
        "rejected_by_id",
        "approved_by_id",
        "requested_by_id",
    ):
        op.drop_column("pharmacist_authorizations", column)
