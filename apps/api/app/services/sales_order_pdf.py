"""A4 order confirmations, pick lists and delivery notes. The invoice for each delivery is the sale's own PDF."""

import base64
import binascii
import io
import uuid

from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.product import Product
from app.models.sales_order import DeliveryNote, PickList, SalesOrder
from app.models.store import Store
from app.models.user import User
from app.services.invoice_pdf import CHARCOAL, LINE, MUTED, SURFACE, _Pdf, money
from app.services.sales_order_service import _order
from app.services.settings_service import cached_settings


def _start(db: Session, title: str, number: str, store: Store, customer: Customer | None, extra: list[str]) -> _Pdf:
    legal = getattr(cached_settings(db), "legal_name", None) or store.name
    pdf = _Pdf(f"{title} {number}")
    pdf.set_title(f"{title} {number}")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.font(8, color=MUTED)
    pdf.cell(0, 5, legal.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.font(18, bold=True)
    pdf.cell(width - 72, 9, title)
    pdf.set_fill_color(*CHARCOAL)
    pdf.font(11, bold=True, color=(255, 255, 255))
    pdf.cell(72, 9, number, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)
    top = pdf.get_y()
    pdf.font(7.5, bold=True, color=MUTED)
    pdf.cell(width / 2, 5, "FROM", new_x="LEFT", new_y="NEXT")
    pdf.font(10, bold=True)
    pdf.cell(width / 2, 5, store.name, new_x="LEFT", new_y="NEXT")
    pdf.font(8.5, color=MUTED)
    pdf.multi_cell(width / 2 - 4, 4.4, store.address or "", new_x="LEFT", new_y="NEXT")
    bottom = pdf.get_y()
    if customer is not None:
        pdf.set_xy(pdf.l_margin + width / 2, top)
        pdf.font(7.5, bold=True, color=MUTED)
        pdf.cell(width / 2, 5, "CUSTOMER", new_x="LEFT", new_y="NEXT")
        pdf.font(10, bold=True)
        pdf.cell(width / 2, 5, customer.company_name or customer.name, new_x="LEFT", new_y="NEXT")
        pdf.font(8.5, color=MUTED)
        for row in [*extra, customer.phone or ""]:
            if row:
                pdf.multi_cell(width / 2 - 4, 4.4, row, new_x="LEFT", new_y="NEXT")
        bottom = max(bottom, pdf.get_y())
    pdf.set_xy(pdf.l_margin, bottom + 4)
    return pdf


def _table(pdf: _Pdf, headers: list[str], widths: list[float], rows: list[list[str]]) -> None:
    def header() -> None:
        pdf.set_fill_color(*SURFACE)
        pdf.font(7.5, bold=True, color=MUTED)
        for index, (label, cell_width) in enumerate(zip(headers, widths, strict=True)):
            pdf.cell(cell_width, 8, label.upper(), fill=True, align="L" if index < 2 else "R")
        pdf.ln(8)

    header()
    for row in rows:
        if pdf.get_y() + 8 > pdf.page_break_trigger:
            pdf.add_page()
            header()
        for index, (text, cell_width) in enumerate(zip(row, widths, strict=True)):
            pdf.font(9.5, bold=index == 1)
            pdf.cell(cell_width, 7, text[:60], align="L" if index < 2 else "R")
        pdf.ln(7)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Product]:
    return {product_id: product for product_id in ids if (product := db.get(Product, product_id)) is not None}


def _context(db: Session, order: SalesOrder) -> tuple[Store, Customer | None]:
    store = db.get(Store, order.store_id)
    assert store is not None
    return store, db.get(Customer, order.customer_id)


def render_order(db: Session, principal: Principal, order_id: uuid.UUID) -> tuple[str, bytes]:
    order = _order(db, principal, order_id)
    store, customer = _context(db, order)
    extra = [order.delivery_address or "", f"Your ref {order.customer_reference}" if order.customer_reference else ""]
    pdf = _start(db, "Order confirmation", order.number, store, customer, extra)
    products = _names(db, {line.product_id for line in order.lines})
    width = pdf.w - pdf.l_margin - pdf.r_margin
    rows = [
        [
            str(position),
            (products[line.product_id].name if line.product_id in products else "Item"),
            f"{line.quantity_ordered:,}",
            f"{line.quantity_delivered:,}",
            money(line.unit_price_cents, order.currency),
            money(line.line_total_cents, order.currency),
        ]
        for position, line in enumerate(order.lines, start=1)
    ]
    _table(pdf, ["#", "Item", "Ordered", "Delivered", "Unit price", "Amount"], [8, width - 120, 22, 22, 34, 34], rows)
    pdf.ln(4)
    for label, value in (("Subtotal", order.subtotal_cents), ("VAT", order.tax_cents), ("Total", order.total_cents)):
        pdf.set_x(pdf.w - pdf.r_margin - 80)
        pdf.font(10, bold=label == "Total")
        pdf.cell(40, 6, label)
        pdf.cell(40, 6, money(value, order.currency), align="R", new_x="LMARGIN", new_y="NEXT")
    if order.requested_date:
        pdf.font(8.5, color=MUTED)
        pdf.cell(0, 6, f"Requested for {order.requested_date:%d %b %Y}. Each delivery is invoiced as it leaves.")
    return order.number, bytes(pdf.output())


def render_pick_list(db: Session, principal: Principal, pick_id: uuid.UUID) -> tuple[str, bytes]:
    pick = db.get(PickList, pick_id)
    if pick is None:
        raise ApiError(404, "not_found", "Pick list was not found.")
    order = _order(db, principal, pick.order_id)
    store, customer = _context(db, order)
    pdf = _start(db, "Pick list", pick.number, store, customer, [f"Order {order.number}"])
    products = _names(db, {line.product_id for line in pick.lines})
    width = pdf.w - pdf.l_margin - pdf.r_margin
    rows = [
        [
            line.bin_location or "-",
            products[line.product_id].name if line.product_id in products else "Item",
            products[line.product_id].sku if line.product_id in products else "",
            f"{line.quantity:,}",
            "[    ]",
        ]
        for line in pick.lines
    ]
    _table(pdf, ["Bin", "Item", "SKU", "Qty", "Picked"], [26, width - 26 - 40 - 20 - 22, 40, 20, 22], rows)
    return pick.number, bytes(pdf.output())


def _signature(data_url: str | None) -> io.BytesIO | None:
    if not data_url or "," not in data_url:
        return None
    try:
        return io.BytesIO(base64.b64decode(data_url.split(",", 1)[1], validate=True))
    except (binascii.Error, ValueError):
        return None


def render_delivery_note(db: Session, principal: Principal, note_id: uuid.UUID) -> tuple[str, bytes]:
    note = db.get(DeliveryNote, note_id)
    if note is None:
        raise ApiError(404, "not_found", "Delivery note was not found.")
    order = _order(db, principal, note.order_id)
    store, customer = _context(db, order)
    driver = db.get(User, note.driver_id) if note.driver_id else None
    extra = [
        order.delivery_address or "",
        f"Order {order.number}",
        " · ".join(item for item in (driver.full_name if driver else "", note.vehicle or "") if item),
    ]
    pdf = _start(db, "Delivery note", note.number, store, customer, extra)
    products = _names(db, {line.product_id for line in note.lines})
    width = pdf.w - pdf.l_margin - pdf.r_margin
    rows = [
        [
            str(position),
            products[line.product_id].name if line.product_id in products else "Item",
            ", ".join(f"…{suffix}" for suffix in (line.serial_suffixes or []))[:40],
            f"{line.quantity:,}",
        ]
        for position, line in enumerate(note.lines, start=1)
    ]
    _table(pdf, ["#", "Item", "Serials", "Qty"], [8, width - 8 - 60 - 20, 60, 20], rows)
    pdf.ln(10)
    if pdf.get_y() + 40 > pdf.page_break_trigger:
        pdf.add_page()
    top = pdf.get_y()
    pdf.font(7.5, bold=True, color=MUTED)
    pdf.cell(0, 5, "RECEIVED IN GOOD ORDER", new_x="LMARGIN", new_y="NEXT")
    image = _signature(note.signature)
    if image is not None:
        try:
            pdf.image(image, x=pdf.l_margin, y=top + 6, h=24)
        except Exception:  # noqa: BLE001 - an unreadable signature must not block the printout
            image = None
    if image is None:
        pdf.line(pdf.l_margin, top + 28, pdf.l_margin + 80, top + 28)
    pdf.set_xy(pdf.l_margin, top + 30)
    pdf.font(9)
    received = (
        f"{note.receiver_name}, {note.delivered_at:%d %b %Y %H:%M}"
        if note.receiver_name and note.delivered_at
        else "Name, signature and date"
    )
    pdf.cell(0, 5, received)
    return note.number, bytes(pdf.output())
