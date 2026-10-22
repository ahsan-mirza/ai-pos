"""Landscape PDF of an audit trail export, in the portal's charcoal/orange style."""

from __future__ import annotations

from datetime import UTC, datetime

from fpdf import FPDF

from app.schemas.audit import AuditLogDetail
from app.services.quote_service import ACCENT, CHARCOAL, FONT_PATH, LINE, MUTED, SURFACE

SENSITIVE_FILL = (255, 235, 228)
COLUMNS: tuple[tuple[str, float], ...] = (
    ("Timestamp (UTC)", 34),
    ("User", 40),
    ("Role", 28),
    ("Branch", 18),
    ("Action", 38),
    ("Target", 34),
    ("Changed fields", 46),
    ("Reason / notes", 0),
)


class _AuditPdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="L", format="A4", unit="mm")
        self.set_margins(12, 12, 12)
        self.set_auto_page_break(True, margin=16)
        self.unicode = FONT_PATH.exists()
        if self.unicode:
            self.add_font("Archivo", "", str(FONT_PATH), variations={"wght": 400})
            self.add_font("Archivo", "B", str(FONT_PATH), variations={"wght": 650})
            self.family = "Archivo"
        else:
            self.family = "Helvetica"
        self.footer_note = ""

    def font(self, size: float, bold: bool = False, color: tuple[int, int, int] = CHARCOAL) -> None:
        self.set_font(self.family, "B" if bold else "", size)
        self.set_text_color(*color)

    def text_of(self, value: str) -> str:
        return value if self.unicode else value.encode("latin-1", "replace").decode("latin-1")

    def footer(self) -> None:
        self.set_y(-11)
        self.font(7, color=MUTED)
        self.cell(0, 4, self.footer_note, align="L")
        self.cell(0, 4, f"Page {self.page_no()}", align="R")

    def table_header(self, widths: list[float]) -> None:
        self.set_fill_color(*CHARCOAL)
        self.font(7.5, bold=True, color=(255, 255, 255))
        for (label, _), width in zip(COLUMNS, widths, strict=True):
            self.cell(width, 7, f" {label}", fill=True)
        self.ln(7)


def _fit(pdf: _AuditPdf, text: str, width: float) -> str:
    text = pdf.text_of(text)
    if pdf.get_string_width(text) <= width - 2:
        return text
    while text and pdf.get_string_width(f"{text}…" if pdf.unicode else f"{text}...") > width - 2:
        text = text[:-1]
    return f"{text}…" if pdf.unicode else f"{text}..."


def render_audit_pdf(rows: list[AuditLogDetail], *, scope: str, filters: dict[str, object]) -> bytes:
    pdf = _AuditPdf()
    generated = datetime.now(UTC)
    pdf.footer_note = pdf.text_of(
        f"Audit trail export · {len(rows)} entries · generated {generated:%d %b %Y %H:%M} UTC"
    )
    pdf.set_title("Audit trail")
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    fixed = sum(width for _, width in COLUMNS)
    widths = [width or usable - fixed for _, width in COLUMNS]

    pdf.set_fill_color(*ACCENT)
    pdf.ellipse(pdf.l_margin, 12, 10, 10, style="F")
    pdf.set_xy(pdf.l_margin, 14.6)
    pdf.font(9, bold=True, color=(255, 255, 255))
    pdf.cell(10, 5, "ai", align="C")
    pdf.set_xy(pdf.l_margin + 14, 11.5)
    pdf.font(7.5, color=MUTED)
    pdf.cell(120, 4.5, pdf.text_of(scope.upper()))
    pdf.set_xy(pdf.l_margin + 14, 16)
    pdf.font(16, bold=True)
    pdf.cell(120, 7, "Audit trail & user activity")

    sensitive = sum(1 for row in rows if row.sensitive)
    pdf.set_xy(pdf.w - pdf.r_margin - 90, 12)
    for label, value, fill in (("Entries", len(rows), CHARCOAL), ("Sensitive", sensitive, ACCENT)):
        pdf.set_fill_color(*fill)
        pdf.font(7, color=(255, 255, 255))
        x = pdf.get_x()
        pdf.cell(44, 4.5, f"  {label.upper()}", fill=True, new_x="LEFT", new_y="NEXT")
        pdf.set_x(x)
        pdf.font(12, bold=True, color=(255, 255, 255))
        pdf.cell(44, 6, f"  {value:,}", fill=True, new_x="RIGHT", new_y="TOP")
        pdf.set_xy(x + 46, 12)

    described = ", ".join(f"{key}: {value}" for key, value in filters.items()) or "No filters (most recent entries)"
    pdf.set_xy(pdf.l_margin, 27)
    pdf.font(7.5, color=MUTED)
    pdf.cell(usable, 4.5, _fit(pdf, f"Filters: {described}", usable))
    pdf.ln(7)

    pdf.table_header(widths)
    for index, row in enumerate(rows):
        if pdf.will_page_break(6.5):
            pdf.add_page()
            pdf.table_header(widths)
        fill = SENSITIVE_FILL if row.sensitive else (SURFACE if index % 2 else (255, 255, 255))
        pdf.set_fill_color(*fill)
        target = row.target_entity + (f" #{str(row.target_entity_id)[:8]}" if row.target_entity_id else "")
        cells = (
            row.occurred_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            row.user_name or "System",
            row.user_role or "—",
            row.store_code or "—",
            row.action_type.replace("_", " ").title(),
            target,
            ", ".join(row.changed_fields) or "—",
            row.reason_notes or "",
        )
        for column, (text, width) in enumerate(zip(cells, widths, strict=True)):
            bold = column == 4 and row.sensitive
            pdf.font(7.5, bold=bold, color=ACCENT if bold else CHARCOAL)
            pdf.cell(width, 6.5, f" {_fit(pdf, text, width - 1)}", fill=True)
        pdf.ln(6.5)
        pdf.set_draw_color(*LINE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + usable, pdf.get_y())

    if not rows:
        pdf.font(9, color=MUTED)
        pdf.cell(usable, 12, "No audit entries match these filters.", align="C")
    return bytes(pdf.output())
