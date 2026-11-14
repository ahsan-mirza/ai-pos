"""Commercial payment methods and attempts. Card providers are not seeded as live.

Revision ID: control_0029
Revises: control_0028
Create Date: 2026-11-14
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "control_0029"
down_revision: str | None = "control_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "platform_payment_methods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("provider_code", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("currencies", sa.JSON(), nullable=False),
        sa.Column("purposes", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_platform_payment_methods"),
        sa.UniqueConstraint("code", name="uq_platform_payment_methods_code"),
    )
    op.create_table(
        "commercial_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("method_code", sa.String(length=32), nullable=False),
        sa.Column("purpose_type", sa.String(length=32), nullable=False),
        sa.Column("purpose_ref", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("amount_fils", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AED"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("failure_reason", sa.String(length=200), nullable=True),
        sa.Column("initiated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_commercial_payments_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["billing_invoices.id"], name="fk_commercial_payments_invoice_id_billing_invoices"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_commercial_payments"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_commercial_payments_idempotency"),
    )
    op.create_index("ix_commercial_payments_tenant_id", "commercial_payments", ["tenant_id"])
    op.create_index("ix_commercial_payments_invoice_id", "commercial_payments", ["invoice_id"])
    op.create_index("ix_commercial_payments_status", "commercial_payments", ["status"])
    op.create_index("ix_commercial_payments_purpose_type", "commercial_payments", ["purpose_type"])
    op.create_table(
        "commercial_payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["commercial_payments.id"],
            name="fk_commercial_payment_events_payment_id_commercial_payments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_commercial_payment_events"),
    )
    op.create_index("ix_commercial_payment_events_payment_id", "commercial_payment_events", ["payment_id"])
    now = datetime.now(UTC)
    methods = sa.table(
        "platform_payment_methods",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("provider_code", sa.String()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("currencies", sa.JSON()),
        sa.column("purposes", sa.JSON()),
        sa.column("sort_order", sa.Integer()),
        sa.column("instructions", sa.Text()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        methods,
        [
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "code": "bank_transfer",
                "display_name": "Bank transfer",
                "category": "BANK_TRANSFER",
                "provider_code": "manual",
                "is_enabled": True,
                "currencies": ["AED"],
                "purposes": [
                    "PLUGIN_PURCHASE",
                    "SUBSCRIPTION",
                    "SUBSCRIPTION_RENEWAL",
                    "SUBSCRIPTION_UPGRADE",
                    "ADDON_PURCHASE",
                ],
                "sort_order": 10,
                "instructions": "Transfer the invoice total and upload the receipt.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "code": "card",
                "display_name": "Credit or debit card",
                "category": "CARD",
                "provider_code": "",
                "is_enabled": False,
                "currencies": ["AED"],
                "purposes": [
                    "PLUGIN_PURCHASE",
                    "SUBSCRIPTION",
                    "SUBSCRIPTION_RENEWAL",
                    "SUBSCRIPTION_UPGRADE",
                    "ADDON_PURCHASE",
                ],
                "sort_order": 20,
                "instructions": "No card provider is configured.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "code": "cash",
                "display_name": "Cash",
                "category": "CASH",
                "provider_code": "manual",
                "is_enabled": False,
                "currencies": ["AED"],
                "purposes": ["PLUGIN_PURCHASE", "ADDON_PURCHASE"],
                "sort_order": 30,
                "instructions": "Cash stays unpaid until authorized staff record the collection.",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_commercial_payment_events_payment_id", table_name="commercial_payment_events")
    op.drop_table("commercial_payment_events")
    op.drop_index("ix_commercial_payments_purpose_type", table_name="commercial_payments")
    op.drop_index("ix_commercial_payments_status", table_name="commercial_payments")
    op.drop_index("ix_commercial_payments_invoice_id", table_name="commercial_payments")
    op.drop_index("ix_commercial_payments_tenant_id", table_name="commercial_payments")
    op.drop_table("commercial_payments")
    op.drop_table("platform_payment_methods")
