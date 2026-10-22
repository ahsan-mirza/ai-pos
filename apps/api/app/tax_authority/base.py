"""What every tax authority adapter provides. Invoicing code builds an `InvoiceDocument` and asks the business's
adapter what kind of invoice it is, what QR code to print, and to issue its e-invoice record."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.einvoice import EInvoice

DocumentType = Literal["invoice", "credit_note"]
InvoiceKind = Literal["FULL", "SIMPLIFIED"]


@dataclass(frozen=True)
class Party:
    name: str
    vat_number: str | None = None
    address: str | None = None
    city: str | None = None
    country: str = "AE"


@dataclass(frozen=True)
class DocumentLine:
    name: str
    quantity: int
    unit_price_cents: int
    tax_cents: int
    total_cents: int
    rate_bps: int


@dataclass(frozen=True)
class InvoiceDocument:
    """One invoice or credit note in the shape authorities need, independent of how it was recorded."""

    document_type: DocumentType
    source_id: uuid.UUID
    number: str
    issued_at: datetime
    currency: str
    seller: Party
    buyer: Party | None
    lines: tuple[DocumentLine, ...]
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    # Credit notes point at the invoice they reverse.
    reference_number: str | None = None
    reason: str | None = None
    payment_means: tuple[str, ...] = field(default_factory=tuple)


class TaxAuthorityAdapter(Protocol):
    code: str
    name: str
    country: str
    #: Whether this authority receives a signed copy of every invoice (an `EInvoice` record).
    issues_einvoices: bool

    def invoice_kind(self, total_cents: int, buyer_vat_number: str | None) -> InvoiceKind: ...

    def issue(self, db: Session, settings: Settings, document: InvoiceDocument) -> EInvoice | None:
        """Records (and, where the authority requires it, signs and submits) the e-invoice. Runs inside the caller's
        transaction so the invoice and its e-invoice commit together."""
        ...
