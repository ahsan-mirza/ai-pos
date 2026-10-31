"""Plugin-owned tables. Tenant, customer, branch, sale, and refund rows stay in AxizPOS."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class EInvoicingSetting(Base):
    __tablename__ = "einvoicing_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revenue_band: Mapped[str] = mapped_column(String(24), default="unknown")
    voluntary: Mapped[bool] = mapped_column(default=False)
    b2b_enabled: Mapped[bool] = mapped_column(default=True)
    b2g_enabled: Mapped[bool] = mapped_column(default=True)
    government_customer_ids: Mapped[list] = mapped_column(JSON, default=list)
    environment: Mapped[str] = mapped_column(String(16), default="sandbox")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProviderAccount(Base):
    __tablename__ = "einvoicing_provider_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_code", name="uq_einvoicing_provider_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    provider_code: Mapped[str] = mapped_column(String(32))
    participant_id: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[str] = mapped_column(String(16), default="sandbox")
    connection_status: Mapped[str] = mapped_column(String(24), default="untested")
    credential_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Invoice(Base):
    __tablename__ = "einvoicing_invoices"
    __table_args__ = (UniqueConstraint("tenant_id", "source_sale_id", name="uq_einvoicing_invoice_sale"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    source_sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    document_number: Mapped[str] = mapped_column(String(40), default="")
    document_kind: Mapped[str] = mapped_column(String(16))
    profile_version: Mapped[str] = mapped_column(String(64), default="pint-ae-billing-1@ae-1")
    issue_date: Mapped[str] = mapped_column(String(10), default="")
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider_code: Mapped[str] = mapped_column(String(32), default="")
    provider_status: Mapped[str] = mapped_column(String(64), default="")
    provider_reference: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    error_detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class InvoiceLine(Base):
    __tablename__ = "einvoicing_invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    net_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, default=0)


class Submission(Base):
    __tablename__ = "einvoicing_submissions"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_einvoicing_submission_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SubmissionAttempt(Base):
    __tablename__ = "einvoicing_submission_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))
    provider_status: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CreditNote(Base):
    __tablename__ = "einvoicing_credit_notes"
    __table_args__ = (UniqueConstraint("tenant_id", "source_return_id", name="uq_einvoicing_credit_return"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    source_return_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    document_number: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    net_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    provider_status: Mapped[str] = mapped_column(String(64), default="")
    provider_reference: Mapped[str] = mapped_column(String(120), default="")
    error_detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Outbox(Base):
    __tablename__ = "einvoicing_outbox"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "source_id", name="uq_einvoicing_outbox_source"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WebhookEvent(Base):
    __tablename__ = "einvoicing_webhook_events"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_code", "event_id", name="uq_einvoicing_webhook_event"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    provider_code: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "einvoicing_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(48))
    subject_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
