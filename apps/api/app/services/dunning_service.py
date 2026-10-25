"""Collections: statements of account (PDF over email, text on WhatsApp/SMS) and weekly overdue reminders."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.sale import Sale
from app.schemas.dunning import DunningResult
from app.services import customer_service, ledger_service, messaging_service
from app.services.invoice_pdf import _Pdf, money
from app.services.settings_service import business_currency, load_settings


def _business_name(db: Session) -> str:
    return load_settings(db).legal_name or "AI POS"


def render_statement(db: Session, customer_id: uuid.UUID) -> bytes:
    data = customer_service.statement(db, customer_id)
    customer = data.customer
    currency = data.currency
    pdf = _Pdf("Statement of account. Please quote the invoice numbers with your payment.")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.font(8, color=(122, 120, 126))
    pdf.cell(0, 5, _business_name(db).upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.font(18, bold=True)
    pdf.cell(0, 9, "Statement of account", new_x="LMARGIN", new_y="NEXT")
    pdf.font(10)
    pdf.cell(0, 6, customer.company_name or customer.name, new_x="LMARGIN", new_y="NEXT")
    pdf.font(9, color=(122, 120, 126))
    pdf.cell(
        0,
        5,
        f"{customer.code} · {datetime.now(UTC):%d %b %Y}"
        + (f" · TRN {customer.trn_vat_number}" if customer.trn_vat_number else ""),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    summary = [
        ("Balance", customer.current_balance_cents),
        ("Overdue", customer.overdue_cents),
        ("Credit limit", customer.credit_limit_cents),
    ]
    box = width / 3
    top = pdf.get_y()
    for index, (label, value) in enumerate(summary):
        x = pdf.l_margin + index * box
        pdf.set_fill_color(34, 32, 38) if index == 0 else pdf.set_fill_color(247, 245, 242)
        pdf.rect(x, top, box - 3, 18, style="F", round_corners=True, corner_radius=3)
        pdf.set_xy(x + 4, top + 3)
        pdf.font(8, color=(190, 188, 194) if index == 0 else (122, 120, 126))
        pdf.cell(box - 10, 4, label)
        pdf.set_xy(x + 4, top + 8)
        pdf.font(12, bold=True, color=(255, 255, 255) if index == 0 else (34, 32, 38))
        pdf.cell(box - 10, 7, money(value, currency))
    pdf.set_y(top + 24)
    widths = [32, 32, 32, 30, 30, width - 156]
    headers = ["Invoice", "Date", "Due", "Total", "Balance", "Status"]
    pdf.set_fill_color(247, 245, 242)
    pdf.font(8, bold=True, color=(122, 120, 126))
    for index, (label, cell) in enumerate(zip(headers, widths, strict=True)):
        pdf.cell(cell, 7, label.upper(), fill=True, align="R" if index in (3, 4) else "L")
    pdf.ln(7)
    for invoice in data.open_invoices:
        pdf.font(9)
        pdf.cell(widths[0], 6, invoice.invoice)
        pdf.cell(widths[1], 6, f"{invoice.created_at:%d %b %Y}")
        pdf.cell(widths[2], 6, f"{invoice.due_date:%d %b %Y}" if invoice.due_date else "—")
        pdf.cell(widths[3], 6, money(invoice.total_cents, currency), align="R")
        pdf.font(9, bold=True)
        pdf.cell(widths[4], 6, money(invoice.due_balance_cents, currency), align="R")
        overdue = invoice.days_overdue > 0
        pdf.font(9, bold=overdue, color=(220, 38, 38) if overdue else (122, 120, 126))
        pdf.cell(widths[5], 6, f"  {invoice.days_overdue} days overdue" if overdue else "  Current")
        pdf.ln(6)
    if not data.open_invoices:
        pdf.font(9, color=(122, 120, 126))
        pdf.cell(0, 8, "No open invoices. Thank you.", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _context(db: Session, customer: Customer) -> dict[str, object]:
    currency = business_currency(db)
    now = datetime.now(UTC)
    invoices = ledger_service.open_invoices(db, customer.id)
    overdue = [sale for sale in invoices if ledger_service.days_overdue(sale, now) > 0]
    return {
        "business": _business_name(db),
        "balance": money(customer.current_balance_cents, currency),
        "overdue": money(sum(sale.due_balance_cents for sale in overdue), currency),
        "days": max((ledger_service.days_overdue(sale, now) for sale in overdue), default=0),
        "_overdue_cents": sum(sale.due_balance_cents for sale in overdue),
    }


def send_statements(
    db: Session, customer_ids: list[uuid.UUID] | None, *, with_balance_only: bool = True
) -> DunningResult:
    """Queues statements. With no ids, every active wholesale account with a balance gets one."""
    query = select(Customer).where(Customer.is_active.is_(True))
    if customer_ids:
        query = query.where(Customer.id.in_(customer_ids))
    else:
        query = query.where(Customer.customer_type == "WHOLESALE")
    queued = skipped = 0
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
    for customer in db.scalars(query):
        if with_balance_only and customer.current_balance_cents <= 0 and not customer_ids:
            continue
        context = _context(db, customer)
        context.pop("_overdue_cents")
        message = messaging_service.enqueue(
            db,
            template_key="statement",
            customer=customer,
            context=context,
            dedupe_key=f"statement:{customer.id}:{stamp}",
            attachment=("statement", str(customer.id)),
        )
        if message is None or message.status == "SKIPPED":
            skipped += 1
        else:
            queued += 1
    db.commit()
    if customer_ids and queued == 0 and skipped == 0:
        raise ApiError(404, "not_found", "Customer was not found.")
    return DunningResult(queued=queued, skipped=skipped)


def send_layaway_reminders(db: Session, settings: Settings) -> int:
    """Weekly nudge for open layaways that still have a balance."""
    year, week, _ = datetime.now(UTC).isocalendar()
    currency = business_currency(db)
    queued = 0
    for quote in db.scalars(
        select(Sale).where(
            Sale.is_quote_proforma.is_(True),
            Sale.quote_kind == "LAYAWAY",
            Sale.quote_status == "OPEN",
            Sale.customer_id.is_not(None),
            Sale.due_balance_cents > 0,
        )
    ):
        customer = db.get(Customer, quote.customer_id)
        if customer is None:
            continue
        expires = quote.quote_expiry_date
        message = messaging_service.enqueue(
            db,
            template_key="layaway_reminder",
            customer=customer,
            context={
                "number": quote.invoice_number or str(quote.id)[:8].upper(),
                "balance": money(quote.due_balance_cents, currency),
                "expires": f"{expires:%d %b %Y}" if expires else "",
            },
            dedupe_key=f"layaway:{quote.id}:{year}-W{week:02d}",
        )
        queued += message is not None and message.status == "QUEUED"
    db.commit()
    return queued


def send_overdue_reminders(db: Session, settings: Settings) -> int:
    """At most one reminder per account per ISO week, only while invoices are overdue."""
    year, week, _ = datetime.now(UTC).isocalendar()
    queued = 0
    for customer in db.scalars(
        select(Customer).where(Customer.is_active.is_(True), Customer.current_balance_cents > 0)
    ):
        context = _context(db, customer)
        if context.pop("_overdue_cents") <= 0:
            continue
        message = messaging_service.enqueue(
            db,
            template_key="overdue_reminder",
            customer=customer,
            context=context,
            dedupe_key=f"overdue:{customer.id}:{year}-W{week:02d}",
        )
        queued += message is not None and message.status == "QUEUED"
    db.commit()
    return queued
