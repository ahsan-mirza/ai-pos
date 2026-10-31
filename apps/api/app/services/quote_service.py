"""Proforma quotes. An open quote holds branch stock through inventory_levels.quantity_reserved, and any
IMEI it names is held by its sale_items link, so nothing else can sell it until the quote converts,
expires, or is cancelled. Expiry is applied lazily whenever quotes are read or written."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.core.security import decrypt_value
from app.models.customer import Customer
from app.models.product import Product
from app.models.quote_payment import QuotePayment
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import (
    PriceOverridePayload,
    SaleItemPayload,
    SalePayload,
    SaleTenderPayload,
)
from app.schemas.wholesale import (
    QuoteConvert,
    QuoteList,
    QuoteOut,
    QuotePayload,
    QuotePaymentIn,
    QuotePaymentOut,
    QuoteStats,
)
from app.services import inventory, price_list_service, uom_service
from app.services.catalog_service import sale_out
from app.services.ledger_service import as_utc
from app.services.numbering import next_server_number
from app.services.sale_service import (
    audit,
    held_by_quote,
    price_lines,
    quote_number,
    record_sale,
    require_customer,
    sellable_serial,
)
from app.services.settings_service import business_currency
from app.services.sync_validation import require_cashier, require_store
from app.services.tax import entered_includes_tax, line_tax
from app.services.tax import policy as tax_policy_for

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Archivo.ttf"
ACCENT = (242, 106, 33)
CHARCOAL = (34, 32, 38)
MUTED = (122, 120, 126)
LINE = (232, 229, 225)
SURFACE = (247, 245, 242)
EXPIRING_SOON = timedelta(hours=48)


def _rejected(exc: SyncRejected) -> ApiError:
    return ApiError(422, "quote_rejected", exc.message)


def _load(db: Session, quote_id: uuid.UUID) -> Sale:
    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.serial_number))
        .where(Sale.id == quote_id, Sale.is_quote_proforma.is_(True))
    )
    quote = db.scalars(statement).unique().one_or_none()
    if quote is None:
        raise ApiError(404, "not_found", "Quote was not found.")
    return quote


def _held_quantities(quote: Sale) -> dict[uuid.UUID, int]:
    held: dict[uuid.UUID, int] = defaultdict(int)
    for item in quote.items:
        held[item.product_id] += item.quantity
    return held


def _release(db: Session, quote: Sale) -> None:
    for product_id, quantity in _held_quantities(quote).items():
        inventory.release(db, product_id, quote.store_id, quantity)


def expire_quotes(db: Session) -> int:
    now = datetime.now(UTC)
    stale = db.scalars(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(Sale.quote_status == "OPEN", Sale.quote_expiry_date.is_not(None), Sale.quote_expiry_date < now)
    ).all()
    for quote in stale:
        _release(db, quote)
        quote.quote_status = "EXPIRED"
    if stale:
        db.commit()
    return len(stale)


def _names(db: Session, quotes: list[Sale]) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    customer_ids = {quote.customer_id for quote in quotes if quote.customer_id is not None}
    cashier_ids = {quote.cashier_id for quote in quotes}
    customers = (
        {
            row.id: row.company_name or row.name
            for row in db.scalars(select(Customer).where(Customer.id.in_(customer_ids)))
        }
        if customer_ids
        else {}
    )
    cashiers = (
        {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(cashier_ids))).unique()}
        if cashier_ids
        else {}
    )
    return customers, cashiers


def _payments(db: Session, quotes: list[Sale]) -> dict[uuid.UUID, list[QuotePaymentOut]]:
    ids = [quote.id for quote in quotes if quote.quote_kind == "LAYAWAY"]
    if not ids:
        return {}
    rows = list(
        db.scalars(select(QuotePayment).where(QuotePayment.quote_id.in_(ids)).order_by(QuotePayment.received_at))
    )
    receivers = {row.received_by_id for row in rows}
    names = (
        {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(receivers))).unique()}
        if receivers
        else {}
    )
    grouped: dict[uuid.UUID, list[QuotePaymentOut]] = defaultdict(list)
    for row in rows:
        grouped[row.quote_id].append(
            QuotePaymentOut(
                id=row.id,
                amount_cents=row.amount_cents,
                method=row.method,
                reference=row.reference,
                status=row.status,
                received_by_name=names.get(row.received_by_id),
                received_at=as_utc(row.received_at),
            )
        )
    return grouped


def _quote_out(
    quote: Sale,
    settings: Settings,
    customers: dict[uuid.UUID, str],
    cashiers: dict[uuid.UUID, str],
    payments: dict[uuid.UUID, list[QuotePaymentOut]],
) -> QuoteOut:
    base = sale_out(quote, settings, customers.get(quote.customer_id) if quote.customer_id else None)
    rows = payments.get(quote.id, [])
    return QuoteOut(
        **base.model_dump(),
        number=quote_number(quote),
        cashier_name=cashiers.get(quote.cashier_id),
        quote_kind=quote.quote_kind or "QUOTE",  # type: ignore[arg-type]
        deposits_cents=sum(row.amount_cents for row in rows if row.status in ("ACTIVE", "APPLIED")),
        refund_due_cents=sum(row.amount_cents for row in rows if row.status == "REFUND_DUE"),
        payments=rows,
    )


def quote_detail(db: Session, settings: Settings, quote_id: uuid.UUID, store_scope: uuid.UUID | None) -> QuoteOut:
    expire_quotes(db)
    quote = _load(db, quote_id)
    if store_scope is not None and quote.store_id != store_scope:
        raise ApiError(404, "not_found", "Quote was not found.")
    customers, cashiers = _names(db, [quote])
    return _quote_out(quote, settings, customers, cashiers, _payments(db, [quote]))


def _active_deposits(db: Session, quote_id: uuid.UUID) -> list[QuotePayment]:
    return list(
        db.scalars(select(QuotePayment).where(QuotePayment.quote_id == quote_id, QuotePayment.status == "ACTIVE"))
    )


def _take_payment(db: Session, quote: Sale, data: QuotePaymentIn, received_by_id: uuid.UUID) -> None:
    if quote.quote_kind != "LAYAWAY":
        raise SyncRejected("Only layaways take deposits.")
    if quote.quote_status != "OPEN":
        raise SyncRejected(f"This layaway is already {str(quote.quote_status).lower()}.")
    if db.get(QuotePayment, data.id) is not None:
        raise SyncRejected("This deposit was already recorded.")
    paid = sum(row.amount_cents for row in _active_deposits(db, quote.id))
    if paid + data.amount_cents > quote.total_cents:
        raise SyncRejected(f"Deposits cannot exceed the layaway total; {quote.total_cents - paid} cents remain.")
    db.add(
        QuotePayment(
            id=data.id,
            quote_id=quote.id,
            store_id=quote.store_id,
            amount_cents=data.amount_cents,
            method=data.method,
            reference=data.reference.strip(),
            received_by_id=received_by_id,
            shift_id=data.shift_id,
            status="ACTIVE",
            received_at=datetime.now(UTC),
        )
    )
    quote.amount_paid_cents = paid + data.amount_cents
    quote.due_balance_cents = quote.total_cents - quote.amount_paid_cents
    db.flush()


def add_payment(
    db: Session,
    settings: Settings,
    quote_id: uuid.UUID,
    data: QuotePaymentIn,
    *,
    received_by_id: uuid.UUID,
    store_scope: uuid.UUID | None,
) -> QuoteOut:
    expire_quotes(db)
    quote = _load(db, quote_id)
    if store_scope is not None and quote.store_id != store_scope:
        raise ApiError(404, "not_found", "Quote was not found.")
    try:
        require_cashier(db, received_by_id, quote.store_id)
        _take_payment(db, quote, data, received_by_id)
    except SyncRejected as exc:
        db.rollback()
        raise _rejected(exc) from exc
    db.commit()
    return quote_detail(db, settings, quote.id, None)


def list_quotes(
    db: Session,
    settings: Settings,
    *,
    status: str | None,
    customer_id: uuid.UUID | None,
    store_scope: uuid.UUID | None,
    limit: int,
    offset: int = 0,
) -> QuoteList:
    expire_quotes(db)
    scope = [Sale.is_quote_proforma.is_(True)]
    if store_scope is not None:
        scope.append(Sale.store_id == store_scope)
    if customer_id is not None:
        scope.append(Sale.customer_id == customer_id)

    counts: dict[str, tuple[int, int]] = {
        row[0]: (int(row[1]), int(row[2]))
        for row in db.execute(
            select(Sale.quote_status, func.count(), func.coalesce(func.sum(Sale.total_cents), 0))
            .where(*scope)
            .group_by(Sale.quote_status)
        ).all()
    }
    soon = datetime.now(UTC) + EXPIRING_SOON
    expiring = db.scalar(
        select(func.count()).select_from(Sale).where(*scope, Sale.quote_status == "OPEN", Sale.quote_expiry_date < soon)
    )
    total = sum(count for count, _ in counts.values())
    converted = counts.get("CONVERTED", (0, 0))

    statement = (
        select(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.serial_number))
        .where(*scope)
        .order_by(Sale.created_at.desc(), Sale.id)
        .offset(offset)
        .limit(limit)
    )
    if status is not None:
        statement = statement.where(Sale.quote_status == status)
    matching = counts.get(status, (0, 0))[0] if status is not None else total
    quotes = list(db.scalars(statement).unique().all())
    customers, cashiers = _names(db, quotes)
    payments = _payments(db, quotes)
    return QuoteList(
        currency=business_currency(db),
        stats=QuoteStats(
            open_count=counts.get("OPEN", (0, 0))[0],
            open_value_cents=counts.get("OPEN", (0, 0))[1],
            converted_count=converted[0],
            converted_value_cents=converted[1],
            expired_count=counts.get("EXPIRED", (0, 0))[0],
            cancelled_count=counts.get("CANCELLED", (0, 0))[0],
            conversion_rate_bps=round(converted[0] * 10_000 / total) if total else 0,
            expiring_soon_count=int(expiring or 0),
        ),
        quotes=[_quote_out(quote, settings, customers, cashiers, payments) for quote in quotes],
        total=matching,
    )


def create_quote(db: Session, settings: Settings, data: QuotePayload) -> QuoteOut:
    expire_quotes(db)
    try:
        store = require_store(db, data.store_id)
        if store.currency != data.currency:
            raise SyncRejected("Quote currency must match the store currency.")
        cashier = require_cashier(db, data.cashier_id, data.store_id)
        if db.get(Sale, data.id) is not None:
            raise SyncRejected("Quote already exists.")
        customer = require_customer(db, data.customer_id)
        tier = price_list_service.tier_for(data.sale_type, customer, db)
        priced = price_lines(
            db,
            items=data.items,
            store_id=data.store_id,
            currency=data.currency,
            tier=tier,
            quote=True,
            tax_policy=tax_policy_for(db, data.store_id),
            cashier=cashier,
            customer=customer,
        )
        if (
            data.subtotal_cents != priced.subtotal_cents
            or data.tax_cents != priced.tax_cents
            or data.total_cents != priced.total_cents
        ):
            raise SyncRejected("Quote totals do not match line items.")

        serial_ids: list[uuid.UUID | None] = []
        seen: set[uuid.UUID] = set()
        for line in priced.lines:
            item = line.item
            if item.serial_kind is None or item.serial_value is None:
                serial_ids.append(None)
                continue
            _, serial = sellable_serial(
                db, product=line.product, store_id=data.store_id, kind=item.serial_kind, raw_value=item.serial_value
            )
            if serial is None or serial.status != "in_stock":
                raise SyncRejected(f"{item.serial_value} is not in stock at this branch.")
            if serial.id in seen:
                raise SyncRejected(f"{item.serial_value} appears twice on the quote.")
            seen.add(serial.id)
            serial_ids.append(serial.id)

        held: dict[uuid.UUID, int] = defaultdict(int)
        for line in priced.lines:
            held[line.product.id] += line.item.quantity
        for product_id, quantity in held.items():
            inventory.reserve(db, product_id, data.store_id, quantity)
    except SyncRejected as exc:
        db.rollback()
        raise _rejected(exc) from exc

    now = datetime.now(UTC)
    quote = Sale(
        id=data.id,
        store_id=data.store_id,
        cashier_id=data.cashier_id,
        status="quote",
        currency=data.currency,
        payment_method="cash",
        subtotal_cents=data.subtotal_cents,
        tax_cents=data.tax_cents,
        total_cents=data.total_cents,
        client_sale_id=str(data.id),
        invoice_number=next_server_number(db, data.store_id, "QUO"),
        sale_type=data.sale_type,
        customer_id=customer.id if customer is not None else None,
        is_quote_proforma=True,
        quote_expiry_date=now + timedelta(days=data.valid_days),
        quote_status="OPEN",
        quote_kind=data.quote_kind,
        payment_status="ON_ACCOUNT_UNPAID",
        amount_paid_cents=0,
        due_balance_cents=data.total_cents,
        created_at=now,
        updated_at=now,
    )
    db.add(quote)
    db.flush()
    for line, serial_id in zip(priced.lines, serial_ids, strict=True):
        item = line.item
        db.add(
            SaleItem(
                id=item.id,
                sale_id=data.id,
                product_id=item.product_id,
                serial_number_id=serial_id,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                line_total_cents=item.line_total_cents,
                unit_type=item.unit_type,
                unit_factor=uom_service.factor_of(db, item.unit_type) or 1,
                list_price_cents=item.list_price_cents,
                price_override_by_id=line.approver.id if line.approver is not None else None,
                tax_rate_bps=line.tax_rate_bps,
                description=(item.description or "").strip() or None,
            )
        )
        if line.approver is not None and item.price_override is not None:
            audit(
                db,
                store_id=data.store_id,
                actor_id=data.cashier_id,
                approver_id=line.approver.id,
                action="price_override",
                entity_id=data.id,
                details={
                    "quote": True,
                    "product_id": str(line.product.id),
                    "list_price_cents": item.list_price_cents,
                    "unit_price_cents": item.unit_price_cents,
                },
                reason=item.price_override.note,
            )
    if data.deposit is not None:
        try:
            _take_payment(db, quote, data.deposit, data.cashier_id)
        except SyncRejected as exc:
            db.rollback()
            raise _rejected(exc) from exc
    db.commit()
    return quote_detail(db, settings, data.id, None)


def cancel_quote(db: Session, settings: Settings, quote_id: uuid.UUID, store_scope: uuid.UUID | None) -> QuoteOut:
    expire_quotes(db)
    quote = _load(db, quote_id)
    if store_scope is not None and quote.store_id != store_scope:
        raise ApiError(404, "not_found", "Quote was not found.")
    if quote.quote_status != "OPEN":
        raise ApiError(422, "quote_closed", f"This quote is already {str(quote.quote_status).lower()}.")
    _release(db, quote)
    quote.quote_status = "CANCELLED"
    for deposit in _active_deposits(db, quote.id):
        deposit.status = "REFUND_DUE"
    db.commit()
    return quote_detail(db, settings, quote.id, None)


def _split_tax(total: int, units: int) -> list[int]:
    base, remainder = divmod(total, units)
    return [base + (1 if index < remainder else 0) for index in range(units)]


def _free_serials(
    db: Session, settings: Settings, quote: Sale, product_id: uuid.UUID, count: int, taken: set[uuid.UUID]
) -> list[SerialNumber]:
    candidates = db.scalars(
        select(SerialNumber)
        .where(
            SerialNumber.product_id == product_id,
            SerialNumber.store_id == quote.store_id,
            SerialNumber.status == "in_stock",
        )
        .order_by(SerialNumber.created_at, SerialNumber.id)
    ).all()
    chosen: list[SerialNumber] = []
    for serial in candidates:
        if len(chosen) == count:
            break
        if serial.id in taken or held_by_quote(db, serial.id, except_quote=quote.id) is not None:
            continue
        chosen.append(serial)
        taken.add(serial.id)
    if len(chosen) < count:
        product = db.get(Product, product_id)
        name = product.name if product is not None else "this product"
        raise SyncRejected(f"Only {len(chosen)} {name} units with IMEIs are free at this branch; {count} are needed.")
    return chosen


def convert_quote(
    db: Session,
    settings: Settings,
    quote_id: uuid.UUID,
    data: QuoteConvert,
    *,
    cashier_id: uuid.UUID,
    store_scope: uuid.UUID | None,
) -> QuoteOut:
    """Turns an open quote into a completed sale at the quoted prices, assigning free IMEIs where needed."""
    expire_quotes(db)
    quote = _load(db, quote_id)
    if store_scope is not None and quote.store_id != store_scope:
        raise ApiError(404, "not_found", "Quote was not found.")
    if quote.quote_status != "OPEN":
        raise ApiError(422, "quote_closed", f"This quote is already {str(quote.quote_status).lower()}.")

    try:
        _release(db, quote)
        policy = tax_policy_for(db, quote.store_id)
        taken = {item.serial_number_id for item in quote.items if item.serial_number_id is not None}
        items: list[SaleItemPayload] = []
        for item in quote.items:
            product = db.get(Product, item.product_id)
            if product is None:
                raise SyncRejected("A quoted product no longer exists.")
            override = (
                PriceOverridePayload(approved_by_id=item.price_override_by_id, note="Approved on the quote")
                if item.price_override_by_id is not None
                else None
            )
            common = {
                "product_id": item.product_id,
                "unit_price_cents": item.unit_price_cents,
                "list_price_cents": item.list_price_cents,
                "price_override": override,
                "description": item.description,
            }
            if not product.is_serialized:
                items.append(
                    SaleItemPayload(
                        id=uuid.uuid4(),
                        quantity=item.quantity,
                        tax_cents=item.tax_cents,
                        line_total_cents=item.line_total_cents,
                        unit_type=item.unit_type,  # type: ignore[arg-type]
                        **common,
                    )
                )
                continue
            serials = (
                [item.serial_number]
                if item.serial_number is not None
                else _free_serials(db, settings, quote, item.product_id, item.quantity, taken)
            )
            if policy.enforced:
                unit = line_tax(
                    item.unit_price_cents,
                    1,
                    policy.rate_for(product.tax_category),
                    inclusive=entered_includes_tax(product),
                )
                taxes = [unit.tax_cents] * len(serials)
                totals = [unit.line_total_cents] * len(serials)
            else:
                taxes = _split_tax(item.tax_cents, len(serials))
                totals = [item.unit_price_cents + tax for tax in taxes]
            for serial, tax, line_total in zip(serials, taxes, totals, strict=True):
                items.append(
                    SaleItemPayload(
                        id=uuid.uuid4(),
                        quantity=1,
                        tax_cents=tax,
                        line_total_cents=line_total,
                        serial_value=decrypt_value(serial.value_encrypted, settings),
                        serial_kind=serial.kind,  # type: ignore[arg-type]
                        **common,
                    )
                )
        # Splitting a quoted quantity into one line per IMEI re-rounds VAT per unit, which can move the
        # total by a few fils; the last tender absorbs that difference.
        tax_total = sum(line.tax_cents for line in items)
        grand_total = sum(line.line_total_cents for line in items)
        tenders = list(data.tenders) if data.tenders else None
        deposits = _active_deposits(db, quote.id)
        deposited = sum(row.amount_cents for row in deposits)
        if deposited:
            due = grand_total - deposited
            paying = sum(tender.amount_cents for tender in tenders or [])
            if tenders is None and due > 0:
                tenders = [SaleTenderPayload(method=data.payment_method, amount_cents=due)]
            elif tenders is not None and paying != quote.total_cents - deposited:
                raise SyncRejected(f"Collect the remaining balance of {quote.total_cents - deposited} cents.")
            tenders = [SaleTenderPayload(method="deposit", amount_cents=deposited), *(tenders or [])]
        if tenders and grand_total != quote.total_cents:
            drift = grand_total - quote.total_cents
            last = tenders[-1]
            if last.amount_cents + drift < 1:
                raise SyncRejected("The converted total changed; re-enter the tenders.")
            tenders[-1] = last.model_copy(update={"amount_cents": last.amount_cents + drift})
        if tenders is None and grand_total:
            tenders = [SaleTenderPayload(method=data.payment_method, amount_cents=grand_total)]
        sale_id = data.sale_id or uuid.uuid4()
        method = data.payment_method
        if tenders and all(tender.method != method for tender in tenders):
            method = tenders[-1].method
        payload = SalePayload(
            id=sale_id,
            store_id=quote.store_id,
            cashier_id=cashier_id,
            currency=quote.currency,
            payment_method=method,
            subtotal_cents=grand_total - tax_total,
            tax_cents=tax_total,
            total_cents=grand_total,
            client_sale_id=str(sale_id),
            items=items,
            sale_type=quote.sale_type,  # type: ignore[arg-type]
            customer_id=quote.customer_id,
            tenders=tenders,
            credit_override=data.credit_override,
        )
        record_sale(db, settings, payload, except_quote=quote.id)
    except SyncRejected as exc:
        db.rollback()
        raise _rejected(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise ApiError(422, "invalid_request", str(exc)) from exc
    quote.quote_status = "CONVERTED"
    quote.converted_sale_id = sale_id
    for deposit in deposits:
        deposit.status = "APPLIED"
    db.commit()
    return quote_detail(db, settings, quote.id, None)


# --- PDF -----------------------------------------------------------------------------------------


def _money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{currency} {abs(cents) / 100:,.2f}"


class _QuotePdf(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=22)
        if FONT_PATH.exists():
            self.add_font("Archivo", "", str(FONT_PATH), variations={"wght": 400})
            self.add_font("Archivo", "B", str(FONT_PATH), variations={"wght": 650})
            self.family = "Archivo"
        else:
            self.family = "Helvetica"
        self.footer_note = ""

    def font(self, size: float, bold: bool = False, color: tuple[int, int, int] = CHARCOAL) -> None:
        self.set_font(self.family, "B" if bold else "", size)
        self.set_text_color(*color)

    def footer(self) -> None:
        self.set_y(-16)
        self.font(8, color=MUTED)
        self.cell(0, 5, self.footer_note, align="L")
        self.cell(0, 5, f"Page {self.page_no()}", align="R")


def render_quote_pdf(db: Session, settings: Settings, quote_id: uuid.UUID, store_scope: uuid.UUID | None) -> bytes:
    expire_quotes(db)
    quote = _load(db, quote_id)
    if store_scope is not None and quote.store_id != store_scope:
        raise ApiError(404, "not_found", "Quote was not found.")
    store = db.get(Store, quote.store_id)
    customer = db.get(Customer, quote.customer_id) if quote.customer_id is not None else None
    cashier = db.get(User, quote.cashier_id)
    currency = quote.currency
    number = quote_number(quote)
    created = as_utc(quote.created_at)
    expires = as_utc(quote.quote_expiry_date) if quote.quote_expiry_date is not None else None

    pdf = _QuotePdf()
    pdf.footer_note = "Proforma quotation. Not a tax invoice. Stock is held until the validity date."
    pdf.set_title(f"Proforma quotation {number}")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    # Brand mark and title
    pdf.set_fill_color(*ACCENT)
    pdf.ellipse(pdf.l_margin, 16, 12, 12, style="F")
    pdf.set_xy(pdf.l_margin, 19.2)
    pdf.font(10, bold=True, color=(255, 255, 255))
    pdf.cell(12, 5.6, "ai", align="C")
    pdf.set_xy(pdf.l_margin + 16, 15.5)
    pdf.font(8, color=MUTED)
    pdf.cell(80, 5, (store.name if store is not None else "AI POS").upper())
    pdf.set_xy(pdf.l_margin + 16, 20.5)
    pdf.font(18, bold=True)
    pdf.cell(80, 8, "Proforma quotation")

    pdf.set_xy(pdf.w - pdf.r_margin - 70, 15.5)
    pdf.set_fill_color(*CHARCOAL)
    pdf.font(11, bold=True, color=(255, 255, 255))
    pdf.cell(70, 9, number, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.w - pdf.r_margin - 70)
    pdf.font(8, color=MUTED)
    status = str(quote.quote_status or "").title()
    pdf.cell(70, 6, f"{status} · Issued {created:%d %b %Y}", align="C")

    # From / bill to / validity
    pdf.set_y(38)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    top = pdf.get_y()
    column = width / 3

    def block(x: float, title: str, lines: list[str]) -> None:
        pdf.set_xy(x, top)
        pdf.font(7.5, bold=True, color=MUTED)
        pdf.cell(column - 4, 5, title.upper(), new_x="LEFT", new_y="NEXT")
        for index, text in enumerate(item for item in lines if item):
            pdf.set_x(x)
            pdf.font(10 if index == 0 else 8.5, bold=index == 0, color=CHARCOAL if index == 0 else MUTED)
            pdf.multi_cell(column - 4, 4.6, text, new_x="LEFT", new_y="NEXT")

    block(
        pdf.l_margin,
        "From",
        [
            store.name if store is not None else "",
            store.address or "" if store is not None else "",
            store.phone or "" if store is not None else "",
        ],
    )
    block(
        pdf.l_margin + column,
        "Bill to",
        [
            (customer.company_name or customer.name) if customer is not None else "Walk-in customer",
            customer.name if customer is not None and customer.company_name else "",
            f"TRN {customer.trn_vat_number}" if customer is not None and customer.trn_vat_number else "",
            customer.phone or "" if customer is not None else "",
        ],
    )
    block(
        pdf.l_margin + column * 2,
        "Validity",
        [
            f"Valid until {expires:%d %b %Y}" if expires is not None else "Open",
            f"{quote.sale_type.title()} pricing",
            f"Prepared by {cashier.full_name}" if cashier is not None else "",
        ],
    )

    # Line items
    pdf.set_y(max(pdf.get_y(), top + 26) + 4)
    widths = [8, width - 8 - 22 - 16 - 30 - 24 - 32, 22, 16, 30, 24, 32]
    headers = ["#", "Item", "Unit", "Qty", "Unit price", "Tax", "Amount"]

    def table_header() -> None:
        pdf.set_fill_color(*SURFACE)
        pdf.font(7.5, bold=True, color=MUTED)
        for index, (label, cell_width) in enumerate(zip(headers, widths, strict=True)):
            pdf.cell(cell_width, 8, label.upper(), fill=True, align="L" if index < 3 else "R")
        pdf.ln(8)

    table_header()
    row_height = 11

    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in quote.items})))
    }
    for position, item in enumerate(quote.items, start=1):
        product = products.get(item.product_id)
        name = product.name if product is not None else "Unknown product"
        detail = product.sku if product is not None else ""
        if item.serial_number is not None:
            detail = f"{detail} · IMEI {decrypt_value(item.serial_number.value_encrypted, settings)}"
        factor = item.unit_factor or uom_service.factor_of(db, item.unit_type) or 1
        unit_label = "Pcs" if item.unit_type == uom_service.PIECE else uom_service.label(db, item.unit_type)
        packs = item.quantity // factor
        if pdf.get_y() + row_height > pdf.page_break_trigger:
            pdf.add_page()
            table_header()
        pdf.font(9, color=MUTED)
        pdf.cell(widths[0], 6, str(position))
        pdf.font(9.5, bold=True)
        pdf.cell(widths[1], 6, name[:60])
        pdf.font(9, color=MUTED)
        pdf.cell(widths[2], 6, unit_label)
        pdf.font(9.5)
        pdf.cell(widths[3], 6, f"{packs:,}" if factor > 1 else f"{item.quantity:,}", align="R")
        pdf.cell(widths[4], 6, _money(item.unit_price_cents * factor, currency), align="R")
        pdf.cell(widths[5], 6, _money(item.tax_cents, currency), align="R")
        pdf.font(9.5, bold=True)
        pdf.cell(widths[6], 6, _money(item.line_total_cents, currency), align="R")
        pdf.ln(5)
        pdf.set_x(pdf.l_margin + widths[0])
        pdf.font(7.5, color=MUTED)
        suffix = f" · {item.quantity:,} pcs" if factor > 1 else ""
        pdf.cell(widths[1] + widths[2], 4, f"{detail}{suffix}"[:90])
        pdf.ln(5)
        pdf.set_draw_color(*LINE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(1)

    # Totals
    pdf.ln(4)
    box_width = 78
    x = pdf.w - pdf.r_margin - box_width
    if pdf.get_y() + 36 > pdf.page_break_trigger:
        pdf.add_page()
    top = pdf.get_y()
    pdf.set_fill_color(*CHARCOAL)
    pdf.rect(x, top, box_width, 29, style="F", round_corners=True, corner_radius=4)
    rows = [("Subtotal", quote.subtotal_cents), ("Tax", quote.tax_cents)]
    pdf.set_xy(x + 6, top + 4)
    for label, value in rows:
        pdf.set_x(x + 6)
        pdf.font(9, color=(190, 188, 194))
        pdf.cell(box_width / 2 - 6, 6, label)
        pdf.font(9.5, color=(255, 255, 255))
        pdf.cell(box_width / 2 - 6, 6, _money(value, currency), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x + 6)
    pdf.font(12, bold=True, color=(255, 255, 255))
    pdf.cell(box_width / 2 - 6, 10, "Total")
    pdf.set_text_color(*ACCENT)
    pdf.cell(box_width / 2 - 6, 10, _money(quote.total_cents, currency), align="R")

    pdf.set_xy(pdf.l_margin, top)
    pdf.font(7.5, bold=True, color=MUTED)
    pdf.cell(width - box_width - 8, 5, "TERMS", new_x="LMARGIN", new_y="NEXT")
    pdf.font(8.5, color=MUTED)
    terms = (
        "Prices are per piece unless a pack is shown. Quantities and IMEIs listed are reserved for you until the "
        "validity date. Payment terms follow your account agreement."
    )
    if customer is not None and customer.payment_terms != "DUE_ON_RECEIPT":
        terms += f" Account terms: {customer.payment_terms.replace('_', ' ').title()}."
    pdf.multi_cell(width - box_width - 8, 4.4, terms)

    return bytes(pdf.output())
