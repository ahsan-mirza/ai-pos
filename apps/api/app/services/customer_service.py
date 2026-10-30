"""Customer accounts: profiles, credit terms, statement of account, and payments received."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.pagination import count_rows
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.price_list import CustomerGroup
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.wholesale import (
    AgingOut,
    AllocationOut,
    CustomerHistoryLine,
    CustomerOut,
    CustomerUpdate,
    CustomerWrite,
    LedgerAdjustment,
    LedgerEntryOut,
    OpenInvoiceOut,
    PaymentCreate,
    PaymentOut,
    StatementOut,
)
from app.services import cheque_service, ledger_service
from app.services.phone_numbers import search_terms
from app.services.settings_service import business_currency


def _invoice(sale: Sale) -> str:
    return sale.invoice_number or sale.client_sale_id[:8].upper()


def _overdue(db: Session, ids: list[uuid.UUID], now: datetime) -> dict[uuid.UUID, tuple[int, int]]:
    """Per customer: (overdue cents, open invoice count)."""
    if not ids:
        return {}
    open_rows = db.execute(
        select(Sale.customer_id, func.count())
        .where(Sale.customer_id.in_(ids), Sale.is_quote_proforma.is_(False), Sale.due_balance_cents > 0)
        .group_by(Sale.customer_id)
    ).all()
    overdue_rows = db.execute(
        select(Sale.customer_id, func.coalesce(func.sum(Sale.due_balance_cents), 0))
        .where(
            Sale.customer_id.in_(ids),
            Sale.is_quote_proforma.is_(False),
            Sale.due_balance_cents > 0,
            Sale.due_date < now,
        )
        .group_by(Sale.customer_id)
    ).all()
    counts = {row[0]: int(row[1]) for row in open_rows}
    overdue = {row[0]: int(row[1]) for row in overdue_rows}
    return {item: (overdue.get(item, 0), counts.get(item, 0)) for item in ids}


def _home_store(db: Session, customer: Customer) -> uuid.UUID:
    """Account payments are not rung at a till; file the cheque under the customer's last branch, else any store."""
    last = db.scalar(
        select(Sale.store_id).where(Sale.customer_id == customer.id).order_by(Sale.created_at.desc()).limit(1)
    )
    if last is not None:
        return last
    store = db.scalar(select(Store.id).order_by(Store.created_at).limit(1))
    if store is None:
        raise ApiError(422, "invalid_request", "Create a store before taking cheques.")
    return store


def customer_out(
    customer: Customer, overdue_cents: int = 0, open_invoice_count: int = 0, cheque_exposure_cents: int = 0
) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        code=customer.code,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        customer_type=customer.customer_type,  # type: ignore[arg-type]
        company_name=customer.company_name,
        trn_vat_number=customer.trn_vat_number,
        price_tier=customer.price_tier,  # type: ignore[arg-type]
        credit_limit_cents=customer.credit_limit_cents,
        current_balance_cents=customer.current_balance_cents,
        available_credit_cents=customer.available_credit_cents,
        payment_terms=customer.payment_terms,  # type: ignore[arg-type]
        address=customer.address,
        is_active=customer.is_active,
        overdue_cents=overdue_cents,
        open_invoice_count=open_invoice_count,
        cheque_exposure_cents=cheque_exposure_cents,
        credit_hold=customer.credit_hold,
        credit_hold_reason=customer.credit_hold_reason,
        whatsapp_opt_in=customer.whatsapp_opt_in,
        sms_opt_in=customer.sms_opt_in,
        email_opt_in=customer.email_opt_in,
        marketing_whatsapp_opt_in=customer.marketing_whatsapp_opt_in,
        marketing_sms_opt_in=customer.marketing_sms_opt_in,
        marketing_email_opt_in=customer.marketing_email_opt_in,
        loyalty_points=customer.loyalty_points,
        risk_score=customer.risk_score,
        risk_grade=customer.risk_grade,
        group_id=customer.group_id,
        tax_treatment=customer.tax_treatment or "STANDARD",  # type: ignore[arg-type]
        tax_certificate_ref=customer.tax_certificate_ref,
        tax_certificate_expiry=customer.tax_certificate_expiry,
        birthday=customer.birthday,
        gender=customer.gender,
        preferred_sizes=customer.preferred_sizes or {},
        notes=customer.notes,
        tags=list(customer.tags or []),
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


def _with_overdue(db: Session, customers: list[Customer]) -> list[CustomerOut]:
    ids = [item.id for item in customers]
    stats = _overdue(db, ids, datetime.now(UTC))
    exposure = cheque_service.exposure(db, ids)
    return [customer_out(item, *stats.get(item.id, (0, 0)), exposure.get(item.id, 0)) for item in customers]


def get_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    return customer


def customer_detail(db: Session, customer_id: uuid.UUID) -> CustomerOut:
    return _with_overdue(db, [get_customer(db, customer_id)])[0]


def purchase_history(
    db: Session,
    customer_id: uuid.UUID,
    limit: int,
    *,
    sold_from: datetime | None = None,
    sold_to: datetime | None = None,
) -> list[CustomerHistoryLine]:
    """Recent items this customer bought. Prices and names are the ones stored on the sale line."""
    get_customer(db, customer_id)
    refunded_qty = (
        select(func.coalesce(func.sum(ReturnItem.quantity), 0))
        .where(ReturnItem.sale_item_id == SaleItem.id)
        .scalar_subquery()
    )
    statement = (
        select(Sale, SaleItem, Product, refunded_qty)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            Sale.customer_id == customer_id,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(("completed", "partially_refunded", "refunded")),
        )
        .order_by(Sale.created_at.desc(), SaleItem.id)
        .limit(limit)
    )
    if sold_from is not None:
        statement = statement.where(Sale.created_at >= sold_from)
    if sold_to is not None:
        statement = statement.where(Sale.created_at < sold_to)
    history = []
    for sale, item, product, returned in db.execute(statement).all():
        attrs = item.variant_attributes or product.variant_attributes or {}
        history.append(
            CustomerHistoryLine(
                sold_at=sale.created_at,
                name=item.product_name or product.name,
                size=attrs.get("size"),
                color=attrs.get("color") or attrs.get("colour"),
                quantity=item.quantity,
                invoice=sale.invoice_number or sale.client_sale_id[:8].upper(),
                sku=item.sku or product.sku,
                unit=item.unit_type,
                unit_price_cents=item.unit_price_cents,
                discount_cents=item.discount_cents + item.manual_discount_cents,
                line_total_cents=item.line_total_cents,
                quantity_refunded=int(returned or 0),
                sale_status=sale.status,
            )
        )
    return history


def list_customers(
    db: Session,
    *,
    query: str | None,
    customer_type: str | None,
    include_inactive: bool,
    limit: int,
    offset: int = 0,
) -> tuple[list[CustomerOut], int]:
    """One page of customers by name, and the total matching the filters."""
    statement = select(Customer)
    if customer_type is not None:
        statement = statement.where(Customer.customer_type == customer_type)
    if not include_inactive:
        statement = statement.where(Customer.is_active.is_(True))
    if query:
        like = f"%{query.strip().lower()}%"
        phone_match = [func.coalesce(Customer.phone, "").like(like)]
        for term in search_terms(query):
            phone_match.append(func.coalesce(Customer.phone, "").like(f"%{term}%"))
        statement = statement.where(
            or_(
                func.lower(Customer.name).like(like),
                func.lower(func.coalesce(Customer.company_name, "")).like(like),
                func.lower(Customer.code).like(like),
                *phone_match,
                func.lower(func.coalesce(Customer.trn_vat_number, "")).like(like),
            )
        )
    total = count_rows(db, statement)
    page = statement.order_by(Customer.name, Customer.id).offset(offset).limit(limit)
    return _with_overdue(db, list(db.scalars(page).all())), total


def sync_customers(db: Session) -> list[CustomerOut]:
    """Every active account for the register's offline cache."""
    statement = select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)
    return _with_overdue(db, list(db.scalars(statement).all()))


def _next_code(db: Session, name: str) -> str:
    stem = "".join(re.findall(r"[A-Z0-9]", name.upper()))[:4] or "CUST"
    count = db.scalar(select(func.count()).select_from(Customer)) or 0
    for offset in range(1, 200):
        candidate = f"{stem}-{count + offset:04d}"
        if db.scalar(select(Customer.id).where(Customer.code == candidate)) is None:
            return candidate
    raise ApiError(409, "conflict", "Could not allocate a customer code. Try again.")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "The customer conflicts with an existing account.") from exc


def _check_group(db: Session, group_id: uuid.UUID | None) -> None:
    if group_id is not None and db.get(CustomerGroup, group_id) is None:
        raise ApiError(422, "invalid_request", "That customer group does not exist.")


def new_customer(db: Session, data: CustomerWrite, customer_id: uuid.UUID | None = None) -> Customer:
    """Adds a customer to the session without committing; the caller owns the transaction."""
    _check_group(db, data.group_id)
    customer = Customer(
        code=_next_code(db, data.company_name or data.name),
        current_balance_cents=0,
        **data.model_dump(),
    )
    if customer_id is not None:
        customer.id = customer_id
    customer.name = customer.name.strip()
    db.add(customer)
    return customer


def create_customer(db: Session, data: CustomerWrite) -> CustomerOut:
    customer = new_customer(db, data)
    _commit(db)
    db.refresh(customer)
    return customer_out(customer)


def update_customer(db: Session, customer_id: uuid.UUID, data: CustomerUpdate) -> CustomerOut:
    customer = get_customer(db, customer_id)
    changes = data.model_dump(exclude_unset=True)
    for name in (
        "name",
        "customer_type",
        "price_tier",
        "credit_limit_cents",
        "payment_terms",
        "is_active",
        "whatsapp_opt_in",
        "sms_opt_in",
        "email_opt_in",
        "marketing_whatsapp_opt_in",
        "marketing_sms_opt_in",
        "marketing_email_opt_in",
        "tax_treatment",
    ):
        if name in changes and changes[name] is None:
            changes.pop(name)
    _check_group(db, changes.get("group_id"))
    for name, value in changes.items():
        setattr(customer, name, value.strip() if name == "name" else value)
    if customer.customer_type == "RETAIL" and customer.credit_limit_cents > 0:
        db.rollback()
        raise ApiError(422, "invalid_request", "Only wholesale customers can have a credit limit.")
    _commit(db)
    db.refresh(customer)
    return customer_detail(db, customer.id)


def _entry_out(entry: CustomerLedgerEntry, invoices: dict[uuid.UUID, str]) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=entry.id,
        entry_type=entry.entry_type,  # type: ignore[arg-type]
        amount_cents=entry.amount_cents,
        balance_after_cents=entry.balance_after_cents,
        sale_id=entry.sale_id,
        invoice=invoices.get(entry.sale_id) if entry.sale_id is not None else None,
        due_date=entry.due_date,
        method=entry.method,
        reference=entry.reference,
        note=entry.note,
        created_at=ledger_service.as_utc(entry.created_at),
    )


def statement(db: Session, customer_id: uuid.UUID) -> StatementOut:
    customer = get_customer(db, customer_id)
    now = datetime.now(UTC)
    rows = ledger_service.entries(db, customer.id)
    sale_ids = {row.sale_id for row in rows if row.sale_id is not None}
    invoices = (
        {sale.id: _invoice(sale) for sale in db.scalars(select(Sale).where(Sale.id.in_(sale_ids))).all()}
        if sale_ids
        else {}
    )
    open_sales = ledger_service.open_invoices(db, customer.id)
    buckets = ledger_service.aging(open_sales, now)
    totals = db.execute(
        select(
            func.coalesce(func.sum(Sale.total_cents), 0),
            func.coalesce(func.sum(Sale.amount_paid_cents), 0),
        ).where(Sale.customer_id == customer.id, Sale.is_quote_proforma.is_(False))
    ).one()
    overdue = sum(sale.due_balance_cents for sale in open_sales if ledger_service.days_overdue(sale, now) > 0)
    return StatementOut(
        customer=customer_out(
            customer, overdue, len(open_sales), cheque_service.exposure(db, [customer.id]).get(customer.id, 0)
        ),
        currency=business_currency(db),
        entries=[_entry_out(row, invoices) for row in rows],
        open_invoices=[
            OpenInvoiceOut(
                sale_id=sale.id,
                invoice=_invoice(sale),
                created_at=ledger_service.as_utc(sale.created_at),
                due_date=ledger_service.as_utc(sale.due_date) if sale.due_date is not None else None,
                total_cents=sale.total_cents,
                amount_paid_cents=sale.amount_paid_cents,
                due_balance_cents=sale.due_balance_cents,
                days_overdue=ledger_service.days_overdue(sale, now),
                payment_status=sale.payment_status,
            )
            for sale in open_sales
        ],
        aging=AgingOut(
            current=buckets["current"],
            days_1_30=buckets["1_30"],
            days_31_60=buckets["31_60"],
            days_61_90=buckets["61_90"],
            days_90_plus=buckets["90_plus"],
        ),
        total_invoiced_cents=int(totals[0]),
        total_paid_cents=int(totals[1]),
        generated_at=now,
    )


def receive_payment(db: Session, customer_id: uuid.UUID, data: PaymentCreate, user_id: uuid.UUID | None) -> PaymentOut:
    customer = get_customer(db, customer_id)
    entry, allocations = ledger_service.receive_payment(
        db,
        customer,
        amount_cents=data.amount_cents,
        method=data.method,
        reference=data.reference.strip(),
        note=data.note.strip(),
        user_id=user_id,
    )
    if data.cheque is not None:
        cheque_service.record(
            db,
            details=data.cheque,
            amount_cents=data.amount_cents,
            currency=business_currency(db),
            store_id=_home_store(db, customer),
            customer_id=customer.id,
            source="LEDGER",
            ledger_entry_id=entry.id,
            user_id=user_id,
        )
    applied = sum(amount for _, amount in allocations)
    out = PaymentOut(
        entry=_entry_out(entry, {sale.id: _invoice(sale) for sale, _ in allocations}),
        allocations=[
            AllocationOut(
                sale_id=sale.id,
                invoice=_invoice(sale),
                applied_cents=amount,
                remaining_cents=sale.due_balance_cents,
            )
            for sale, amount in allocations
        ],
        unapplied_cents=data.amount_cents - applied,
        customer=customer_out(customer),
    )
    _commit(db)
    out.customer = customer_detail(db, customer.id)
    return out


def adjust_balance(
    db: Session, customer_id: uuid.UUID, data: LedgerAdjustment, user_id: uuid.UUID | None
) -> CustomerOut:
    customer = get_customer(db, customer_id)
    ledger_service.adjust(db, customer, amount_cents=data.amount_cents, note=data.note.strip(), user_id=user_id)
    _commit(db)
    return customer_detail(db, customer.id)
