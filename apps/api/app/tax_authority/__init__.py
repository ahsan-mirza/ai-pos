"""Tax authority adapters. Invoicing code never checks which country a business is in; it asks the adapter.

`adapter_for(db)` returns the business's adapter (Store Settings → VAT). `issue_for_sale` / `issue_for_return` build
the authority-neutral document and let the adapter record its e-invoice inside the caller's transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.customer import Customer
from app.models.einvoice import EInvoice
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.tax_authority.base import DocumentLine, InvoiceDocument, Party, TaxAuthorityAdapter
from app.tax_authority.fta import FtaAdapter
from app.tax_authority.zatca import ZatcaAdapter

ADAPTERS: dict[str, TaxAuthorityAdapter] = {"fta": FtaAdapter(), "zatca": ZatcaAdapter()}
DEFAULT_AUTHORITY = "fta"

__all__ = [
    "ADAPTERS",
    "DEFAULT_AUTHORITY",
    "InvoiceDocument",
    "TaxAuthorityAdapter",
    "adapter_for",
    "einvoice_for",
    "issue_for_return",
    "issue_for_sale",
]


def adapter_for(db: Session) -> TaxAuthorityAdapter:
    from app.services.settings_service import cached_settings

    return ADAPTERS.get(cached_settings(db).tax_authority, ADAPTERS[DEFAULT_AUTHORITY])


def _seller(db: Session, store: Store, country: str) -> Party:
    from app.services.settings_service import cached_settings

    row = cached_settings(db)
    return Party(
        name=row.legal_name or store.name,
        vat_number=row.trn,
        address=store.address,
        city=getattr(store, "emirate", None),
        country=country,
    )


def _buyer(customer: Customer | None, country: str) -> Party | None:
    if customer is None:
        return None
    return Party(
        name=customer.company_name or customer.name,
        vat_number=customer.trn_vat_number,
        address=customer.address,
        country=country,
    )


def _product_names(db: Session, ids: set) -> dict:
    if not ids:
        return {}
    return {row.id: row.name for row in db.scalars(select(Product).where(Product.id.in_(ids)))}


def issue_for_sale(db: Session, settings: Settings, sale: Sale, customer: Customer | None) -> EInvoice | None:
    adapter = adapter_for(db)
    if not adapter.issues_einvoices or sale.is_quote_proforma:
        return None
    store = db.get(Store, sale.store_id)
    assert store is not None
    names = _product_names(db, {item.product_id for item in sale.items})
    document = InvoiceDocument(
        document_type="invoice",
        source_id=sale.id,
        number=sale.invoice_number or sale.client_sale_id[:16].upper(),
        issued_at=sale.created_at,
        currency=sale.currency,
        seller=_seller(db, store, adapter.country),
        buyer=_buyer(customer, adapter.country),
        lines=tuple(
            DocumentLine(
                name=item.description or names.get(item.product_id, "Item"),
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                total_cents=item.line_total_cents,
                rate_bps=item.tax_rate_bps or 0,
            )
            for item in sale.items
        ),
        subtotal_cents=sale.subtotal_cents,
        tax_cents=sale.tax_cents,
        total_cents=sale.total_cents,
        payment_means=tuple(dict.fromkeys(tender.method for tender in sale.tenders)) or (sale.payment_method,),
    )
    return adapter.issue(db, settings, document)


def issue_for_return(db: Session, settings: Settings, record: SaleReturn) -> EInvoice | None:
    adapter = adapter_for(db)
    if not adapter.issues_einvoices:
        return None
    sale = db.get(Sale, record.original_sale_id)
    store = db.get(Store, record.store_id)
    assert sale is not None and store is not None
    customer = db.get(Customer, sale.customer_id) if sale.customer_id else None
    items = list(db.scalars(select(ReturnItem).where(ReturnItem.return_id == record.id)))
    names = _product_names(db, {item.product_id for item in items})
    rates = dict(
        db.execute(
            select(SaleItem.id, SaleItem.tax_rate_bps).where(SaleItem.id.in_({item.sale_item_id for item in items}))
        ).all()
    )
    document = InvoiceDocument(
        document_type="credit_note",
        source_id=record.id,
        number=record.credit_note_number or str(record.id)[:16].upper(),
        issued_at=record.created_at,
        currency=record.currency,
        seller=_seller(db, store, adapter.country),
        buyer=_buyer(customer, adapter.country),
        lines=tuple(
            DocumentLine(
                name=names.get(item.product_id, "Item"),
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_refund_cents,
                total_cents=item.refund_cents,
                rate_bps=rates.get(item.sale_item_id) or 0,
            )
            for item in items
        ),
        subtotal_cents=record.total_refund_cents - record.tax_refund_cents,
        tax_cents=record.tax_refund_cents,
        total_cents=record.total_refund_cents,
        reference_number=sale.invoice_number,
        reason=record.reason_notes or None,
        payment_means=(record.refund_method,),
    )
    return adapter.issue(db, settings, document)


def einvoice_for(db: Session, source_type: str, source_id) -> EInvoice | None:
    return db.scalar(select(EInvoice).where(EInvoice.source_type == source_type, EInvoice.source_id == source_id))
