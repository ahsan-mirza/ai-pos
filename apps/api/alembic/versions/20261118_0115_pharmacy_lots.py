"""Pharmacy lot metadata on existing cost layers, plus an append-only event history.

Revision ID: 20261118_0115
Revises: 20261118_0114
Create Date: 2026-11-19

Existing batch_items rows are not updated. Grocery batch numbers are not copied
into manufacturer_lot. Quantities are not touched.

recall_id is a nullable uuid without a foreign key. pharmacy_recalls is a later
stage, and this revision does not invent that table. The check still requires
recall_id when lot_status is RECALLED.

Referential actions the architecture report left unspecified:
- source_batch_item_id and released_by_id use ON DELETE SET NULL
- batch_item_events.batch_item_id uses ON DELETE CASCADE
- batch_item_events.user_id uses ON DELETE SET NULL
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0115"
down_revision: str | None = "20261118_0114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)

_STATUSES = "'RELEASED', 'UNRELEASED', 'QUARANTINED', 'RECALLED', 'DAMAGED', 'SUPPLIER_RETURN'"
_ACTIONS = (
    "'RECEIVED', 'RELEASED', 'QUARANTINED', 'RECALLED', 'DAMAGED', "
    "'TRANSFER_OUT', 'TRANSFER_IN', 'RETURNED', 'SUPPLIER_RETURN'"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.add_column("batch_items", sa.Column("manufacturer_lot", sa.String(length=64), nullable=True))
    op.add_column("batch_items", sa.Column("manufactured_on", sa.Date(), nullable=True))
    op.add_column("batch_items", sa.Column("lot_status", sa.String(length=16), nullable=True))
    op.add_column("batch_items", sa.Column("quarantine_reason", sa.Text(), nullable=True))
    op.add_column("batch_items", sa.Column("recall_id", sa.Uuid(), nullable=True))
    op.add_column("batch_items", sa.Column("recall_reason", sa.Text(), nullable=True))
    op.add_column("batch_items", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("batch_items", sa.Column("released_by_id", sa.Uuid(), nullable=True))
    op.add_column("batch_items", sa.Column("source_batch_item_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_batch_items_manufacturer_lot_length",
        "batch_items",
        "manufacturer_lot IS NULL OR (length(manufacturer_lot) >= 1 AND length(manufacturer_lot) <= 64)",
    )
    op.create_check_constraint(
        "ck_batch_items_manufactured_before_expiry",
        "batch_items",
        "manufactured_on IS NULL OR expiry_date IS NULL OR manufactured_on <= expiry_date",
    )
    op.create_check_constraint(
        "ck_batch_items_lot_status",
        "batch_items",
        f"lot_status IS NULL OR lot_status IN ({_STATUSES})",
    )
    op.create_check_constraint(
        "ck_batch_items_recall_id",
        "batch_items",
        "lot_status IS NULL OR lot_status <> 'RECALLED' OR recall_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_batch_items_released_by_id_users",
        "batch_items",
        "users",
        ["released_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_batch_items_source_batch_item_id_batch_items",
        "batch_items",
        "batch_items",
        ["source_batch_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_batch_items_manufacturer_lot",
        "batch_items",
        ["tenant_id", "product_id", "manufacturer_lot"],
    )
    op.create_index(
        "ix_batch_items_lot_draw",
        "batch_items",
        ["tenant_id", "product_id", "store_id", "lot_status", "expiry_date", "quantity_remaining"],
    )
    op.create_table(
        "batch_item_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_item_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("recall_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"action IN ({_ACTIONS})", name="ck_batch_item_events_action"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})",
            name="ck_batch_item_events_from_status",
        ),
        sa.CheckConstraint(
            f"to_status IS NULL OR to_status IN ({_STATUSES})",
            name="ck_batch_item_events_to_status",
        ),
        sa.ForeignKeyConstraint(
            ["batch_item_id"],
            ["batch_items.id"],
            name="fk_batch_item_events_batch_item_id_batch_items",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_batch_item_events_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batch_item_events"),
    )
    op.create_index("ix_batch_item_events_tenant_id", "batch_item_events", ["tenant_id"])
    op.create_index("ix_batch_item_events_item", "batch_item_events", ["tenant_id", "batch_item_id"])
    _rls("batch_item_events")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION batch_item_events_append_only() RETURNS trigger AS $$
                BEGIN
                  RAISE EXCEPTION 'batch_item_events is append-only';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER batch_item_events_append_only
                BEFORE UPDATE OR DELETE ON batch_item_events
                FOR EACH ROW EXECUTE FUNCTION batch_item_events_append_only()
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS batch_item_events_append_only ON batch_item_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS batch_item_events_append_only()"))
        op.execute(sa.text('DROP POLICY IF EXISTS tenant_isolation ON "batch_item_events"'))
        op.execute(sa.text('ALTER TABLE "batch_item_events" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "batch_item_events" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_batch_item_events_item", table_name="batch_item_events")
    op.drop_index("ix_batch_item_events_tenant_id", table_name="batch_item_events")
    op.drop_table("batch_item_events")
    op.drop_index("ix_batch_items_lot_draw", table_name="batch_items")
    op.drop_index("ix_batch_items_manufacturer_lot", table_name="batch_items")
    op.drop_constraint("fk_batch_items_source_batch_item_id_batch_items", "batch_items", type_="foreignkey")
    op.drop_constraint("fk_batch_items_released_by_id_users", "batch_items", type_="foreignkey")
    op.drop_constraint("ck_batch_items_recall_id", "batch_items", type_="check")
    op.drop_constraint("ck_batch_items_lot_status", "batch_items", type_="check")
    op.drop_constraint("ck_batch_items_manufactured_before_expiry", "batch_items", type_="check")
    op.drop_constraint("ck_batch_items_manufacturer_lot_length", "batch_items", type_="check")
    op.drop_column("batch_items", "source_batch_item_id")
    op.drop_column("batch_items", "released_by_id")
    op.drop_column("batch_items", "released_at")
    op.drop_column("batch_items", "recall_reason")
    op.drop_column("batch_items", "recall_id")
    op.drop_column("batch_items", "quarantine_reason")
    op.drop_column("batch_items", "lot_status")
    op.drop_column("batch_items", "manufactured_on")
    op.drop_column("batch_items", "manufacturer_lot")
