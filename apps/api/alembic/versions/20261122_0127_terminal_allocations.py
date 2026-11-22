"""Terminal stock allocations. Reservations only. Not a second inventory ledger.

Revision ID: 20261122_0127
Revises: 20261122_0126
Create Date: 2026-11-22

Additive. Not applied to the developer, inventory acceptance, or production databases.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0127"
down_revision: str | None = "20261122_0126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "terminal_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("device_thumbprint", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(), nullable=True),
        sa.Column("batch_item_id", sa.Uuid(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quantity_allocated", sa.Integer(), nullable=False),
        sa.Column("quantity_consumed", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("signing_key_id", sa.String(length=64), nullable=False),
        sa.Column("manifest_payload", sa.Text(), nullable=False),
        sa.Column("manifest_signature", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "manifest_id", name="uq_terminal_allocations_manifest"),
    )
    op.create_index("ix_terminal_allocations_tenant_id", "terminal_allocations", ["tenant_id"])
    op.create_index("ix_terminal_allocations_store_id", "terminal_allocations", ["store_id"])
    op.create_index("ix_terminal_allocations_device_id", "terminal_allocations", ["device_id"])
    op.create_index("ix_terminal_allocations_product_id", "terminal_allocations", ["product_id"])
    op.create_table(
        "terminal_allocation_consumptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "allocation_id", "sequence", name="uq_terminal_allocation_consumptions_sequence"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_terminal_allocation_consumptions_key"),
    )


def downgrade() -> None:
    op.drop_table("terminal_allocation_consumptions")
    op.drop_table("terminal_allocations")
