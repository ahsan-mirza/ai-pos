"""UAE VAT return (VAT201) figures from posted sales, credit notes, and goods receipts."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.payables import SupplierBill, SupplierBillLine
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.schemas.vat import VatBox, VatEmirateRow, VatReport
from app.services.invoice_pdf import EMIRATES, _Pdf, money
from app.services.settings_service import cached_settings
from app.services.tax import div_half_up
from app.tax_authority.fta import FULL_INVOICE_THRESHOLD_CENTS

POSTED = ("completed", "partially_refunded", "refunded")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start:
        raise ApiError(422, "validation_error", "The period ends before it starts.")
    if (end - start).days > 400:
        raise ApiError(422, "validation_error", "A VAT period is at most 400 days.")
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def _category(rate_column, tax_column, treatment_column=None):
    """STANDARD when VAT was charged; otherwise the customer's relief (export / zone or exempt) on the line,
    else the product's own category."""
    whens = [((func.coalesce(rate_column, 0) > 0) | (tax_column > 0), "STANDARD")]
    if treatment_column is not None:
        whens.append((treatment_column == "EXEMPT", "EXEMPT"))
        whens.append((treatment_column.in_(("ZERO_EXPORT", "DESIGNATED_ZONE")), "ZERO"))
    return case(*whens, else_=func.coalesce(Product.tax_category, "STANDARD"))


def build(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> VatReport:
    since, until = _bounds(start, end)
    settings = cached_settings(db)
    emirate_key = func.coalesce(Store.emirate, "")

    sales = (
        select(
            emirate_key.label("vat_emirate"),
            _category(SaleItem.tax_rate_bps, SaleItem.tax_cents, SaleItem.tax_treatment).label("vat_category"),
            func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0),
            func.coalesce(func.sum(SaleItem.tax_cents), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Store, Store.id == Sale.store_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
            Sale.created_at >= since,
            Sale.created_at < until,
            # Gift cards are multi-purpose vouchers: outside VAT when sold, taxed on what they buy.
            SaleItem.gift_card_code.is_(None),
        )
        .group_by("vat_emirate", "vat_category")
    )
    refunds = (
        select(
            emirate_key.label("vat_emirate"),
            _category(None, ReturnItem.tax_refund_cents, SaleItem.tax_treatment).label("vat_category"),
            func.coalesce(func.sum(ReturnItem.refund_cents - ReturnItem.tax_refund_cents), 0),
            func.coalesce(func.sum(ReturnItem.tax_refund_cents), 0),
        )
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .outerjoin(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
        .join(Store, Store.id == SaleReturn.store_id)
        .join(Product, Product.id == ReturnItem.product_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
        .group_by("vat_emirate", "vat_category")
    )
    if store_id is not None:
        sales = sales.where(Sale.store_id == store_id)
        refunds = refunds.where(SaleReturn.store_id == store_id)

    emirates: dict[str, VatEmirateRow] = {
        code: VatEmirateRow(emirate=code, label=label, amount_cents=0, vat_cents=0, adjustment_cents=0)
        for code, label in EMIRATES.items()
    }
    unassigned = VatEmirateRow(
        emirate=None, label="branches with no emirate set", amount_cents=0, vat_cents=0, adjustment_cents=0
    )
    totals = {"ZERO": 0, "EXEMPT": 0}
    adjustments = {"ZERO": 0, "EXEMPT": 0}

    def row_for(code: str) -> VatEmirateRow:
        return emirates.get(code, unassigned)

    for code, category, net, tax in db.execute(sales).all():
        if category == "STANDARD":
            row = row_for(code)
            row.amount_cents += int(net)
            row.vat_cents += int(tax)
        else:
            totals[category] = totals.get(category, 0) + int(net)
    for code, category, net, tax in db.execute(refunds).all():
        if category == "STANDARD":
            row = row_for(code)
            row.amount_cents -= int(net)
            row.adjustment_cents -= int(tax)
        else:
            adjustments[category] = adjustments.get(category, 0) - int(net)

    # Input VAT: supplier bills and expenses backed by a tax invoice; goods received but not yet billed are
    # estimated at the standard rate until their supplier invoice is entered.
    billed = (
        select(
            func.coalesce(func.sum(SupplierBillLine.quantity * SupplierBillLine.unit_cost_cents), 0),
            func.coalesce(func.sum(SupplierBillLine.tax_cents), 0),
        )
        .join(SupplierBill, SupplierBill.id == SupplierBillLine.bill_id)
        .where(
            SupplierBill.bill_date >= start,
            SupplierBill.bill_date <= end,
            SupplierBill.status != "VOID",
            SupplierBillLine.tax_category == "STANDARD",
        )
    )
    expensed = select(
        func.coalesce(func.sum(Expense.net_cents), 0), func.coalesce(func.sum(Expense.tax_cents), 0)
    ).where(
        Expense.spent_on >= start,
        Expense.spent_on <= end,
        Expense.status != "VOID",
        Expense.has_tax_invoice.is_(True),
        Expense.tax_cents > 0,
    )
    receipts = (
        select(func.coalesce(func.sum(GoodsReceiptLine.quantity * PurchaseOrderLine.unit_cost_cents), 0))
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrderLine, PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id)
        .where(
            GoodsReceipt.created_at >= since,
            GoodsReceipt.created_at < until,
            GoodsReceipt.id.not_in(
                select(SupplierBill.goods_receipt_id).where(SupplierBill.goods_receipt_id.is_not(None))
            ),
        )
    )
    if store_id is not None:
        billed = billed.where(SupplierBill.store_id == store_id)
        expensed = expensed.where(Expense.store_id == store_id)
        receipts = receipts.where(GoodsReceipt.store_id == store_id)
    bill_net, bill_tax = db.execute(billed).one()
    expense_net, expense_tax = db.execute(expensed).one()
    unbilled = int(db.scalar(receipts) or 0)
    estimated_tax = div_half_up(unbilled * settings.standard_rate_bps, 10_000)
    purchases = int(bill_net) + int(expense_net) + unbilled
    input_vat = int(bill_tax) + int(expense_tax) + estimated_tax if settings.vat_registered else 0

    invoice_counts = select(
        func.count(Sale.id),
        func.coalesce(
            func.sum(
                case(
                    ((Customer.trn_vat_number.is_not(None)) | (Sale.total_cents > FULL_INVOICE_THRESHOLD_CENTS), 1),
                    else_=0,
                )
            ),
            0,
        ),
    ).outerjoin(Customer, Customer.id == Sale.customer_id)
    invoice_counts = invoice_counts.where(
        Sale.is_quote_proforma.is_(False),
        Sale.status.in_(POSTED),
        Sale.created_at >= since,
        Sale.created_at < until,
    )
    credit_notes = select(func.count(SaleReturn.id)).where(
        SaleReturn.created_at >= since, SaleReturn.created_at < until
    )
    if store_id is not None:
        invoice_counts = invoice_counts.where(Sale.store_id == store_id)
        credit_notes = credit_notes.where(SaleReturn.store_id == store_id)
    count, full = db.execute(invoice_counts).one()

    rows = [*emirates.values()] + ([unassigned] if unassigned.amount_cents or unassigned.vat_cents else [])
    standard_amount = sum(row.amount_cents for row in rows)
    output_vat = sum(row.vat_cents + row.adjustment_cents for row in rows)
    boxes = [
        VatBox(key="1", label="Standard rated supplies", amount_cents=standard_amount, vat_cents=output_vat),
        VatBox(key="2", label="Tax refunds to tourists", amount_cents=0, vat_cents=0),
        VatBox(key="3", label="Supplies subject to reverse charge", amount_cents=0, vat_cents=0),
        VatBox(key="4", label="Zero rated supplies", amount_cents=totals["ZERO"] + adjustments["ZERO"], vat_cents=0),
        VatBox(key="5", label="Exempt supplies", amount_cents=totals["EXEMPT"] + adjustments["EXEMPT"], vat_cents=0),
        VatBox(key="6", label="Goods imported into the UAE", amount_cents=0, vat_cents=0),
        VatBox(
            key="8",
            label="Totals (sales and all other outputs)",
            amount_cents=standard_amount
            + totals["ZERO"]
            + adjustments["ZERO"]
            + totals["EXEMPT"]
            + adjustments["EXEMPT"],
            vat_cents=output_vat,
        ),
        VatBox(key="9", label="Standard rated expenses", amount_cents=purchases, vat_cents=input_vat),
        VatBox(key="10", label="Supplies subject to reverse charge", amount_cents=0, vat_cents=0),
        VatBox(key="11", label="Totals (expenses and all other inputs)", amount_cents=purchases, vat_cents=input_vat),
    ]
    return VatReport(
        period_from=start,
        period_to=end,
        store_id=store_id,
        currency=settings.currency,
        trn=settings.trn,
        legal_name=settings.legal_name,
        vat_registered=settings.vat_registered,
        emirates=rows,
        boxes=boxes,
        output_vat_cents=output_vat,
        input_vat_cents=input_vat,
        net_vat_cents=output_vat - input_vat,
        input_vat_estimated=unbilled > 0,
        invoices=int(count),
        full_invoices=int(full),
        simplified_invoices=int(count) - int(full),
        credit_notes=int(db.scalar(credit_notes) or 0),
    )


def to_csv(report: VatReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["VAT return", f"{report.period_from} to {report.period_to}", report.trn or "", report.currency])
    writer.writerow(["Box", "Description", "Amount", "VAT", "Adjustment"])
    for row in report.emirates:
        writer.writerow(
            [
                f"1 ({row.emirate or '-'})",
                row.label,
                f"{row.amount_cents / 100:.2f}",
                f"{row.vat_cents / 100:.2f}",
                f"{row.adjustment_cents / 100:.2f}",
            ]
        )
    for box in report.boxes:
        writer.writerow([box.key, box.label, f"{box.amount_cents / 100:.2f}", f"{box.vat_cents / 100:.2f}", ""])
    writer.writerow(["12", "Total value of due tax", "", f"{report.output_vat_cents / 100:.2f}", ""])
    writer.writerow(["13", "Total value of recoverable tax", "", f"{report.input_vat_cents / 100:.2f}", ""])
    writer.writerow(["14", "Payable tax for the period", "", f"{report.net_vat_cents / 100:.2f}", ""])
    return buffer.getvalue()


def to_pdf(report: VatReport) -> bytes:
    pdf = _Pdf("VAT return working paper. File the return on the FTA portal (EmaraTax).")
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.font(8, color=(122, 120, 126))
    pdf.cell(0, 5, (report.legal_name or "").upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.font(18, bold=True)
    pdf.cell(0, 9, "VAT return (VAT201)", new_x="LMARGIN", new_y="NEXT")
    pdf.font(9, color=(122, 120, 126))
    pdf.cell(
        0,
        5,
        f"{report.period_from:%d %b %Y} to {report.period_to:%d %b %Y} · TRN {report.trn or 'not registered'}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    widths = [18, width - 18 - 36 - 32 - 32, 36, 32, 32]

    def line(cells: list[str], bold: bool = False, fill: bool = False) -> None:
        pdf.set_fill_color(247, 245, 242)
        pdf.font(9, bold=bold)
        for index, (text, cell_width) in enumerate(zip(cells, widths, strict=True)):
            pdf.cell(cell_width, 7, text, fill=fill, align="L" if index < 2 else "R")
        pdf.ln(7)

    line(["Box", "Description", "Amount", "VAT", "Adjustment"], bold=True, fill=True)
    for row in report.emirates:
        line(
            [
                f"1 {row.emirate or ''}",
                row.label,
                money(row.amount_cents, report.currency),
                money(row.vat_cents, report.currency),
                money(row.adjustment_cents, report.currency),
            ]
        )
    for box in report.boxes:
        line(
            [box.key, box.label, money(box.amount_cents, report.currency), money(box.vat_cents, report.currency), ""],
            bold=box.key in ("8", "11"),
        )
    line(["12", "Total value of due tax", "", money(report.output_vat_cents, report.currency), ""], bold=True)
    line(["13", "Total value of recoverable tax", "", money(report.input_vat_cents, report.currency), ""], bold=True)
    line(
        ["14", "Payable tax for the period", "", money(report.net_vat_cents, report.currency), ""], bold=True, fill=True
    )
    pdf.ln(4)
    pdf.font(8.5, color=(122, 120, 126))
    pdf.multi_cell(
        width,
        4.4,
        f"{report.invoices} tax invoices ({report.full_invoices} full, {report.simplified_invoices} simplified) and "
        f"{report.credit_notes} credit notes in the period. "
        + (
            "Input VAT on goods received but not yet billed is estimated at the standard rate; enter those "
            "supplier invoices under Payables to replace the estimate."
            if report.input_vat_estimated
            else ""
        ),
    )
    return bytes(pdf.output())
