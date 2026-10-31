"""Restaurant and cafe table reservations, seating sessions, and append-only table history.

Revision ID: 20261031_0094
Revises: 20261031_0093
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261031_0094"
down_revision: str | None = "20261031_0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGER = (
    "reservations:view",
    "reservations:create",
    "reservations:update",
    "reservations:confirm",
    "reservations:cancel",
    "reservations:seat",
    "reservations:mark_no_show",
    "reservations:view_history",
    "reservations:manage_settings",
    "table_history:view",
)
CASHIER = ("reservations:view", "reservations:create", "reservations:seat")
ADMIN = MANAGER + ("reservations:view_all_branches", "table_history:view_all_branches")
GRANTS = {"Super Admin": ADMIN, "Store Manager": MANAGER, "Cashier": CASHIER}


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("tenant_id", sa.Uuid()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission", sa.String()),
        sa.column("tenant_id", sa.Uuid()),
    )
    for name, permissions in GRANTS.items():
        found = bind.execute(
            sa.select(roles.c.id, roles.c.tenant_id).where(roles.c.name == name, roles.c.is_system.is_(True))
        ).all()
        for role_id, tenant_id in found:
            held = {
                row[0]
                for row in bind.execute(
                    sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
                )
            }
            missing = [
                {"role_id": role_id, "permission": item, "tenant_id": tenant_id}
                for item in permissions
                if item not in held
            ]
            if missing:
                op.bulk_insert(role_permissions, missing)


def upgrade() -> None:
    op.create_table(
        "reservation_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("grace_minutes", sa.Integer(), nullable=False),
        sa.Column("min_notice_minutes", sa.Integer(), nullable=False),
        sa.Column("max_advance_days", sa.Integer(), nullable=False),
        sa.Column("max_guests", sa.Integer(), nullable=False),
        sa.Column("allow_same_day", sa.Boolean(), nullable=False),
        sa.Column("allow_walk_in", sa.Boolean(), nullable=False),
        sa.Column("allow_guest_profiles", sa.Boolean(), nullable=False),
        sa.Column("require_phone", sa.Boolean(), nullable=False),
        sa.Column("confirm_on_create", sa.Boolean(), nullable=False),
        sa.Column("notify_confirmation", sa.Boolean(), nullable=False),
        sa.Column("notify_updates", sa.Boolean(), nullable=False),
        sa.Column("notify_cancellation", sa.Boolean(), nullable=False),
        sa.Column("notify_reminder", sa.Boolean(), nullable=False),
        sa.Column("open_time", sa.String(length=5), nullable=False),
        sa.Column("close_time", sa.String(length=5), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "store_id", name="uq_reservation_settings_store"),
        sa.CheckConstraint("duration_minutes >= 15", name="ck_reservation_settings_duration"),
        sa.CheckConstraint("buffer_minutes >= 0", name="ck_reservation_settings_buffer"),
        sa.CheckConstraint("grace_minutes >= 0", name="ck_reservation_settings_grace"),
    )
    op.create_index("ix_reservation_settings_tenant_id", "reservation_settings", ["tenant_id"])
    op.create_index("ix_reservation_settings_store_id", "reservation_settings", ["store_id"])
    op.create_table(
        "reservations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=True),
        sa.Column("reservation_number", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guest_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("occasion", sa.String(length=80), nullable=True),
        sa.Column("special_requests", sa.String(length=500), nullable=True),
        sa.Column("internal_notes", sa.String(length=500), nullable=True),
        sa.Column("assigned_employee_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=32), nullable=True),
        sa.Column("cancellation_detail", sa.String(length=500), nullable=True),
        sa.Column("customer_notified", sa.Boolean(), nullable=False),
        sa.Column("notification_status", sa.String(length=16), nullable=False),
        sa.Column("notification_detail", sa.String(length=300), nullable=True),
        sa.Column("notification_message_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["table_id"], ["dining_tables.id"]),
        sa.ForeignKeyConstraint(["assigned_employee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["notification_message_id"], ["outbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "store_id", "reservation_number", name="uq_reservations_number"),
        sa.CheckConstraint("guest_count >= 1", name="ck_reservations_guests"),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','arrived','seated','completed','cancelled','no_show','rejected')",
            name="ck_reservations_status",
        ),
    )
    op.create_index("ix_reservations_tenant_id", "reservations", ["tenant_id"])
    op.create_index("ix_reservations_store_id", "reservations", ["store_id"])
    op.create_index("ix_reservations_status", "reservations", ["status"])
    op.create_index("ix_reservations_table_window", "reservations", ["table_id", "status", "starts_at"])
    op.create_index("ix_reservations_store_start", "reservations", ["store_id", "starts_at"])
    op.create_table(
        "reservation_status_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reservation_status_events_tenant_id", "reservation_status_events", ["tenant_id"])
    op.create_index(
        "ix_reservation_status_events_reservation",
        "reservation_status_events",
        ["reservation_id", "created_at"],
    )
    op.create_table(
        "table_seating_sessions",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=True),
        sa.Column("guest_count", sa.Integer(), nullable=False),
        sa.Column("assigned_employee_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["table_id"], ["dining_tables.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"]),
        sa.ForeignKeyConstraint(["assigned_employee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("guest_count >= 1", name="ck_seating_sessions_guests"),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_seating_sessions_status"),
    )
    op.create_index("ix_table_seating_sessions_tenant_id", "table_seating_sessions", ["tenant_id"])
    op.create_index("ix_table_seating_sessions_store_id", "table_seating_sessions", ["store_id"])
    op.create_index("ix_seating_sessions_table", "table_seating_sessions", ["table_id", "status"])
    op.create_table(
        "seating_session_orders",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seating_session_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["seating_session_id"], ["table_seating_sessions.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["open_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_seating_session_orders_order"),
    )
    op.create_index("ix_seating_session_orders_tenant_id", "seating_session_orders", ["tenant_id"])
    op.create_index("ix_seating_session_orders_session", "seating_session_orders", ["seating_session_id"])
    op.create_table(
        "table_activity_events",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("reservation_id", sa.Uuid(), nullable=True),
        sa.Column("seating_session_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["table_id"], ["dining_tables.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"]),
        sa.ForeignKeyConstraint(["seating_session_id"], ["table_seating_sessions.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["open_orders.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_table_activity_events_tenant_id", "table_activity_events", ["tenant_id"])
    op.create_index("ix_table_activity_events_created_at", "table_activity_events", ["created_at"])
    op.create_index("ix_table_activity_table_created", "table_activity_events", ["table_id", "created_at"])
    op.create_index("ix_table_activity_store_created", "table_activity_events", ["store_id", "created_at"])
    _grant(op.get_bind())


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission LIKE 'reservations:%' OR permission LIKE 'table_history:%'"
    )
    op.drop_table("table_activity_events")
    op.drop_table("seating_session_orders")
    op.drop_table("table_seating_sessions")
    op.drop_table("reservation_status_events")
    op.drop_table("reservations")
    op.drop_table("reservation_settings")
