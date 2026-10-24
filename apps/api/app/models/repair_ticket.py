from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class RepairTicket(TenantScoped, TimestampMixin, Base):
    __tablename__ = "repair_tickets"
    __table_args__ = (
        tenant_unique("tracking_token", name="uq_repair_tickets_tracking_token"),
        CheckConstraint("estimated_cost_cents >= 0", name="estimate_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_phone: Mapped[str] = mapped_column(String(40))
    device_model: Mapped[str] = mapped_column(String(120))
    identifier_kind: Mapped[str] = mapped_column(String(16))
    identifier_hash: Mapped[str] = mapped_column(String(64))
    identifier_encrypted: Mapped[str] = mapped_column(Text)
    issue: Mapped[str] = mapped_column(String(2000))
    # intake -> diagnosing -> awaiting_approval -> in_repair <-> waiting_parts -> ready -> closed (or cancelled)
    status: Mapped[str] = mapped_column(String(20), index=True)
    estimated_cost_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    warranty_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("warranty_registrations.id"), nullable=True
    )
    # IN_WARRANTY, EXPIRED, or NOT_FOUND (the unit was not sold here), set when the ticket is booked.
    warranty_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The sale that invoiced the ticket's parts and labour; once set the lines are frozen.
    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    technician_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # LOW | NORMAL | HIGH | URGENT
    priority: Mapped[str] = mapped_column(String(8), default="NORMAL", server_default="NORMAL")
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Screen lock code, encrypted like identifiers; revealing it is audited.
    passcode_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"powers_on": true, "screen_cracked": false, ...} as checked with the customer at the counter.
    intake_checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    accessories: Mapped[str] = mapped_column(String(300), default="", server_default="")
    # Estimate approval: PENDING while the customer decides, then APPROVED or DECLINED.
    approval_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    approval_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # link (the customer's phone), in_store, phone (staff recorded a call)
    approval_channel: Mapped[str | None] = mapped_column(String(12), nullable=True)
    approval_note: Mapped[str] = mapped_column(String(300), default="", server_default="")
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repair_warranty_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Public status page /track/<token>; issued on first use for tickets booked before it existed.
    tracking_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepairAttachment(TenantScoped, Base):
    """A photo or document on a ticket (intake condition, diagnosis, finished work), stored under storage/repairs."""

    __tablename__ = "repair_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repair_tickets.id", ondelete="CASCADE"), index=True
    )
    # INTAKE | DIAGNOSIS | AFTER
    kind: Mapped[str] = mapped_column(String(10))
    file_name: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(120))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepairDeposit(TenantScoped, Base):
    """Money taken up front. HELD until the invoice credits it as a `deposit` tender (APPLIED), or given back
    (REFUNDED) when the repair does not go ahead."""

    __tablename__ = "repair_deposits"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="deposit_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("repair_tickets.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    reference: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(10), default="HELD", index=True)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    refund_shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    applied_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepairEvent(TenantScoped, Base):
    """Append-only status history of a repair ticket."""

    __tablename__ = "repair_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("repair_tickets.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(500), default="")
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(12), default="portal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepairLine(TenantScoped, TimestampMixin, Base):
    """A part (a stocked catalog product) or labour (an open-price service product) charged on the ticket.
    unit_price_cents is per piece and follows the business's VAT-inclusive/exclusive setting like any sale line."""

    __tablename__ = "repair_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="price_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("repair_tickets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    description: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # Parts held for this ticket in the branch's quantity_reserved; less than quantity when stock ran short.
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
