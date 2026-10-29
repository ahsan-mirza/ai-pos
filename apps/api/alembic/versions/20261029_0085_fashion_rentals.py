"""Fashion rental terms, bookings, lines and deposit movements.

Revision ID: 20261029_0085
Revises: 20261029_0084
Create Date: 2026-10-29

A catalogue product can be rented without a second product row. Deposits live on the rental,
apart from the rental charge.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0085"
down_revision: str | None = "20261029_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_rentals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("offer", sa.String(length=8), nullable=False),
        sa.Column("price_per_day_cents", sa.Integer(), nullable=False),
        sa.Column("weekly_price_cents", sa.Integer(), nullable=True),
        sa.Column("deposit_cents", sa.Integer(), nullable=False),
        sa.Column("min_days", sa.Integer(), nullable=False),
        sa.Column("max_days", sa.Integer(), nullable=True),
        sa.Column("default_days", sa.Integer(), nullable=False),
        sa.Column("buffer_days", sa.Integer(), nullable=False),
        sa.Column("late_fee_per_day_cents", sa.Integer(), nullable=False),
        sa.Column("cleaning_fee_cents", sa.Integer(), nullable=False),
        sa.Column("requires_inspection", sa.Boolean(), nullable=False),
        sa.Column("condition_note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "product_id", name="uq_product_rentals_product"),
    )
    op.create_index("ix_product_rentals_tenant_id", "product_rentals", ["tenant_id"])
    op.create_index("ix_product_rentals_product_id", "product_rentals", ["product_id"])
    op.create_table(
        "rentals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("agreed_net_cents", sa.Integer(), nullable=False),
        sa.Column("discount_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("extension_net_cents", sa.Integer(), nullable=False),
        sa.Column("extension_tax_cents", sa.Integer(), nullable=False),
        sa.Column("late_fee_cents", sa.Integer(), nullable=False),
        sa.Column("cleaning_fee_cents", sa.Integer(), nullable=False),
        sa.Column("damage_cents", sa.Integer(), nullable=False),
        sa.Column("amount_paid_cents", sa.Integer(), nullable=False),
        sa.Column("deposit_due_cents", sa.Integer(), nullable=False),
        sa.Column("deposit_collected_cents", sa.Integer(), nullable=False),
        sa.Column("deposit_refunded_cents", sa.Integer(), nullable=False),
        sa.Column("deposit_deducted_cents", sa.Integer(), nullable=False),
        sa.Column("deduction_reason", sa.String(length=255), nullable=True),
        sa.Column("waived_late_reason", sa.String(length=255), nullable=True),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("handover_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handover_condition", sa.String(length=255), nullable=True),
        sa.Column("handover_by", sa.Uuid(), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_condition", sa.String(length=255), nullable=True),
        sa.Column("return_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_rentals_reference"),
        sa.UniqueConstraint("tenant_id", "client_request_id", name="uq_rentals_client_request"),
    )
    op.create_index("ix_rentals_tenant_id", "rentals", ["tenant_id"])
    op.create_index("ix_rentals_store_status", "rentals", ["store_id", "status"])
    op.create_index("ix_rentals_dates", "rentals", ["start_date", "return_date"])
    op.create_table(
        "rental_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rental_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["rental_id"], ["rentals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rental_lines_tenant_id", "rental_lines", ["tenant_id"])
    op.create_index("ix_rental_lines_product", "rental_lines", ["product_id", "rental_id"])
    op.create_table(
        "rental_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rental_id", sa.Uuid(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rental_id"], ["rentals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "client_request_id", name="uq_rental_payments_request"),
    )
    op.create_index("ix_rental_payments_tenant_id", "rental_payments", ["tenant_id"])
    op.create_index("ix_rental_payments_rental_id", "rental_payments", ["rental_id"])


def downgrade() -> None:
    op.drop_table("rental_payments")
    op.drop_table("rental_lines")
    op.drop_table("rentals")
    op.drop_table("product_rentals")
