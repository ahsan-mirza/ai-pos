"""Repair status timeline, parts and labour lines, and the invoicing sale.

Revision ID: 20261019_0027
Revises: 20261019_0026
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0027"
down_revision: str | None = "20261019_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repair_tickets",
        sa.Column(
            "sale_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("sales.id", name="fk_repair_tickets_sale_id_sales"),
            nullable=True,
        ),
    )
    op.create_table(
        "repair_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(as_uuid=True), sa.ForeignKey("repair_tickets.id"), nullable=False, index=True),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(12), nullable=False, server_default="portal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repair_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(as_uuid=True), sa.ForeignKey("repair_tickets.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("description", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="repair_line_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="repair_line_price_nonnegative"),
    )
    # Existing tickets start their timeline at the status they hold today.
    tickets = sa.table(
        "repair_tickets",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    events = sa.table(
        "repair_events",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("ticket_id", sa.Uuid(as_uuid=True)),
        sa.column("to_status", sa.String),
        sa.column("note", sa.String),
        sa.column("source", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(tickets.c.id, tickets.c.status, tickets.c.created_at)).all()
    if rows:
        op.bulk_insert(
            events,
            [
                {
                    "id": uuid.uuid4(),
                    "ticket_id": ticket_id,
                    "to_status": status,
                    "note": "Status when the timeline was introduced",
                    "source": "migration",
                    "created_at": created_at,
                }
                for ticket_id, status, created_at in rows
            ],
        )


def downgrade() -> None:
    op.drop_table("repair_lines")
    op.drop_table("repair_events")
    op.drop_constraint("fk_repair_tickets_sale_id_sales", "repair_tickets", type_="foreignkey")
    op.drop_column("repair_tickets", "sale_id")
