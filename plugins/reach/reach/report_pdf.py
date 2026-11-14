"""Campaign run summary. Generated from stored counts. Accepted is not the same as delivered."""

from __future__ import annotations

from fpdf import FPDF


# A PDF lists this many recipient rows. A longer audience stays in the CSV, and the PDF says so.
PDF_RECIPIENT_CAP = 2000


def render_run(run: dict, recipients: list[dict]) -> bytes:
    pdf = FPDF()
    pdf.compress = False
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Campaign run report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    lines = [
        f"Campaign: {run['campaign_name']}",
        f"Run: {run['run_number']}",
        f"Channel: {run['channel']}",
        f"Status: {run['status']}",
        f"Started: {_stamp(run.get('started_at'))}",
        f"Completed: {_stamp(run.get('completed_at'))}",
        f"Report first built: {_stamp(run.get('report_built_at'))}",
        f"Delivery figures updated: {_stamp(run.get('delivery_updated_at'))}",
        f"Audience: {run['total_recipients']}",
        f"Eligible: {run['eligible_recipients']}",
        f"Excluded: {run['excluded_recipients']}",
        f"Accepted by provider: {run['accepted_count']}",
        f"Delivered (provider confirmed): {run['delivered_count']}",
        f"Read: {run['read_count']}",
        f"Failed: {run['failed_count']}",
        f"Skipped: {run['skipped_count']}",
        f"Cancelled: {run['cancelled_count']}",
    ]
    for line in lines:
        pdf.cell(0, 7, _safe(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    total = int(run.get("recipient_rows") or len(recipients))
    shown = recipients[:PDF_RECIPIENT_CAP]
    complete = len(shown) >= total
    pdf.cell(0, 8, "Recipients", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if complete:
        pdf.cell(0, 7, _safe(f"This list is complete. {total} rows."), new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(
            0,
            7,
            _safe(
                f"This list is not the full audience. {len(shown)} of {total} rows are printed. "
                "Download the CSV for every row."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.set_font("Helvetica", "", 9)
    for person in shown:
        pdf.cell(
            0,
            6,
            _safe(f"{person['customer']}  {person['contact']}  {person['status']}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    return bytes(pdf.output())


def _stamp(value: object) -> str:
    if value is None:
        return "Not recorded"
    return str(value)[:19]


def _safe(value: str) -> str:
    return value.encode("latin-1", "replace").decode("latin-1")
