"""Payslip PDF from an approved payroll snapshot. Amounts are the stored cents, not a fresh calculation."""

from __future__ import annotations

import base64
import calendar
import io
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.staff import PayrollLine, PayrollRun
from app.models.user import User
from app.services.invoice_pdf import CHARCOAL, MUTED, _Pdf
from app.services.payroll_engine import FORMULA, _deductions, _gross, _leave_deduction
from app.services.settings_service import cached_settings, receipt_profile


def _money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}{currency} {amount // 100:,}.{amount % 100:02d}"


def _logo(db: Session):
    raw = receipt_profile(db, None).settings.logo_png
    if not raw or "," not in raw:
        return None
    try:
        return io.BytesIO(base64.b64decode(raw.split(",", 1)[1]))
    except (ValueError, TypeError):
        return None


def render(db: Session, line: PayrollLine, run: PayrollRun, employee: User) -> tuple[str, bytes]:
    settings = cached_settings(db)
    business = settings.legal_name or "Payslip"
    last = calendar.monthrange(run.year, run.month)[1]
    period = f"01-{run.month:02d}-{run.year} to {last:02d}-{run.month:02d}-{run.year}"
    pdf = _Pdf("Approved payroll snapshot. This copy was printed from that snapshot.")
    pdf.set_title(f"Payslip {line.employee_code}")
    pdf.add_page()
    logo = _logo(db)
    if logo is not None:
        pdf.image(logo, w=28)
        pdf.ln(2)
    pdf.font(16, bold=True, color=CHARCOAL)
    pdf.cell(0, 8, business, new_x="LMARGIN", new_y="NEXT")
    if settings.legal_name_ar and pdf.arabic(12):
        pdf.cell(0, 7, settings.legal_name_ar, new_x="LMARGIN", new_y="NEXT")
        pdf.font(11, bold=True)
    else:
        pdf.font(11, bold=True)
    pdf.cell(0, 7, "Payslip", new_x="LMARGIN", new_y="NEXT")
    pdf.font(9, color=MUTED)
    pdf.cell(0, 5, f"{employee.full_name}  ·  {line.employee_code}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Period {period}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Payment status {run.payment_status.replace('_', ' ').title()}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.font(9, bold=True)
    pdf.cell(120, 6, "Component")
    pdf.cell(0, 6, "Amount", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.font(9)
    for row in (line.breakdown or {}).get("components") or []:
        if not isinstance(row, dict):
            continue
        cents = int(row.get("cents") or 0)
        label = str(row.get("name") or "")
        if row.get("kind") == "DEDUCTION":
            label = f"{label} (deduction)"
            cents = -cents
        pdf.cell(120, 6, label)
        pdf.cell(0, 6, _money(cents, run.currency), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.font(9, bold=True)
    pdf.cell(120, 6, "Gross earnings")
    pdf.cell(0, 6, _money(_gross(line), run.currency), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(120, 6, "Total deductions")
    pdf.cell(0, 6, _money(_deductions(line), run.currency), align="R", new_x="LMARGIN", new_y="NEXT")
    if line.unpaid_leave_days:
        pdf.font(8, color=MUTED)
        leave = _money(_leave_deduction(line), run.currency)
        pdf.cell(0, 5, f"Includes unpaid leave of {leave}.", new_x="LMARGIN", new_y="NEXT")
    pdf.font(12, bold=True)
    pdf.cell(120, 8, "Net payable")
    pdf.cell(0, 8, _money(line.net_cents, run.currency), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.font(8, color=MUTED)
    pdf.multi_cell(0, 4, FORMULA)
    pdf.ln(2)
    printed = datetime.now(UTC).strftime("%d-%m-%Y")
    pdf.cell(
        0,
        5,
        f"Generated {printed}. Figures are the approved payroll snapshot and do not change.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    name = f"payslip-{line.employee_code}-{run.year}{run.month:02d}.pdf"
    return name, bytes(pdf.output())
