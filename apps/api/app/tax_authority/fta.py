"""UAE Federal Tax Authority. Tax invoices are printed, not cleared: a full tax invoice when the buyer has a TRN or
the total exceeds AED 10,000, otherwise a simplified one. Electronic invoicing (PINT AE) is exported on demand by
`export_service`, so nothing is issued per invoice."""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.einvoice import EInvoice
from app.tax_authority.base import InvoiceDocument, InvoiceKind

FULL_INVOICE_THRESHOLD_CENTS = 1_000_000


class FtaAdapter:
    code = "fta"
    name = "UAE Federal Tax Authority"
    country = "AE"
    issues_einvoices = False

    def invoice_kind(self, total_cents: int, buyer_vat_number: str | None) -> InvoiceKind:
        if buyer_vat_number:
            return "FULL"
        return "FULL" if total_cents > FULL_INVOICE_THRESHOLD_CENTS else "SIMPLIFIED"

    def issue(self, db: Session, settings: Settings, document: InvoiceDocument) -> EInvoice | None:
        return None
