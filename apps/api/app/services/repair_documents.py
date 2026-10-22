"""The A4 job card a customer signs at intake: device, condition checklist, estimate, terms, and a Code 128 of the
ticket the register scans to open it at pickup."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value
from app.models.repair_ticket import RepairDeposit, RepairTicket
from app.models.store import Store
from app.models.user import User
from app.services import barcodes
from app.services.invoice_pdf import CHARCOAL, LINE, MUTED, SURFACE, _Pdf, money
from app.services.repair_workshop_service import (
    STATUS_LABELS,
    barcode_value,
    reference,
    repair_settings,
    tracking_url,
    warranty_days,
)
from app.services.settings_service import cached_settings

CHECKLIST_LABELS = {
    "powers_on": "Powers on",
    "screen_cracked": "Screen cracked",
    "back_cracked": "Back glass cracked",
    "water_damage": "Signs of liquid damage",
    "buttons_work": "Buttons work",
    "camera_works": "Camera works",
    "charging_works": "Charges",
    "touch_works": "Touch works",
    "speaker_works": "Speaker and mic work",
    "face_or_touch_id": "Face / Touch ID works",
    "sim_tray": "SIM tray present",
    "find_my_off": "Find My / FRP switched off",
}


def _bars(pdf: _Pdf, modules: str, x: float, y: float, width: float, height: float) -> None:
    module = width / len(modules)
    run = 0
    pdf.set_fill_color(*CHARCOAL)
    for index, bit in enumerate(modules + "0"):
        if bit == "1":
            run += 1
            continue
        if run:
            pdf.rect(x + (index - run) * module, y, run * module, height, style="F")
            run = 0


def _checked(value: object) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value or "-")


def render_job_card(
    db: Session, settings: Settings, ticket_id: uuid.UUID, store_scope: uuid.UUID | None
) -> tuple[str, bytes]:
    ticket = db.get(RepairTicket, ticket_id)
    if ticket is None or (store_scope is not None and ticket.store_id != store_scope):
        raise ApiError(404, "not_found", "Repair ticket was not found.")
    store = db.get(Store, ticket.store_id)
    assert store is not None
    technician = db.get(User, ticket.technician_id) if ticket.technician_id else None
    deposits = db.scalars(
        select(RepairDeposit).where(RepairDeposit.ticket_id == ticket.id, RepairDeposit.status != "REFUNDED")
    ).all()
    terms = repair_settings(db).terms
    ref = reference(ticket)
    legal = getattr(cached_settings(db), "legal_name", None) or store.name

    pdf = _Pdf(f"Job card {ref}")
    pdf.set_title(f"Job card {ref}")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.font(8, color=MUTED)
    pdf.cell(0, 5, legal.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.font(18, bold=True)
    pdf.cell(width - 72, 9, "Repair job card")
    pdf.set_fill_color(*CHARCOAL)
    pdf.font(11, bold=True, color=(255, 255, 255))
    pdf.cell(72, 9, ref, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    top = pdf.get_y() + 3
    _bars(pdf, barcodes.code128_modules(barcode_value(ticket)), pdf.w - pdf.r_margin - 72, top, 72, 14)
    pdf.font(7.5, color=MUTED)
    pdf.set_xy(pdf.w - pdf.r_margin - 72, top + 15)
    pdf.cell(72, 4, barcode_value(ticket), align="C")
    pdf.set_xy(pdf.l_margin, top)
    pdf.font(9, color=MUTED)
    pdf.multi_cell(width - 80, 4.6, f"{store.name}\n{store.address or ''}".strip(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(top + 22)
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    def pair(label: str, value: str) -> None:
        pdf.font(7.5, bold=True, color=MUTED)
        pdf.cell(42, 6, label.upper())
        pdf.font(10)
        pdf.multi_cell(width - 42, 6, value or "-", new_x="LMARGIN", new_y="NEXT")

    identifier = decrypt_value(ticket.identifier_encrypted, settings)
    pair("Customer", f"{ticket.customer_name} · {ticket.customer_phone}")
    pair("Device", ticket.device_model)
    pair(ticket.identifier_kind.upper(), identifier)
    pair("Reported issue", ticket.issue)
    pair("Accessories left", ticket.accessories or "None")
    pair("Booked in", f"{ticket.created_at:%d %b %Y %H:%M}")
    if ticket.promised_at:
        pair("Promised for", f"{ticket.promised_at:%d %b %Y %H:%M}")
    if technician:
        pair("Technician", technician.full_name)
    pair("Status", STATUS_LABELS.get(ticket.status, ticket.status))
    pair("Estimate", money(ticket.approval_amount_cents or ticket.estimated_cost_cents, ticket.currency))
    if deposits:
        paid = sum(row.amount_cents for row in deposits)
        pair("Deposit paid", money(paid, ticket.currency))
    days = warranty_days(db, ticket)
    pair("Repair warranty", f"{days} days on parts and labour" if days else "None")
    pdf.ln(3)

    checklist = ticket.intake_checklist or {}
    if checklist:
        pdf.set_fill_color(*SURFACE)
        pdf.font(7.5, bold=True, color=MUTED)
        pdf.cell(width, 7, "CONDITION AT INTAKE", fill=True, new_x="LMARGIN", new_y="NEXT")
        column = width / 2
        for index, (key, value) in enumerate(checklist.items()):
            if index % 2 == 0 and index:
                pdf.ln(6)
            pdf.set_x(pdf.l_margin + (index % 2) * column)
            pdf.font(9)
            pdf.cell(column - 22, 6, CHECKLIST_LABELS.get(key, key.replace("_", " ").capitalize())[:48])
            pdf.font(9, bold=True)
            pdf.cell(22, 6, _checked(value)[:20])
        pdf.ln(9)

    pdf.font(7.5, bold=True, color=MUTED)
    pdf.cell(0, 6, "TERMS", new_x="LMARGIN", new_y="NEXT")
    pdf.font(8.5, color=MUTED)
    pdf.multi_cell(width, 4.4, terms, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(width, 4.4, f"Track this repair: {tracking_url(settings, ticket)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    if pdf.get_y() + 20 > pdf.page_break_trigger:
        pdf.add_page()
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y + 10, pdf.l_margin + 75, y + 10)
    pdf.line(pdf.w - pdf.r_margin - 75, y + 10, pdf.w - pdf.r_margin, y + 10)
    pdf.set_xy(pdf.l_margin, y + 11)
    pdf.font(8, color=MUTED)
    pdf.cell(75, 4, "Customer signature")
    pdf.set_x(pdf.w - pdf.r_margin - 75)
    pdf.cell(75, 4, "Received by")
    db.commit()
    return ref, bytes(pdf.output())
