from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

EINVOICE_STATUSES = ("PENDING", "REPORTED", "CLEARED", "REJECTED")
SOURCE_TYPES = ("sale", "return")


class EInvoice(TenantScoped, TimestampMixin, Base):
    """The tax authority's copy of one invoice or credit note: signed XML, its hash in the business's invoice chain,
    the QR code printed on it, and the authority's answer."""

    __tablename__ = "e_invoices"
    __table_args__ = (
        tenant_unique("document_uuid", name="uq_e_invoices_document_uuid"),
        tenant_unique("source_type", "source_id", name="uq_e_invoices_source"),
        tenant_unique("authority", "counter", name="uq_e_invoices_counter"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    authority: Mapped[str] = mapped_column(String(8), index=True)
    source_type: Mapped[str] = mapped_column(String(8))
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    number: Mapped[str] = mapped_column(String(40), index=True)
    # STANDARD (B2B tax invoice, cleared before it is shared) or SIMPLIFIED (B2C, reported within 24 hours).
    kind: Mapped[str] = mapped_column(String(12))
    document_uuid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    # Invoice counter value (ICV): position in the chain, never reused.
    counter: Mapped[int] = mapped_column(Integer)
    invoice_hash: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str] = mapped_column(String(128))
    qr: Mapped[str] = mapped_column(Text)
    xml: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)
    # "simulation" until the business completes onboarding with the authority.
    submission_mode: Mapped[str] = mapped_column(String(12))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EInvoiceChain(TenantScoped, TimestampMixin, Base):
    """Head of one authority's invoice chain. Locked while an invoice is issued so counters and hashes never fork."""

    __tablename__ = "e_invoice_chains"

    authority: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_counter: Mapped[int] = mapped_column(Integer, default=0)
    last_hash: Mapped[str] = mapped_column(String(128))


class TaxAuthorityCredential(TenantScoped, TimestampMixin, Base):
    """The business's signing key and certificate for one authority. Simulation credentials are self-signed; real
    onboarding replaces them with the certificate the authority issues."""

    __tablename__ = "tax_authority_credentials"

    authority: Mapped[str] = mapped_column(String(8), primary_key=True)
    environment: Mapped[str] = mapped_column(String(12))
    private_key_encrypted: Mapped[str] = mapped_column(Text)
    certificate_pem: Mapped[str] = mapped_column(Text)
