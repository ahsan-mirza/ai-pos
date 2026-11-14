"""Plan-change requests and their status history.

Revision ID: control_0034
Revises: control_0033
Create Date: 2026-11-14

Records a tenant's request to change plan. Invoices, bank transfers, payments,
and subscription activation stay on the existing commercial tables. This migration
does not copy or rewrite those rows.

Downgrade drops only the two new tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0034"
down_revision: str | None = "control_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

_OPEN = "status IN ('quoted', 'pending_payment', 'payment_submitted')"
_STATUSES = (
    "status IN ('quoted', 'pending_payment', 'payment_submitted', "
    "'completed', 'cancelled', 'rejected', 'expired', 'failed')"
)


def upgrade() -> None:
    op.create_table(
        "subscription_change_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("reference", sa.String(24), nullable=False),
        sa.Column("current_plan_code", sa.String(32), nullable=False),
        sa.Column("requested_plan_code", sa.String(32), nullable=False),
        sa.Column("requested_cycle_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quote_snapshot", sa.JSON(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(as_uuid=True), sa.ForeignKey("billing_invoices.id"), nullable=True),
        sa.Column("requested_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issuing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_STATUSES, name="ck_subscription_changes_status"),
    )
    op.create_index("ix_subscription_changes_tenant", "subscription_change_requests", ["tenant_id"])
    op.create_index("ix_subscription_changes_invoice", "subscription_change_requests", ["invoice_id"])
    op.create_index(
        "ix_subscription_changes_tenant_created",
        "subscription_change_requests",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "uq_subscription_changes_one_open",
        "subscription_change_requests",
        ["tenant_id"],
        unique=True,
        sqlite_where=sa.text(_OPEN),
        postgresql_where=sa.text(_OPEN),
    )
    op.create_table(
        "subscription_change_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("subscription_change_requests.id"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscription_change_events_request_id", "subscription_change_events", ["request_id"])
    op.create_index(
        "ix_subscription_change_events_request",
        "subscription_change_events",
        ["request_id", "created_at"],
    )
    op.create_index(
        "uq_subscription_change_events_one_completion",
        "subscription_change_events",
        ["request_id"],
        unique=True,
        sqlite_where=sa.text("status = 'completed'"),
        postgresql_where=sa.text("status = 'completed'"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION subscription_change_same_tenant() RETURNS trigger AS $$
            BEGIN
              IF NEW.invoice_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM billing_invoices WHERE id = NEW.invoice_id AND tenant_id = NEW.tenant_id
              ) THEN
                RAISE EXCEPTION 'cross-tenant invoice';
              END IF;
              IF NEW.subscription_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM subscriptions WHERE id = NEW.subscription_id AND tenant_id = NEW.tenant_id
              ) THEN
                RAISE EXCEPTION 'cross-tenant subscription';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER subscription_change_same_tenant
            BEFORE INSERT OR UPDATE ON subscription_change_requests
            FOR EACH ROW EXECUTE PROCEDURE subscription_change_same_tenant()
            """
        )
    else:
        check = """
            WHEN (
              NEW.invoice_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM billing_invoices WHERE id = NEW.invoice_id AND tenant_id = NEW.tenant_id
              )
            ) OR (
              NEW.subscription_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM subscriptions WHERE id = NEW.subscription_id AND tenant_id = NEW.tenant_id
              )
            )
            BEGIN
              SELECT RAISE(ABORT, 'cross-tenant reference');
            END
        """
        op.execute(
            "CREATE TRIGGER subscription_change_same_tenant_insert "
            "BEFORE INSERT ON subscription_change_requests FOR EACH ROW " + check
        )
        op.execute(
            "CREATE TRIGGER subscription_change_same_tenant_update "
            "BEFORE UPDATE ON subscription_change_requests FOR EACH ROW " + check
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS subscription_change_same_tenant ON subscription_change_requests")
        op.execute("DROP FUNCTION IF EXISTS subscription_change_same_tenant()")
    else:
        op.execute("DROP TRIGGER IF EXISTS subscription_change_same_tenant_update")
        op.execute("DROP TRIGGER IF EXISTS subscription_change_same_tenant_insert")
    op.drop_index("uq_subscription_change_events_one_completion", table_name="subscription_change_events")
    op.drop_index("ix_subscription_change_events_request", table_name="subscription_change_events")
    op.drop_index("ix_subscription_change_events_request_id", table_name="subscription_change_events")
    op.drop_table("subscription_change_events")
    op.drop_index("uq_subscription_changes_one_open", table_name="subscription_change_requests")
    op.drop_index("ix_subscription_changes_tenant_created", table_name="subscription_change_requests")
    op.drop_index("ix_subscription_changes_invoice", table_name="subscription_change_requests")
    op.drop_index("ix_subscription_changes_tenant", table_name="subscription_change_requests")
    op.drop_table("subscription_change_requests")
