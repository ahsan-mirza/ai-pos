"""A4 bilingual (English / Arabic) tax invoices and credit notes.

The business's tax authority adapter decides full vs simplified (UAE FTA: buyer TRN or a total over AED 10,000;
ZATCA: buyer VAT number). When the authority issues e-invoices, its QR code is printed beside the totals."""

import io
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import segno
from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value
from app.models.customer import Customer
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.services.ledger_service import as_utc
from app.services.settings_service import cached_settings, pos_policy
from app.tax_authority import adapter_for, einvoice_for

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
ACCENT = (253, 55, 6)
CHARCOAL = (34, 32, 38)
MUTED = (122, 120, 126)
LINE = (232, 229, 225)
SURFACE = (247, 245, 242)
LEGAL_NOTES = {
    "fta": "VAT charged under UAE Federal Decree-Law No. 8 of 2017.",
    "zatca": "VAT charged under the KSA VAT Law. E-invoice issued under ZATCA Fatoora requirements.",
}
COUNTRY_NAMES = {"AE": "United Arab Emirates", "SA": "Saudi Arabia"}

EMIRATES = {
    "AUH": "Abu Dhabi",
    "DXB": "Dubai",
    "SHJ": "Sharjah",
    "AJM": "Ajman",
    "UAQ": "Umm Al Quwain",
    "RAK": "Ras Al Khaimah",
    "FUJ": "Fujairah",
}


def money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{currency} {abs(cents) / 100:,.2f}"


def invoice_kind(db: Session, total_cents: int, customer: Customer | None) -> str:
    """'FULL' or 'SIMPLIFIED' under the business's tax authority."""
    return adapter_for(db).invoice_kind(total_cents, customer.trn_vat_number if customer is not None else None)


def qr_png(payload: str) -> io.BytesIO:
    image = io.BytesIO()
    segno.make(payload, error="m").save(image, kind="png", scale=8, border=2)
    image.seek(0)
    return image


class _Pdf(FPDF):
    def __init__(self, footer_note: str) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=22)
        latin = FONTS / "Archivo.ttf"
        arabic = FONTS / "NotoNaskhArabic.ttf"
        self.latin = "Archivo" if latin.exists() else "Helvetica"
        if latin.exists():
            self.add_font("Archivo", "", str(latin), variations={"wght": 400})
            self.add_font("Archivo", "B", str(latin), variations={"wght": 650})
        self.has_arabic = arabic.exists()
        if self.has_arabic:
            self.add_font("Naskh", "", str(arabic))
        self.footer_note = footer_note

    def font(self, size: float, bold: bool = False, color: tuple[int, int, int] = CHARCOAL) -> None:
        self.set_text_shaping(False)
        self.set_font(self.latin, "B" if bold else "", size)
        self.set_text_color(*color)

    def arabic(self, size: float, color: tuple[int, int, int] = MUTED) -> bool:
        if not self.has_arabic:
            return False
        self.set_font("Naskh", "", size)
        self.set_text_shaping(True)
        self.set_text_color(*color)
        return True

    def footer(self) -> None:
        self.set_y(-16)
        self.font(8, color=MUTED)
        self.cell(0, 5, self.footer_note, align="L")
        self.cell(0, 5, f"Page {self.page_no()}", align="R")


@dataclass
class _Line:
    name: str
    detail: str
    quantity: int
    unit_cents: int
    rate_bps: int | None
    tax_cents: int
    total_cents: int


def _document(
    *,
    title_en: str,
    title_ar: str,
    number: str,
    issued: str,
    reference: str | None,
    store: Store,
    customer: Customer | None,
    full: bool,
    lines: list[_Line],
    subtotal: int,
    tax: int,
    total: int,
    currency: str,
    settings_row: object,
    note: str,
    authority: str = "fta",
    country: str = "AE",
    qr: str | None = None,
) -> bytes:
    legal = getattr(settings_row, "legal_name", None) or store.name
    legal_ar = getattr(settings_row, "legal_name_ar", None)
    trn = getattr(settings_row, "trn", None)
    pdf = _Pdf(note)
    pdf.set_title(f"{title_en} {number}")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_fill_color(*ACCENT)
    pdf.ellipse(pdf.l_margin, 16, 12, 12, style="F")
    pdf.set_xy(pdf.l_margin, 19.2)
    pdf.font(10, bold=True, color=(255, 255, 255))
    pdf.cell(12, 5.6, "ai", align="C")
    pdf.set_xy(pdf.l_margin + 16, 15.5)
    pdf.font(8, color=MUTED)
    pdf.cell(90, 5, legal.upper())
    pdf.set_xy(pdf.l_margin + 16, 20.5)
    pdf.font(18, bold=True)
    pdf.cell(80, 8, title_en)
    if pdf.arabic(13, CHARCOAL):
        pdf.set_xy(pdf.l_margin + 16, 28.5)
        pdf.cell(80, 6, title_ar)

    pdf.set_xy(pdf.w - pdf.r_margin - 72, 15.5)
    pdf.set_fill_color(*CHARCOAL)
    pdf.font(11, bold=True, color=(255, 255, 255))
    pdf.cell(72, 9, number, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.w - pdf.r_margin - 72)
    pdf.font(8, color=MUTED)
    pdf.cell(72, 6, f"Issued {issued}" + (f" · Ref {reference}" if reference else ""), align="C")

    pdf.set_y(40)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    top = pdf.get_y()
    column = width / 2

    def block(x: float, title: str, rows: list[str]) -> None:
        pdf.set_xy(x, top)
        pdf.font(7.5, bold=True, color=MUTED)
        pdf.cell(column - 4, 5, title.upper(), new_x="LEFT", new_y="NEXT")
        for index, text in enumerate(row for row in rows if row):
            pdf.set_x(x)
            pdf.font(10 if index == 0 else 8.5, bold=index == 0, color=CHARCOAL if index == 0 else MUTED)
            pdf.multi_cell(column - 4, 4.6, text, new_x="LEFT", new_y="NEXT")

    region = EMIRATES.get(store.emirate or "", "") if country == "AE" else ""
    tax_id = "TRN" if country == "AE" else "VAT No."
    block(
        pdf.l_margin,
        "Supplier",
        [
            legal,
            store.address or "",
            ", ".join(item for item in (region, COUNTRY_NAMES.get(country, country)) if item),
            f"{tax_id} {trn}" if trn else f"{tax_id} not registered",
        ],
    )
    if full and customer is not None:
        block(
            pdf.l_margin + column,
            "Recipient",
            [
                customer.company_name or customer.name,
                customer.address or "",
                f"{tax_id} {customer.trn_vat_number}" if customer.trn_vat_number else "Not VAT registered",
                customer.phone or "",
            ],
        )
    elif customer is not None:
        block(pdf.l_margin + column, "Customer", [customer.company_name or customer.name, customer.phone or ""])
    if legal_ar and pdf.arabic(10, CHARCOAL):
        pdf.set_xy(pdf.l_margin, top + 26)
        pdf.cell(column - 4, 5, legal_ar)

    pdf.set_y(top + 34)
    widths = [8, width - 8 - 16 - 30 - 18 - 26 - 30, 16, 30, 18, 26, 30]
    headers = ["#", "Description", "Qty", "Unit price", "VAT %", "VAT", "Amount"]

    def header() -> None:
        pdf.set_fill_color(*SURFACE)
        pdf.font(7.5, bold=True, color=MUTED)
        for index, (label, cell_width) in enumerate(zip(headers, widths, strict=True)):
            pdf.cell(cell_width, 8, label.upper(), fill=True, align="L" if index < 2 else "R")
        pdf.ln(8)

    header()
    for position, item in enumerate(lines, start=1):
        if pdf.get_y() + 11 > pdf.page_break_trigger:
            pdf.add_page()
            header()
        pdf.font(9, color=MUTED)
        pdf.cell(widths[0], 6, str(position))
        pdf.font(9.5, bold=True)
        pdf.cell(widths[1], 6, item.name[:58])
        pdf.font(9.5)
        pdf.cell(widths[2], 6, f"{item.quantity:,}", align="R")
        pdf.cell(widths[3], 6, money(item.unit_cents, currency), align="R")
        pdf.cell(widths[4], 6, f"{(item.rate_bps or 0) / 100:g}%" if item.rate_bps is not None else "-", align="R")
        pdf.cell(widths[5], 6, money(item.tax_cents, currency), align="R")
        pdf.font(9.5, bold=True)
        pdf.cell(widths[6], 6, money(item.total_cents, currency), align="R")
        pdf.ln(5)
        pdf.set_x(pdf.l_margin + widths[0])
        pdf.font(7.5, color=MUTED)
        pdf.cell(widths[1], 4, item.detail[:90])
        pdf.ln(5)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(1)

    pdf.ln(4)
    if pdf.get_y() + 36 > pdf.page_break_trigger:
        pdf.add_page()
    box = 84
    x = pdf.w - pdf.r_margin - box
    top = pdf.get_y()
    pdf.set_fill_color(*CHARCOAL)
    pdf.rect(x, top, box, 29, style="F", round_corners=True, corner_radius=4)
    pdf.set_xy(x + 6, top + 4)
    for label, value in (("Total excl. VAT", subtotal), ("VAT", tax)):
        pdf.set_x(x + 6)
        pdf.font(9, color=(190, 188, 194))
        pdf.cell(box / 2 - 6, 6, label)
        pdf.font(9.5, color=(255, 255, 255))
        pdf.cell(box / 2 - 6, 6, money(value, currency), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x + 6)
    pdf.font(12, bold=True, color=(255, 255, 255))
    pdf.cell(box / 2 - 6, 10, "Total")
    pdf.set_text_color(*ACCENT)
    pdf.cell(box / 2 - 6, 10, money(total, currency), align="R")
    pdf.set_xy(pdf.l_margin, top)
    pdf.font(7.5, bold=True, color=MUTED)
    pdf.cell(
        width - box - 8, 5, "FULL TAX INVOICE" if full else "SIMPLIFIED TAX INVOICE", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.font(8.5, color=MUTED)
    text_width = width - box - 8 - (34 if qr else 0)
    pdf.multi_cell(
        text_width,
        4.4,
        f"Amounts in {currency}. {LEGAL_NOTES.get(authority, '')}".strip() if trn else f"Amounts in {currency}.",
    )
    if qr:
        pdf.image(qr_png(qr), x=x - 34, y=top, w=29, h=29)
    return bytes(pdf.output())


def _product_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Product]:
    if not ids:
        return {}
    return {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(ids)))}


def render_sale_invoice(db: Session, settings: Settings, sale_id: uuid.UUID, store_scope: uuid.UUID | None) -> bytes:
    sale = (
        db.scalars(
            select(Sale)
            .options(selectinload(Sale.items).selectinload(SaleItem.serial_number))
            .where(Sale.id == sale_id, Sale.is_quote_proforma.is_(False))
        )
        .unique()
        .one_or_none()
    )
    if sale is None or (store_scope is not None and sale.store_id != store_scope):
        raise ApiError(404, "not_found", "Sale was not found.")
    store = db.get(Store, sale.store_id)
    assert store is not None
    customer = db.get(Customer, sale.customer_id) if sale.customer_id else None
    products = _product_names(db, {item.product_id for item in sale.items})
    lines = []
    for item in sale.items:
        product = products.get(item.product_id)
        detail = product.sku if product is not None else ""
        if item.serial_number is not None:
            detail = f"{detail} · IMEI {decrypt_value(item.serial_number.value_encrypted, settings)}"
        lines.append(
            _Line(
                name=item.description or (product.name if product is not None else "Item"),
                detail=detail,
                quantity=item.quantity,
                unit_cents=item.unit_price_cents,
                rate_bps=item.tax_rate_bps,
                tax_cents=item.tax_cents,
                total_cents=item.line_total_cents,
            )
        )
    adapter = adapter_for(db)
    full = invoice_kind(db, sale.total_cents, customer) == "FULL"
    einvoice = einvoice_for(db, "sale", sale.id)
    simplified_title = adapter.code == "zatca" and not full
    return _document(
        title_en="Simplified Tax Invoice" if simplified_title else "Tax Invoice",
        title_ar="فاتورة ضريبية مبسطة" if simplified_title else "فاتورة ضريبية",
        number=sale.invoice_number or sale.client_sale_id[:8].upper(),
        issued=f"{as_utc(sale.created_at):%d %b %Y %H:%M}",
        reference=None,
        store=store,
        customer=customer,
        full=full,
        lines=lines,
        subtotal=sale.subtotal_cents,
        tax=sale.tax_cents,
        total=sale.total_cents,
        currency=sale.currency,
        settings_row=cached_settings(db),
        note="Tax invoice. Keep it for returns and warranty claims.",
        authority=adapter.code,
        country=adapter.country,
        qr=einvoice.qr if einvoice is not None else None,
    )


def render_gift_receipt(db: Session, sale_id: uuid.UUID, store_scope: uuid.UUID | None) -> bytes:
    """A4 gift receipt: items, sizes and quantities without any price, the exchange-by date from the returns policy,
    and the sale's receipt code as a QR the returns desk scans."""
    sale = db.scalars(
        select(Sale).options(selectinload(Sale.items)).where(Sale.id == sale_id, Sale.is_quote_proforma.is_(False))
    ).one_or_none()
    if sale is None or (store_scope is not None and sale.store_id != store_scope):
        raise ApiError(404, "not_found", "Sale was not found.")
    store = db.get(Store, sale.store_id)
    assert store is not None
    rules = pos_policy(db).returns
    exchange_by = as_utc(sale.created_at) + timedelta(days=rules.window_days + rules.exchange_window_days)
    products = _product_names(db, {item.product_id for item in sale.items})
    legal = getattr(cached_settings(db), "legal_name", None) or store.name

    pdf = _Pdf("Gift receipt. Prices are not shown.")
    pdf.set_title(f"Gift receipt {sale.invoice_number or sale.client_sale_id[:8].upper()}")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_fill_color(*ACCENT)
    pdf.ellipse(pdf.l_margin, 16, 12, 12, style="F")
    pdf.set_xy(pdf.l_margin + 16, 15.5)
    pdf.font(8, color=MUTED)
    pdf.cell(90, 5, legal.upper())
    pdf.set_xy(pdf.l_margin + 16, 20.5)
    pdf.font(20, bold=True)
    pdf.cell(80, 9, "A gift for you")
    pdf.set_xy(pdf.w - pdf.r_margin - 42, 14)
    pdf.image(qr_png(sale.client_sale_id), w=36, h=36)
    pdf.set_xy(pdf.l_margin + 16, 31)
    pdf.font(9, color=MUTED)
    pdf.cell(100, 5, f"{store.name} · {as_utc(sale.created_at):%d %b %Y}")
    pdf.set_xy(pdf.l_margin + 16, 37)
    pdf.font(10, bold=True, color=ACCENT)
    pdf.cell(100, 5, f"Exchange by {exchange_by:%d %b %Y}")
    pdf.set_y(56)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    for item in sale.items:
        if item.gift_card_code is not None:
            continue
        product = products.get(item.product_id)
        name = item.description or (product.name if product is not None else "Item")
        variant = " · ".join((product.variant_attributes or {}).values()) if product is not None else ""
        pdf.font(11, bold=True)
        pdf.cell(width - 24, 7, name[:70])
        pdf.font(11)
        pdf.cell(24, 7, f"x {item.quantity:,}", align="R", new_x="LMARGIN", new_y="NEXT")
        if variant:
            pdf.font(8.5, color=MUTED)
            pdf.cell(width, 5, variant[:90], new_x="LMARGIN", new_y="NEXT")
        pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.w - pdf.r_margin, pdf.get_y() + 1)
        pdf.ln(3)
    pdf.ln(6)
    pdf.font(9, color=MUTED)
    pdf.multi_cell(
        width,
        4.8,
        "Bring this receipt to any of our branches to exchange or return. The code above finds the purchase "
        "without showing what it cost; refunds go to store credit.",
    )
    return bytes(pdf.output())


def render_credit_note(db: Session, settings: Settings, return_id: uuid.UUID, store_scope: uuid.UUID | None) -> bytes:
    record = db.get(SaleReturn, return_id)
    if record is None or (store_scope is not None and record.store_id != store_scope):
        raise ApiError(404, "not_found", "Return was not found.")
    sale = db.get(Sale, record.original_sale_id)
    store = db.get(Store, record.store_id)
    assert store is not None and sale is not None
    customer = db.get(Customer, sale.customer_id) if sale.customer_id else None
    items = list(db.scalars(select(ReturnItem).where(ReturnItem.return_id == record.id)).all())
    products = _product_names(db, {item.product_id for item in items})
    lines = [
        _Line(
            name=products[item.product_id].name if item.product_id in products else "Item",
            detail=item.condition_status.replace("_", " "),
            quantity=item.quantity,
            unit_cents=item.unit_price_cents,
            rate_bps=None,
            tax_cents=item.tax_refund_cents,
            total_cents=item.refund_cents,
        )
        for item in items
    ]
    adapter = adapter_for(db)
    einvoice = einvoice_for(db, "return", record.id)
    return _document(
        title_en="Tax Credit Note",
        title_ar="إشعار دائن ضريبي",
        number=record.credit_note_number or str(record.id)[:8].upper(),
        issued=f"{as_utc(record.created_at):%d %b %Y %H:%M}",
        reference=sale.invoice_number,
        store=store,
        customer=customer,
        full=customer is not None and bool(customer.trn_vat_number),
        lines=lines,
        subtotal=record.total_refund_cents - record.tax_refund_cents,
        tax=record.tax_refund_cents,
        total=record.total_refund_cents,
        currency=record.currency,
        settings_row=cached_settings(db),
        note="Tax credit note against the referenced tax invoice.",
        authority=adapter.code,
        country=adapter.country,
        qr=einvoice.qr if einvoice is not None else None,
    )
