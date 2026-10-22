"""Shelf and swing-tag labels as a PDF: product name, variant (size / colour), shelf price including VAT where the
business prices that way, the barcode (EAN-13 when the code is a valid EAN-13, Code 128 otherwise) and the SKU.

Layouts: an A4 sheet of 24 labels (3 x 8, 70 x 37 mm, the common office-label stock) or one label per page on a
50 x 30 mm thermal roll."""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fpdf import FPDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch
from app.models.product import Product
from app.services import barcodes
from app.services.settings_service import business_currency
from app.services.tax import line_tax
from app.services.tax import policy as tax_policy

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_LABELS = 2000
Layout = Literal["a4_3x8", "roll_50x30"]


@dataclass(frozen=True)
class _Sheet:
    page: tuple[float, float]
    columns: int
    rows: int
    label: tuple[float, float]
    margin: tuple[float, float]
    gap: tuple[float, float]


SHEETS: dict[str, _Sheet] = {
    "a4_3x8": _Sheet(page=(210, 297), columns=3, rows=8, label=(70, 37), margin=(0, 0.5), gap=(0, 0)),
    "roll_50x30": _Sheet(page=(50, 30), columns=1, rows=1, label=(50, 30), margin=(0, 0), gap=(0, 0)),
}


@dataclass(frozen=True)
class LabelData:
    name: str
    variant: str
    price: str | None
    code: str
    sku: str


def _money(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:,.2f}"


def _variant_text(attributes: dict[str, str] | None) -> str:
    return " · ".join(value for value in (attributes or {}).values())


def label_data(db: Session, products: list[tuple[Product, int]], show_price: bool) -> list[LabelData]:
    tax = tax_policy(db)
    currency = business_currency(db)
    labels: list[LabelData] = []
    for product, copies in products:
        def shelf_of(cents: int) -> int:
            if tax.enforced and not tax.prices_include_vat:
                return line_tax(cents, 1, tax.rate_for(product.tax_category), inclusive=False).line_total_cents
            return cents

        shelf = shelf_of(product.price_cents)
        price = _money(shelf, currency) if show_price and not product.is_open_price else None
        was = product.compare_at_cents
        if price and was is not None and was > product.price_cents:
            price = f"{price}  was {_money(shelf_of(was), currency)}"
        data = LabelData(
            name=product.name,
            variant=_variant_text(product.variant_attributes),
            price=price,
            code=product.barcode,
            sku=product.sku,
        )
        labels.extend([data] * copies)
    if not labels:
        raise ApiError(422, "nothing_to_print", "Choose at least one product to label.")
    if len(labels) > MAX_LABELS:
        raise ApiError(422, "too_many_labels", f"Print at most {MAX_LABELS} labels at a time.")
    return labels


class _LabelPdf(FPDF):
    def __init__(self, sheet: _Sheet) -> None:
        super().__init__(unit="mm", format=sheet.page)
        self.set_margins(0, 0, 0)
        self.set_auto_page_break(False)
        latin = FONTS / "Archivo.ttf"
        self.family_name = "Archivo" if latin.exists() else "Helvetica"
        if latin.exists():
            self.add_font("Archivo", "", str(latin), variations={"wght": 400})
            self.add_font("Archivo", "B", str(latin), variations={"wght": 700})

    def text_at(
        self, x: float, y: float, width: float, size: float, text: str, *, bold: bool = False, align: str = "L"
    ) -> None:
        self.set_font(self.family_name, "B" if bold else "", size)
        while size > 4 and self.get_string_width(text) > width:
            size -= 0.5
            self.set_font(self.family_name, "B" if bold else "", size)
        self.set_xy(x, y)
        self.cell(width, size * 0.42, text, align=align)


def _bars(pdf: _LabelPdf, modules: str, x: float, y: float, width: float, height: float) -> None:
    module = width / len(modules)
    run = 0
    for index, bit in enumerate(modules + "0"):
        if bit == "1":
            run += 1
            continue
        if run:
            pdf.rect(x + (index - run) * module, y, run * module, height, style="F")
            run = 0


def _draw(pdf: _LabelPdf, label: LabelData, x: float, y: float, size: tuple[float, float]) -> None:
    width, height = size
    pad = 2.5 if width >= 60 else 2
    inner = width - pad * 2
    pdf.set_text_color(20, 20, 20)
    pdf.set_fill_color(0, 0, 0)
    pdf.text_at(x + pad, y + pad, inner, 7.5 if width >= 60 else 6.5, label.name[:60], bold=True)
    line = y + pad + 3.6
    if label.variant:
        pdf.text_at(x + pad, line, inner * 0.62, 6.5 if width >= 60 else 5.5, label.variant)
    if label.price:
        pdf.text_at(x + pad, line - 0.4, inner, 10 if width >= 60 else 8, label.price, bold=True, align="R")
    bar_top = line + 4.2
    bar_height = height - (bar_top - y) - pad - 3.2
    ean = barcodes.is_ean13(label.code)
    modules = barcodes.ean13_modules(label.code) if ean else barcodes.code128_modules(label.code)
    quiet = 11 if ean else 10
    total = len(modules) + quiet * 2
    bar_width = min(inner, total * (0.33 if width >= 60 else 0.3))
    left = x + (width - bar_width) / 2
    module = bar_width / total
    _bars(pdf, modules, left + quiet * module, bar_top, len(modules) * module, max(bar_height, 6))
    pdf.text_at(x + pad, bar_top + max(bar_height, 6) + 0.6, inner, 6 if width >= 60 else 5, label.code, align="C")
    if label.sku != label.code:
        pdf.set_text_color(110, 110, 110)
        pdf.text_at(x + pad, y + height - pad - 1.6, inner, 4.5, label.sku, align="R")


def render(labels: list[LabelData], layout: Layout) -> bytes:
    sheet = SHEETS[layout]
    pdf = _LabelPdf(sheet)
    pdf.set_title("Labels")
    per_page = sheet.columns * sheet.rows
    for index, label in enumerate(labels):
        slot = index % per_page
        if slot == 0:
            pdf.add_page()
        column, row = slot % sheet.columns, slot // sheet.columns
        x = sheet.margin[0] + column * (sheet.label[0] + sheet.gap[0])
        y = sheet.margin[1] + row * (sheet.label[1] + sheet.gap[1])
        _draw(pdf, label, x, y, sheet.label)
    return bytes(pdf.output())


def for_products(db: Session, items: list[tuple[uuid.UUID, int]], *, layout: Layout, show_price: bool) -> bytes:
    ids = [product_id for product_id, _ in items]
    products = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(ids)))}
    missing = [str(product_id) for product_id in ids if product_id not in products]
    if missing:
        raise ApiError(404, "not_found", f"{len(missing)} product(s) were not found.")
    return render(label_data(db, [(products[pid], copies) for pid, copies in items], show_price), layout)


def for_batch(db: Session, batch_id: uuid.UUID, *, layout: Layout, show_price: bool) -> bytes:
    """One label per unit received in the batch, in import order."""
    batch = db.get(PurchaseBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "Purchase batch was not found.")
    items = list(db.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id).order_by(BatchItem.position)).all())
    products = {
        row.id: row for row in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in items})))
    }
    pairs = [(products[item.product_id], item.quantity_imported) for item in items if item.quantity_imported > 0]
    return render(label_data(db, pairs, show_price), layout)


def for_model(db: Session, model_id: uuid.UUID, *, layout: Layout, show_price: bool) -> bytes:
    products = list(db.scalars(select(Product).where(Product.product_model_id == model_id).order_by(Product.sku)))
    return render(label_data(db, [(product, 1) for product in products], show_price), layout)
