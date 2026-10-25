"""Read side of e-invoicing: the chain head, per-status counts and the issued documents."""

import uuid

from cryptography import x509
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.einvoice import EInvoice, EInvoiceChain, TaxAuthorityCredential
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.schemas.einvoices import AuthorityOption, EInvoiceList, EInvoiceOut, EInvoiceSummary
from app.tax_authority import ADAPTERS, adapter_for


def _scoped(statement, store_scope: uuid.UUID | None):
    if store_scope is None:
        return statement
    sales = select(Sale.id).where(Sale.store_id == store_scope)
    returns = select(SaleReturn.id).where(SaleReturn.store_id == store_scope)
    return statement.where(
        or_(
            (EInvoice.source_type == "sale") & EInvoice.source_id.in_(sales),
            (EInvoice.source_type == "return") & EInvoice.source_id.in_(returns),
        )
    )


def out(record: EInvoice) -> EInvoiceOut:
    result = EInvoiceOut.model_validate(record)
    result.errors = list((record.response or {}).get("errors", []))
    return result


def summary(db: Session, store_scope: uuid.UUID | None) -> EInvoiceSummary:
    adapter = adapter_for(db)
    chain = db.scalar(select(EInvoiceChain).where(EInvoiceChain.authority == adapter.code))
    credential = db.scalar(select(TaxAuthorityCredential).where(TaxAuthorityCredential.authority == adapter.code))
    certificate = x509.load_pem_x509_certificate(credential.certificate_pem.encode()) if credential else None
    counts = dict(
        db.execute(
            _scoped(
                select(EInvoice.status, func.count()).where(EInvoice.authority == adapter.code), store_scope
            ).group_by(EInvoice.status)
        ).all()
    )
    return EInvoiceSummary(
        authority=adapter.code,
        authority_name=adapter.name,
        issues_einvoices=adapter.issues_einvoices,
        options=[
            AuthorityOption(code=a.code, name=a.name, country=a.country, issues_einvoices=a.issues_einvoices)
            for a in ADAPTERS.values()
        ],
        environment=credential.environment if credential else None,
        certificate_subject=certificate.subject.rfc4514_string() if certificate else None,
        certificate_expires_at=certificate.not_valid_after_utc if certificate else None,
        last_counter=chain.last_counter if chain else 0,
        last_hash=chain.last_hash if chain and chain.last_counter else None,
        counts={status: int(counts.get(status, 0)) for status in ("PENDING", "REPORTED", "CLEARED", "REJECTED")},
    )


def list_einvoices(
    db: Session, *, status: str | None, store_scope: uuid.UUID | None, limit: int, offset: int
) -> EInvoiceList:
    statement = _scoped(select(EInvoice), store_scope)
    if status is not None:
        statement = statement.where(EInvoice.status == status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(EInvoice.counter.desc()).limit(limit).offset(offset)).all()
    return EInvoiceList(items=[out(row) for row in rows], total=total)


def get(db: Session, einvoice_id: uuid.UUID, store_scope: uuid.UUID | None) -> EInvoice:
    record = db.scalar(_scoped(select(EInvoice).where(EInvoice.id == einvoice_id), store_scope))
    if record is None:
        raise ApiError(404, "not_found", "E-invoice was not found.")
    return record
