"""Laundry production floor: stages, batches, machines, inspections, and incidents.

Revision ID: 20261121_0123
Revises: 20261121_0122
Create Date: 2026-11-21

Garments stay work items. This revision does not write stock quantities.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0123"
down_revision: str | None = "20261121_0122"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "laundry_packing_scans",
    "laundry_incidents",
    "laundry_rework_tasks",
    "laundry_inspections",
    "laundry_stage_events",
    "laundry_machine_cycles",
    "laundry_batch_items",
    "laundry_batches",
    "laundry_machines",
    "laundry_sorting_categories",
)


def _policy(table: str) -> str:
    return f"""
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
      OR app_owner_may_bypass('{table}'::regclass)
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
      OR app_owner_may_bypass('{table}'::regclass)
    )
    """


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {_policy(table)}'))  # noqa: TID251


def _drop_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))  # noqa: TID251


def upgrade() -> None:
    op.alter_column("laundry_orders", "operational_status", existing_type=sa.String(20), type_=sa.String(32))
    op.alter_column("laundry_garments", "stage", existing_type=sa.String(20), type_=sa.String(32))
    op.add_column("laundry_garments", sa.Column("workflow_code", sa.String(40), nullable=False, server_default=""))
    op.add_column("laundry_garments", sa.Column("sorting_category", sa.String(40), nullable=False, server_default=""))
    op.add_column("laundry_garments", sa.Column("station", sa.String(40), nullable=False, server_default=""))
    op.add_column(
        "laundry_garments",
        sa.Column(
            "assigned_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_laundry_garments_assignee"),
            nullable=True,
        ),
    )
    op.add_column("laundry_garments", sa.Column("current_batch_id", sa.Uuid(), nullable=True))
    op.add_column("laundry_garments", sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("laundry_garments", sa.Column("rework_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("laundry_garments", sa.Column("qc_result", sa.String(20), nullable=False, server_default=""))
    op.add_column("laundry_garments", sa.Column("hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("laundry_garments", sa.Column("location_label", sa.String(80), nullable=False, server_default=""))
    op.add_column("laundry_garments", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_laundry_garments_current_batch_id", "laundry_garments", ["current_batch_id"])
    op.execute(sa.text("UPDATE laundry_garments SET stage_entered_at = created_at WHERE stage_entered_at IS NULL"))  # noqa: TID251
    if op.get_bind().dialect.name == "postgresql":
        copy_workflow = sa.text(  # noqa: TID251
            "UPDATE laundry_garments AS g SET workflow_code = s.workflow_code "
            "FROM laundry_services AS s WHERE g.service_id = s.id AND g.workflow_code = ''"
        )
        op.execute(copy_workflow)  # noqa: TID251

    op.create_table(
        "laundry_sorting_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("workflow_code", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_sorting_categories"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_sorting_categories_code"),
    )
    op.create_index("ix_laundry_sorting_categories_tenant_id", "laundry_sorting_categories", ["tenant_id"])
    op.create_table(
        "laundry_machines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("machine_type", sa.String(20), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("plant_store_id", sa.Uuid(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("capacity_unit", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("maintenance_note", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity IS NULL OR capacity >= 0", name="ck_laundry_machines_capacity"),
        sa.CheckConstraint("version >= 1", name="ck_laundry_machines_version"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_machines_store"),
        sa.ForeignKeyConstraint(["plant_store_id"], ["stores.id"], name="fk_laundry_machines_plant"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_machines"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_machines_code"),
    )
    op.create_index("ix_laundry_machines_tenant_id", "laundry_machines", ["tenant_id"])
    op.create_index("ix_laundry_machines_store_id", "laundry_machines", ["store_id"])
    op.create_index("ix_laundry_machines_status", "laundry_machines", ["status"])
    op.create_table(
        "laundry_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=True),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("load_weight", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_laundry_batches_version"),
        sa.CheckConstraint("load_weight IS NULL OR load_weight >= 0", name="ck_laundry_batches_load"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_batches_store"),
        sa.ForeignKeyConstraint(["machine_id"], ["laundry_machines.id"], name="fk_laundry_batches_machine"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], name="fk_laundry_batches_operator"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_batches"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_batches_code"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_batches_key"),
    )
    op.create_index("ix_laundry_batches_tenant_id", "laundry_batches", ["tenant_id"])
    op.create_index("ix_laundry_batches_store_id", "laundry_batches", ["store_id"])
    op.create_index("ix_laundry_batches_status", "laundry_batches", ["status"])
    op.create_table(
        "laundry_batch_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=True),
        sa.Column("bag_id", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["laundry_batches.id"], name="fk_laundry_batch_items_batch"),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_batch_items_garment"),
        sa.ForeignKeyConstraint(["bag_id"], ["laundry_bags.id"], name="fk_laundry_batch_items_bag"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_batch_items"),
    )
    op.create_index("ix_laundry_batch_items_tenant_id", "laundry_batch_items", ["tenant_id"])
    op.create_index("ix_laundry_batch_items_batch_id", "laundry_batch_items", ["batch_id"])
    op.create_index("ix_laundry_batch_items_garment_id", "laundry_batch_items", ["garment_id"])
    op.create_table(
        "laundry_machine_cycles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("cycle_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("load_weight", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("issue", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("load_weight IS NULL OR load_weight > 0", name="ck_laundry_machine_cycles_load"),
        sa.ForeignKeyConstraint(["machine_id"], ["laundry_machines.id"], name="fk_laundry_cycles_machine"),
        sa.ForeignKeyConstraint(["batch_id"], ["laundry_batches.id"], name="fk_laundry_cycles_batch"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], name="fk_laundry_cycles_operator"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_machine_cycles"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_machine_cycles_key"),
    )
    op.create_index("ix_laundry_machine_cycles_tenant_id", "laundry_machine_cycles", ["tenant_id"])
    op.create_index("ix_laundry_machine_cycles_machine_id", "laundry_machine_cycles", ["machine_id"])
    op.create_index("ix_laundry_machine_cycles_batch_id", "laundry_machine_cycles", ["batch_id"])
    op.create_index("ix_laundry_machine_cycles_status", "laundry_machine_cycles", ["status"])
    op.create_table(
        "laundry_stage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage", sa.String(32), nullable=False),
        sa.Column("to_stage", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_stage_events_garment"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_stage_events_order"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_laundry_stage_events_actor"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_stage_events_store"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_stage_events"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_stage_events_key"),
    )
    op.create_index("ix_laundry_stage_events_tenant_id", "laundry_stage_events", ["tenant_id"])
    op.create_index("ix_laundry_stage_events_garment_id", "laundry_stage_events", ["garment_id"])
    op.create_index("ix_laundry_stage_events_order_id", "laundry_stage_events", ["order_id"])
    op.create_table(
        "laundry_inspections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_inspections_garment"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_inspections_order"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_laundry_inspections_actor"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_inspections"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_inspections_key"),
    )
    op.create_index("ix_laundry_inspections_tenant_id", "laundry_inspections", ["tenant_id"])
    op.create_index("ix_laundry_inspections_garment_id", "laundry_inspections", ["garment_id"])
    op.create_index("ix_laundry_inspections_order_id", "laundry_inspections", ["order_id"])
    op.create_table(
        "laundry_rework_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("required_stage", sa.String(32), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_rework_garment"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_rework_order"),
        sa.ForeignKeyConstraint(["inspection_id"], ["laundry_inspections.id"], name="fk_laundry_rework_inspection"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], name="fk_laundry_rework_assignee"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_rework_tasks"),
    )
    op.create_index("ix_laundry_rework_tasks_tenant_id", "laundry_rework_tasks", ["tenant_id"])
    op.create_index("ix_laundry_rework_tasks_garment_id", "laundry_rework_tasks", ["garment_id"])
    op.create_index("ix_laundry_rework_tasks_order_id", "laundry_rework_tasks", ["order_id"])
    op.create_index("ix_laundry_rework_tasks_status", "laundry_rework_tasks", ["status"])
    op.create_table(
        "laundry_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("location", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("blocks_ready", sa.Boolean(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("resolution", sa.String(500), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_incidents_order"),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_incidents_garment"),
        sa.ForeignKeyConstraint(["batch_id"], ["laundry_batches.id"], name="fk_laundry_incidents_batch"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_laundry_incidents_actor"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_incidents"),
    )
    op.create_index("ix_laundry_incidents_tenant_id", "laundry_incidents", ["tenant_id"])
    op.create_index("ix_laundry_incidents_order_id", "laundry_incidents", ["order_id"])
    op.create_index("ix_laundry_incidents_garment_id", "laundry_incidents", ["garment_id"])
    op.create_index("ix_laundry_incidents_status", "laundry_incidents", ["status"])
    op.create_table(
        "laundry_packing_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=False),
        sa.Column("bag_code", sa.String(40), nullable=False),
        sa.Column("rework_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_packing_order"),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_packing_garment"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_laundry_packing_actor"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_packing_scans"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_packing_scans_key"),
        sa.UniqueConstraint("tenant_id", "garment_id", "rework_count", name="uq_laundry_packing_scans_generation"),
    )
    op.create_index("ix_laundry_packing_scans_tenant_id", "laundry_packing_scans", ["tenant_id"])
    op.create_index("ix_laundry_packing_scans_order_id", "laundry_packing_scans", ["order_id"])
    op.create_index("ix_laundry_packing_scans_garment_id", "laundry_packing_scans", ["garment_id"])
    for table in reversed(TABLES):
        _rls(table)


def downgrade() -> None:
    for table in TABLES:
        _drop_rls(table)
        op.drop_table(table)
    op.drop_index("ix_laundry_garments_current_batch_id", table_name="laundry_garments")
    for column in (
        "version",
        "location_label",
        "hold",
        "qc_result",
        "rework_count",
        "stage_entered_at",
        "current_batch_id",
        "assigned_user_id",
        "station",
        "sorting_category",
        "workflow_code",
    ):
        op.drop_column("laundry_garments", column)
    op.alter_column("laundry_garments", "stage", existing_type=sa.String(32), type_=sa.String(20))
    op.alter_column("laundry_orders", "operational_status", existing_type=sa.String(32), type_=sa.String(20))
