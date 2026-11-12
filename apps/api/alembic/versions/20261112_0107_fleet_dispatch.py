"""Delivery scheduling and manual fleet dispatch on the existing sales order.

Revision ID: 20261112_0107
Revises: 20261112_0106
Create Date: 2026-11-12

Zones, vehicles, drivers, and dispatch plans. A plan does not invoice the order.
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0107"
down_revision: str | None = "20261112_0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
OVERRIDE = "sales:dispatch_override"


def _grant(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("roles") or not inspector.has_table("role_permissions"):
        return
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
    )
    held_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission", sa.String(64)),
        sa.column("tenant_id", sa.Uuid()),
    )
    for role_id in (SUPER_ADMIN_ROLE_ID, STORE_MANAGER_ROLE_ID):
        role = bind.execute(sa.select(roles.c.id, roles.c.tenant_id).where(roles.c.id == role_id)).first()
        if role is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(held_table.c.permission).where(held_table.c.role_id == role_id)
            )
        }
        if OVERRIDE in held:
            continue
        op.bulk_insert(
            held_table,
            [{"role_id": role_id, "permission": OVERRIDE, "tenant_id": role.tenant_id}],
        )


def upgrade() -> None:
    op.create_table(
        "delivery_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_delivery_zones_code"),
    )
    op.create_index("ix_delivery_zones_tenant_id", "delivery_zones", ["tenant_id"])
    op.create_index("ix_delivery_zones_store_id", "delivery_zones", ["store_id"])

    op.create_table(
        "delivery_zone_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_delivery_zone_slots_weekday"),
        sa.ForeignKeyConstraint(["zone_id"], ["delivery_zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delivery_zone_slots_tenant_id", "delivery_zone_slots", ["tenant_id"])
    op.create_index("ix_delivery_zone_slots_zone_id", "delivery_zone_slots", ["zone_id"])

    op.create_table(
        "fleet_vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("registration", sa.String(length=24), nullable=False),
        sa.Column("vehicle_type", sa.String(length=40), nullable=False),
        sa.Column("max_weight_grams", sa.Integer(), nullable=True),
        sa.Column("weight_unit", sa.String(length=8), nullable=False),
        sa.Column("max_volume_cm3", sa.Integer(), nullable=True),
        sa.Column("volume_unit", sa.String(length=8), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("maintenance_status", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "availability IN ('AVAILABLE', 'ON_ROUTE', 'OFF_DUTY')",
            name="ck_fleet_vehicles_availability",
        ),
        sa.CheckConstraint(
            "maintenance_status IN ('NONE', 'DUE', 'IN_SHOP')",
            name="ck_fleet_vehicles_maintenance",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "store_id", "code", name="uq_fleet_vehicles_code"),
    )
    op.create_index("ix_fleet_vehicles_tenant_id", "fleet_vehicles", ["tenant_id"])
    op.create_index("ix_fleet_vehicles_store_id", "fleet_vehicles", ["store_id"])

    op.create_table(
        "driver_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("license_number", sa.String(length=40), nullable=False),
        sa.Column("license_expiry", sa.Date(), nullable=True),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_driver_profiles_user"),
    )
    op.create_index("ix_driver_profiles_tenant_id", "driver_profiles", ["tenant_id"])
    op.create_index("ix_driver_profiles_user_id", "driver_profiles", ["user_id"])
    op.create_index("ix_driver_profiles_store_id", "driver_profiles", ["store_id"])

    op.create_table(
        "dispatch_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("driver_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("capacity_override_by_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')", name="ck_dispatch_plans_status"),
        sa.ForeignKeyConstraint(["capacity_override_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["driver_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["fleet_vehicles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_dispatch_plans_number"),
    )
    op.create_index("ix_dispatch_plans_tenant_id", "dispatch_plans", ["tenant_id"])
    op.create_index("ix_dispatch_plans_store_id", "dispatch_plans", ["store_id"])
    op.create_index("ix_dispatch_plans_service_date", "dispatch_plans", ["service_date"])
    op.create_index("ix_dispatch_plans_vehicle_id", "dispatch_plans", ["vehicle_id"])
    op.create_index("ix_dispatch_plans_driver_user_id", "dispatch_plans", ["driver_user_id"])

    op.create_table(
        "dispatch_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["sales_orders.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["dispatch_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "order_id", name="uq_dispatch_assignments_order"),
    )
    op.create_index("ix_dispatch_assignments_tenant_id", "dispatch_assignments", ["tenant_id"])
    op.create_index("ix_dispatch_assignments_plan_id", "dispatch_assignments", ["plan_id"])
    op.create_index("ix_dispatch_assignments_order_id", "dispatch_assignments", ["order_id"])

    op.add_column(
        "sales_orders",
        sa.Column("scheduling_status", sa.String(length=16), nullable=False, server_default="UNSCHEDULED"),
    )
    op.add_column("sales_orders", sa.Column("promised_on", sa.Date(), nullable=True))
    op.add_column("sales_orders", sa.Column("window_start", sa.Time(), nullable=True))
    op.add_column("sales_orders", sa.Column("window_end", sa.Time(), nullable=True))
    op.add_column("sales_orders", sa.Column("delivery_zone_id", sa.Uuid(), nullable=True))
    op.add_column(
        "sales_orders",
        sa.Column("delivery_instructions", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index("ix_sales_orders_scheduling_status", "sales_orders", ["scheduling_status"])
    op.add_column(
        "business_settings",
        sa.Column("fleet_capacity_policy", sa.String(length=16), nullable=False, server_default="block"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_sales_orders_delivery_zone_id_delivery_zones",
            "sales_orders",
            "delivery_zones",
            ["delivery_zone_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_check_constraint(
            "ck_sales_orders_scheduling_status",
            "sales_orders",
            "scheduling_status IN ('UNSCHEDULED', 'SCHEDULED', 'CANCELLED')",
        )
    _grant(op.get_bind())


def _revoke(bind: sa.engine.Connection) -> None:
    if not sa.inspect(bind).has_table("role_permissions"):
        return
    held = sa.table("role_permissions", sa.column("permission", sa.String(64)))
    bind.execute(sa.delete(held).where(held.c.permission == OVERRIDE))


def downgrade() -> None:
    _revoke(op.get_bind())
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_sales_orders_scheduling_status", "sales_orders", type_="check")
        op.drop_constraint("fk_sales_orders_delivery_zone_id_delivery_zones", "sales_orders", type_="foreignkey")
    op.drop_column("business_settings", "fleet_capacity_policy")
    op.drop_index("ix_sales_orders_scheduling_status", table_name="sales_orders")
    op.drop_column("sales_orders", "delivery_instructions")
    op.drop_column("sales_orders", "delivery_zone_id")
    op.drop_column("sales_orders", "window_end")
    op.drop_column("sales_orders", "window_start")
    op.drop_column("sales_orders", "promised_on")
    op.drop_column("sales_orders", "scheduling_status")
    op.drop_index("ix_dispatch_assignments_order_id", table_name="dispatch_assignments")
    op.drop_index("ix_dispatch_assignments_plan_id", table_name="dispatch_assignments")
    op.drop_index("ix_dispatch_assignments_tenant_id", table_name="dispatch_assignments")
    op.drop_table("dispatch_assignments")
    op.drop_index("ix_dispatch_plans_driver_user_id", table_name="dispatch_plans")
    op.drop_index("ix_dispatch_plans_vehicle_id", table_name="dispatch_plans")
    op.drop_index("ix_dispatch_plans_service_date", table_name="dispatch_plans")
    op.drop_index("ix_dispatch_plans_store_id", table_name="dispatch_plans")
    op.drop_index("ix_dispatch_plans_tenant_id", table_name="dispatch_plans")
    op.drop_table("dispatch_plans")
    op.drop_index("ix_driver_profiles_store_id", table_name="driver_profiles")
    op.drop_index("ix_driver_profiles_user_id", table_name="driver_profiles")
    op.drop_index("ix_driver_profiles_tenant_id", table_name="driver_profiles")
    op.drop_table("driver_profiles")
    op.drop_index("ix_fleet_vehicles_store_id", table_name="fleet_vehicles")
    op.drop_index("ix_fleet_vehicles_tenant_id", table_name="fleet_vehicles")
    op.drop_table("fleet_vehicles")
    op.drop_index("ix_delivery_zone_slots_zone_id", table_name="delivery_zone_slots")
    op.drop_index("ix_delivery_zone_slots_tenant_id", table_name="delivery_zone_slots")
    op.drop_table("delivery_zone_slots")
    op.drop_index("ix_delivery_zones_store_id", table_name="delivery_zones")
    op.drop_index("ix_delivery_zones_tenant_id", table_name="delivery_zones")
    op.drop_table("delivery_zones")
