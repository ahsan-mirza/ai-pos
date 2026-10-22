"""Warranty policies, extended plans, and per-unit registrations; repair tickets link to them.

Revision ID: 20261019_0019
Revises: 20261019_0018
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0019"
down_revision: str | None = "20261019_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("products", sa.Column("is_service", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "warranty_policies",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("category_id", sa.Uuid(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("terms", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("months >= 0 AND months <= 120", name="warranty_months_range"),
    )
    op.create_table(
        "warranty_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("extra_months", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, unique=True),
        sa.Column("terms", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("extra_months > 0 AND extra_months <= 60", name="plan_months_range"),
    )
    op.create_table(
        "warranty_registrations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=False, index=True),
        sa.Column("sale_item_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sale_items.id"), nullable=False, unique=True),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), sa.ForeignKey("serial_numbers.id"), nullable=True, index=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("policy_id", sa.Uuid(as_uuid=True), sa.ForeignKey("warranty_policies.id"), nullable=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("warranty_plans.id"), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("claims", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.add_column(
        "repair_tickets",
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
    )
    op.create_index("ix_repair_tickets_customer_id", "repair_tickets", ["customer_id"])
    op.add_column(
        "repair_tickets",
        sa.Column(
            "warranty_registration_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("warranty_registrations.id"),
            nullable=True,
        ),
    )
    op.add_column("repair_tickets", sa.Column("warranty_status", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("repair_tickets", "warranty_status")
    op.drop_column("repair_tickets", "warranty_registration_id")
    op.drop_index("ix_repair_tickets_customer_id", table_name="repair_tickets")
    op.drop_column("repair_tickets", "customer_id")
    op.drop_table("warranty_registrations")
    op.drop_table("warranty_plans")
    op.drop_table("warranty_policies")
    op.drop_column("products", "is_service")
