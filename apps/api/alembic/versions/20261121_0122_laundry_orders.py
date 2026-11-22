"""Laundry orders, garments, bags, tags, photos, and held deposits.

Revision ID: 20261121_0122
Revises: 20261121_0121
Create Date: 2026-11-21

Garments being cleaned are not stock. Deposits are held money, not a second tender ledger.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0122"
down_revision: str | None = "20261121_0121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "laundry_tag_events",
    "laundry_tags",
    "laundry_photos",
    "laundry_order_events",
    "laundry_deposits",
    "laundry_bags",
    "laundry_garments",
    "laundry_orders",
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
    op.create_table(
        "laundry_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("intake_store_id", sa.Uuid(), nullable=False),
        sa.Column("plant_store_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("price_list_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("promised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("express", sa.Boolean(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("garment_count", sa.Integer(), nullable=False),
        sa.Column("bag_count", sa.Integer(), nullable=False),
        sa.Column("measured_weight", sa.Integer(), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("discount_cents", sa.Integer(), nullable=False),
        sa.Column("surcharge_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("amount_paid_cents", sa.Integer(), nullable=False),
        sa.Column("balance_due_cents", sa.Integer(), nullable=False),
        sa.Column("payment_status", sa.String(length=16), nullable=False),
        sa.Column("operational_status", sa.String(length=20), nullable=False),
        sa.Column("collection_status", sa.String(length=20), nullable=False),
        sa.Column("claim_status", sa.String(length=16), nullable=False),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_laundry_orders_subtotal"),
        sa.CheckConstraint("discount_cents >= 0", name="ck_laundry_orders_discount"),
        sa.CheckConstraint("surcharge_cents >= 0", name="ck_laundry_orders_surcharge"),
        sa.CheckConstraint("tax_cents >= 0", name="ck_laundry_orders_tax"),
        sa.CheckConstraint("total_cents >= 0", name="ck_laundry_orders_total"),
        sa.CheckConstraint("amount_paid_cents >= 0", name="ck_laundry_orders_paid"),
        sa.CheckConstraint("balance_due_cents >= 0", name="ck_laundry_orders_due"),
        sa.CheckConstraint("amount_paid_cents + balance_due_cents = total_cents", name="ck_laundry_orders_balance"),
        sa.CheckConstraint("garment_count >= 0 AND bag_count >= 0", name="ck_laundry_orders_counts"),
        sa.CheckConstraint("version >= 1", name="ck_laundry_orders_version"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_laundry_orders_customer"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_laundry_orders_device"),
        sa.ForeignKeyConstraint(["intake_store_id"], ["stores.id"], name="fk_laundry_orders_intake"),
        sa.ForeignKeyConstraint(["plant_store_id"], ["stores.id"], name="fk_laundry_orders_plant"),
        sa.ForeignKeyConstraint(["price_list_id"], ["laundry_price_lists.id"], name="fk_laundry_orders_price_list"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_laundry_orders_created_by"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_orders"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_orders_idempotency"),
    )
    op.create_index("ix_laundry_orders_tenant_id", "laundry_orders", ["tenant_id"])
    op.create_index("ix_laundry_orders_intake_store_id", "laundry_orders", ["intake_store_id"])
    op.create_index("ix_laundry_orders_customer_id", "laundry_orders", ["customer_id"])
    op.create_index("ix_laundry_orders_payment_status", "laundry_orders", ["payment_status"])
    op.create_index("ix_laundry_orders_operational_status", "laundry_orders", ["operational_status"])
    op.create_table(
        "laundry_garments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("garment_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("brand", sa.String(length=80), nullable=False),
        sa.Column("colour", sa.String(length=40), nullable=False),
        sa.Column("fabric", sa.String(length=40), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.String(length=500), nullable=False),
        sa.Column("condition", sa.String(length=80), nullable=False),
        sa.Column("stains", sa.String(length=255), nullable=False),
        sa.Column("pre_existing_damage", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("location_store_id", sa.Uuid(), nullable=True),
        sa.Column("exception_state", sa.String(length=20), nullable=False),
        sa.Column("line_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_laundry_garments_quantity"),
        sa.ForeignKeyConstraint(["location_store_id"], ["stores.id"], name="fk_laundry_garments_location"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_garments_order"),
        sa.ForeignKeyConstraint(["service_id"], ["laundry_services.id"], name="fk_laundry_garments_service"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_garments"),
    )
    op.create_index("ix_laundry_garments_tenant_id", "laundry_garments", ["tenant_id"])
    op.create_index("ix_laundry_garments_order_id", "laundry_garments", ["order_id"])
    op.create_index("ix_laundry_garments_service_id", "laundry_garments", ["service_id"])
    op.create_index("ix_laundry_garments_stage", "laundry_garments", ["stage"])
    op.create_table(
        "laundry_bags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("bag_type", sa.String(length=40), nullable=False),
        sa.Column("gross_weight", sa.Integer(), nullable=False),
        sa.Column("tare_weight", sa.Integer(), nullable=False),
        sa.Column("net_weight", sa.Integer(), nullable=False),
        sa.Column("scale_reference", sa.String(length=80), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location_store_id", sa.Uuid(), nullable=True),
        sa.Column("contents", sa.JSON(), nullable=False),
        sa.Column("line_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gross_weight > tare_weight", name="ck_laundry_bags_net"),
        sa.CheckConstraint("tare_weight >= 0", name="ck_laundry_bags_tare"),
        sa.ForeignKeyConstraint(["location_store_id"], ["stores.id"], name="fk_laundry_bags_location"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_bags_order"),
        sa.ForeignKeyConstraint(["service_id"], ["laundry_services.id"], name="fk_laundry_bags_service"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_bags"),
    )
    op.create_index("ix_laundry_bags_tenant_id", "laundry_bags", ["tenant_id"])
    op.create_index("ix_laundry_bags_order_id", "laundry_bags", ["order_id"])
    op.create_index("ix_laundry_bags_service_id", "laundry_bags", ["service_id"])
    op.create_table(
        "laundry_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=True),
        sa.Column("bag_id", sa.Uuid(), nullable=True),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bag_id"], ["laundry_bags.id"], name="fk_laundry_tags_bag"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_laundry_tags_device"),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_tags_garment"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_tags_order"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_tags_store"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_tags"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_tags_code"),
    )
    op.create_index("ix_laundry_tags_tenant_id", "laundry_tags", ["tenant_id"])
    op.create_index("ix_laundry_tags_order_id", "laundry_tags", ["order_id"])
    op.create_index("ix_laundry_tags_status", "laundry_tags", ["status"])
    op.create_index("ix_laundry_tags_store_id", "laundry_tags", ["store_id"])
    op.create_table(
        "laundry_tag_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_laundry_tag_events_device"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_tag_events_order"),
        sa.ForeignKeyConstraint(["tag_id"], ["laundry_tags.id"], name="fk_laundry_tag_events_tag"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_tag_events"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_laundry_tag_events_key"),
    )
    op.create_index("ix_laundry_tag_events_tenant_id", "laundry_tag_events", ["tenant_id"])
    op.create_index("ix_laundry_tag_events_tag_id", "laundry_tag_events", ["tag_id"])
    op.create_index("ix_laundry_tag_events_order_id", "laundry_tag_events", ["order_id"])
    op.create_table(
        "laundry_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("garment_id", sa.Uuid(), nullable=True),
        sa.Column("mime", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size > 0 AND byte_size <= 5000000", name="ck_laundry_photos_size"),
        sa.ForeignKeyConstraint(["garment_id"], ["laundry_garments.id"], name="fk_laundry_photos_garment"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_photos_order"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name="fk_laundry_photos_uploader"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_photos"),
    )
    op.create_index("ix_laundry_photos_tenant_id", "laundry_photos", ["tenant_id"])
    op.create_index("ix_laundry_photos_order_id", "laundry_photos", ["order_id"])
    op.create_table(
        "laundry_order_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_laundry_order_events_actor"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_order_events_order"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_order_events"),
    )
    op.create_index("ix_laundry_order_events_tenant_id", "laundry_order_events", ["tenant_id"])
    op.create_index("ix_laundry_order_events_order_id", "laundry_order_events", ["order_id"])
    op.create_table(
        "laundry_deposits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("received_by_id", sa.Uuid(), nullable=True),
        sa.Column("shift_id", sa.Uuid(), nullable=True),
        sa.Column("refund_shift_id", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_cents > 0", name="ck_laundry_deposits_amount"),
        sa.ForeignKeyConstraint(["order_id"], ["laundry_orders.id"], name="fk_laundry_deposits_order"),
        sa.ForeignKeyConstraint(["received_by_id"], ["users.id"], name="fk_laundry_deposits_receiver"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_deposits_store"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_deposits"),
    )
    op.create_index("ix_laundry_deposits_tenant_id", "laundry_deposits", ["tenant_id"])
    op.create_index("ix_laundry_deposits_order_id", "laundry_deposits", ["order_id"])
    op.create_index("ix_laundry_deposits_store_id", "laundry_deposits", ["store_id"])
    op.create_index("ix_laundry_deposits_status", "laundry_deposits", ["status"])
    op.create_index("ix_laundry_deposits_shift_id", "laundry_deposits", ["shift_id"])
    op.create_index("ix_laundry_deposits_refund_shift_id", "laundry_deposits", ["refund_shift_id"])
    for table in reversed(TABLES):
        _rls(table)


def downgrade() -> None:
    for table in TABLES:
        _drop_rls(table)
        op.drop_table(table)
