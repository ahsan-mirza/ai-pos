"""Accounting exports: a balanced general-ledger journal (CSV) and PINT AE UBL 2.1 e-invoices."""

import csv
import io
import uuid
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError
from app.models.banking import BankStatementLine
from app.models.batch import BatchItem, PurchaseBatch
from app.models.cheque import Cheque, ChequeEvent
from app.models.customer import Customer, CustomerLedgerEntry
from app.models.payables import SupplierBill, SupplierPayment
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, PurchaseOrderLine
from app.models.return_item import ReturnItem
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.trade_in import TradeIn
from app.schemas.exports import GlAccountOut, GlAccountsWrite
from app.services import (
    channel_service,
    costing,
    expense_service,
    management_reports,
    staff_service,
    trade_in_service,
)
from app.services.settings_service import load_settings

POSTED = ("completed", "partially_refunded", "refunded")

ACCOUNTS = {
    "cash": ("1000", "Cash on hand"),
    "card": ("1010", "Card settlements receivable"),
    "original_card": ("1010", "Card settlements receivable"),
    "transfer": ("1020", "Bank"),
    "cheque": ("1030", "Cheques in hand"),
    "qr": ("1040", "QR payment settlements receivable"),
    "bnpl": ("1045", "Pay-later provider settlements receivable"),
    "original_bnpl": ("1045", "Pay-later provider settlements receivable"),
    "channel": ("1050", "Delivery channel settlements receivable"),
    "on_account": ("1100", "Accounts receivable"),
    "inventory": ("1200", "Inventory"),
    "vat_input": ("1300", "VAT input recoverable"),
    "payables": ("2000", "Accounts payable"),
    "cheques_issued": ("2010", "Cheques issued, not cleared"),
    "grni": ("2050", "Stock received, not billed"),
    "vat": ("2100", "VAT output"),
    "deposit": ("2200", "Customer deposits"),
    "loyalty": ("2300", "Loyalty points liability"),
    "store_credit": ("2400", "Store credit liability"),
    "gift_card": ("2410", "Gift cards outstanding"),
    "trade_in": ("2500", "Trade-in credit owed"),
    "corporate_tax": ("2600", "Corporate tax payable"),
    "tips": ("2700", "Tips owed to staff"),
    "opening_equity": ("3000", "Owner's capital and opening balances"),
    "retained_earnings": ("3100", "Retained earnings"),
    "revenue": ("4000", "Sales revenue"),
    "returns": ("4100", "Sales returns"),
    "restocking": ("4200", "Restocking fees"),
    "other_income": ("4300", "Other income"),
    "service_charge": ("4400", "Service charge income"),
    "cogs": ("5000", "Cost of goods sold"),
    "other_purchases": ("5100", "Other purchases"),
    "shrinkage": ("5200", "Stock shrinkage and write-offs"),
    "petty_cash": ("1005", "Petty cash"),
    "expense_rent": ("6100", "Rent"),
    "expense_utilities": ("6200", "Utilities and telecom"),
    "expense_salaries": ("6300", "Salaries and wages"),
    "expense_transport": ("6400", "Transport and fuel"),
    "expense_marketing": ("6500", "Marketing"),
    "expense_maintenance": ("6600", "Repairs and maintenance"),
    "expense_office": ("6700", "Office and supplies"),
    "expense_bank_fees": ("6800", "Bank and card fees"),
    "channel_commission": ("6810", "Delivery channel commission"),
    "expense_other": ("6900", "Other expenses"),
    "corporate_tax_expense": ("6950", "Corporate tax expense"),
}
ACCOUNT_USES = {
    "cash": "Cash taken and refunded at the till",
    "card": "Card payments awaiting settlement",
    "original_card": "Refunds back to the customer's card",
    "transfer": "Bank transfers",
    "cheque": "Cheques received, until they clear",
    "qr": "QR payments awaiting settlement",
    "bnpl": "Tabby and Tamara payments awaiting payout",
    "original_bnpl": "Refunds back through Tabby or Tamara",
    "channel": "Delivery-app orders the channel pays out later",
    "tips": "Tips collected for staff, paid out from the drawer or payroll",
    "service_charge": "Automatic service charge on dine-in bills",
    "channel_commission": "Commission the delivery apps keep",
    "on_account": "Wholesale credit sales and account receipts",
    "inventory": "Stock at cost",
    "vat": "Output VAT on sales and credit notes",
    "deposit": "Layaway deposits applied at conversion",
    "loyalty": "Points redeemed as payment",
    "store_credit": "Store credit issued on returns and spent at checkout",
    "gift_card": "Gift cards sold or issued, until they are spent",
    "revenue": "Net sales",
    "returns": "Net value of returned goods",
    "restocking": "Restocking fees kept on returns",
    "cogs": "FIFO cost of goods sold",
    "vat_input": "VAT paid on supplier bills and expenses",
    "payables": "Supplier bills not yet paid",
    "cheques_issued": "Cheques written to suppliers until they clear",
    "other_purchases": "Supplier bill lines that are not stock",
    "trade_in": "Trade-in value promised against a sale, until the sale uses it",
    "petty_cash": "Each branch's petty cash float",
    "expense_rent": "Rent expenses",
    "expense_utilities": "DEWA, internet and phone expenses",
    "expense_salaries": "Salaries and wages paid as expenses",
    "expense_transport": "Fuel, taxis and delivery expenses",
    "expense_marketing": "Advertising and marketing expenses",
    "expense_maintenance": "Repairs and maintenance expenses",
    "expense_office": "Office supplies and stationery",
    "expense_bank_fees": "Bank charges and card terminal fees",
    "expense_other": "Expenses in no other category",
    "grni": "Stock received or imported at cost, until the supplier's bill arrives",
    "shrinkage": "Stock written off (or found) by adjustments and counts, at cost",
    "other_income": "Bounced-cheque fees and other non-sales income",
    "opening_equity": "Owner's capital and opening balances",
    "retained_earnings": "Profit carried forward when a year is closed",
    "corporate_tax": "UAE corporate tax provided, not yet paid",
    "corporate_tax_expense": "UAE corporate tax charged against profit",
}
EXPENSE_PAID_FROM = {"PETTY_CASH": "petty_cash", "BANK": "transfer", "CARD": "transfer"}
Chart = dict[str, tuple[str, str]]


def chart_of_accounts(db: Session) -> Chart:
    overrides = load_settings(db).gl_accounts or {}
    chart: Chart = {}
    for key, (code, name) in ACCOUNTS.items():
        custom = overrides.get(key) or {}
        chart[key] = (custom.get("code") or code, custom.get("name") or name)
    return chart


def account_rows(db: Session) -> list[GlAccountOut]:
    chart = chart_of_accounts(db)
    return [
        GlAccountOut(
            key=key,
            use=ACCOUNT_USES[key],
            code=chart[key][0],
            name=chart[key][1],
            default_code=code,
            default_name=name,
        )
        for key, (code, name) in ACCOUNTS.items()
    ]


def save_accounts(db: Session, data: GlAccountsWrite) -> list[GlAccountOut]:
    unknown = set(data.accounts) - set(ACCOUNTS)
    if unknown:
        raise ApiError(422, "validation_error", f"Unknown accounts: {', '.join(sorted(unknown))}.")
    overrides = {}
    for key, entry in data.accounts.items():
        code, name = ACCOUNTS[key]
        custom = {}
        if entry.code.strip() and entry.code.strip() != code:
            custom["code"] = entry.code.strip()
        if entry.name.strip() and entry.name.strip() != name:
            custom["name"] = entry.name.strip()
        if custom:
            overrides[key] = custom
    load_settings(db).gl_accounts = overrides or None
    db.commit()
    return account_rows(db)


@dataclass
class JournalLine:
    day: date
    journal: str
    reference: str
    account: str
    debit: int = 0
    credit: int = 0
    memo: str = ""
    # The document this line came from ("sale:<id>", "bill:<id>", ...); the ledger posts one entry per source.
    source: str = ""


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Choose a period of at most 400 days that ends after it starts.")
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def _day(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


def journal(db: Session, start: date, end: date, store_id: uuid.UUID | None) -> list[JournalLine]:
    since, until = _bounds(start, end)
    chart = chart_of_accounts(db)
    lines: list[JournalLine] = []
    fallback: dict[uuid.UUID, int] = {}

    def item_cost(item: SaleItem) -> int:
        """FIFO cost of a sold line; lines sold from unbatched stock use the latest purchase cost."""
        if item.cost_cents is not None:
            return item.cost_cents
        if item.product_id not in fallback:
            fallback[item.product_id] = costing.fallback_unit_cost(db, item.product_id) or 0
        return fallback[item.product_id] * item.quantity * (item.unit_factor or 1)

    sales = (
        select(Sale)
        .options(selectinload(Sale.items), selectinload(Sale.tenders))
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
    )
    returns = select(SaleReturn).where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
    if store_id is not None:
        sales = sales.where(Sale.store_id == store_id)
        returns = returns.where(SaleReturn.store_id == store_id)
    for sale in db.scalars(sales).unique():
        day, ref = _day(sale.created_at), sale.invoice_number or sale.client_sale_id[:8].upper()
        source = f"sale:{sale.id}"
        received = defaultdict(int)
        for tender in sale.tenders:
            received[tender.method] += tender.amount_cents
        if not sale.tenders and sale.payment_method != "on_account" and sale.amount_paid_cents:
            # Sales synced before split tenders carry only their payment method.
            received[sale.payment_method] += min(sale.amount_paid_cents, sale.total_cents)
        covered = sum(received.values())
        tip = sale.tip_cents or 0
        if covered < sale.total_cents + tip:
            received["on_account"] += sale.total_cents + tip - covered
        for method, amount in received.items():
            account = chart.get(method, chart["cash"])[0]
            lines.append(JournalLine(day, "SALES", ref, account, debit=amount, memo=method, source=source))
        service = sale.service_charge_cents or 0
        # A gift card sold is money held for the customer, not revenue, until it is spent.
        gift_cards = sum(item.line_total_cents for item in sale.items if item.gift_card_code)
        net = sale.total_cents - sale.tax_cents - service - gift_cards
        lines.append(JournalLine(day, "SALES", ref, chart["revenue"][0], credit=net, source=source))
        if gift_cards:
            lines.append(
                JournalLine(
                    day,
                    "SALES",
                    ref,
                    chart["gift_card"][0],
                    credit=gift_cards,
                    memo="gift card",
                    source=source,
                )
            )
        if service:
            lines.append(JournalLine(day, "SALES", ref, chart["service_charge"][0], credit=service, source=source))
        if tip:
            lines.append(JournalLine(day, "SALES", ref, chart["tips"][0], credit=tip, memo="tip", source=source))
        if sale.tax_cents:
            lines.append(JournalLine(day, "SALES", ref, chart["vat"][0], credit=sale.tax_cents, source=source))
        cost = sum(item_cost(item) for item in sale.items)
        if cost:
            memo = "Includes estimated cost" if any(item.cost_cents is None for item in sale.items) else ""
            lines.append(JournalLine(day, "COGS", ref, chart["cogs"][0], debit=cost, memo=memo, source=source))
            lines.append(JournalLine(day, "COGS", ref, chart["inventory"][0], credit=cost, source=source))
    return_rows = list(db.scalars(returns))
    tenders: dict[uuid.UUID, list[ReturnTender]] = defaultdict(list)
    if return_rows:
        for tender in db.scalars(
            select(ReturnTender).where(ReturnTender.return_id.in_([row.id for row in return_rows]))
        ):
            tenders[tender.return_id].append(tender)
    returned_items: dict[uuid.UUID, list[tuple[ReturnItem, SaleItem]]] = defaultdict(list)
    if return_rows:
        for returned, sold in db.execute(
            select(ReturnItem, SaleItem)
            .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
            .where(ReturnItem.return_id.in_([row.id for row in return_rows]))
        ):
            returned_items[returned.return_id].append((returned, sold))
    for record in return_rows:
        day, ref = _day(record.created_at), record.credit_note_number or str(record.id)[:8].upper()
        source = f"return:{record.id}"
        net = record.total_refund_cents - record.tax_refund_cents + record.restocking_fee_cents
        lines.append(JournalLine(day, "RETURNS", ref, chart["returns"][0], debit=net, source=source))
        if record.tax_refund_cents:
            lines.append(
                JournalLine(day, "RETURNS", ref, chart["vat"][0], debit=record.tax_refund_cents, source=source)
            )
        if record.restocking_fee_cents:
            lines.append(
                JournalLine(
                    day, "RETURNS", ref, chart["restocking"][0], credit=record.restocking_fee_cents, source=source
                )
            )
        for tender in tenders.get(record.id, []):
            account = chart.get(tender.method, chart["cash"])[0]
            lines.append(JournalLine(day, "RETURNS", ref, account, credit=tender.amount_cents, source=source))
        restored = sum(
            item_cost(sold) * returned.quantity // max(sold.quantity, 1)
            for returned, sold in returned_items.get(record.id, [])
        )
        if restored:
            lines.append(JournalLine(day, "COGS", ref, chart["inventory"][0], debit=restored, source=source))
            lines.append(JournalLine(day, "COGS", ref, chart["cogs"][0], credit=restored, source=source))
    payments = select(CustomerLedgerEntry).where(
        CustomerLedgerEntry.entry_type == "PAYMENT",
        CustomerLedgerEntry.sale_id.is_(None),
        CustomerLedgerEntry.created_at >= since,
        CustomerLedgerEntry.created_at < until,
    )
    if store_id is None:
        for entry in db.scalars(payments):
            day, amount = _day(entry.created_at), -entry.amount_cents
            ref = entry.reference or str(entry.id)[:8].upper()
            source = f"receipt:{entry.id}"
            account = chart.get(entry.method or "cash", chart["cash"])[0]
            lines.append(JournalLine(day, "RECEIPTS", ref, account, debit=amount, source=source))
            lines.append(JournalLine(day, "RECEIPTS", ref, chart["on_account"][0], credit=amount, source=source))
    lines.extend(_payables_lines(db, chart, start, end, store_id))
    lines.extend(_expense_lines(db, chart, start, end, store_id))
    lines.extend(_trade_in_lines(db, chart, start, end, store_id))
    lines.extend(_stock_lines(db, chart, since, until, store_id))
    if store_id is None:
        for run in staff_service.finalized_in(db, since, until):
            day, ref = _day(run.finalized_at), f"PAYROLL {run.year}-{run.month:02d}"  # type: ignore[arg-type]
            source = f"payroll:{run.id}"
            net = sum(line.net_cents for line in run.lines)
            if net:
                lines.append(JournalLine(day, "PAYROLL", ref, chart["expense_salaries"][0], debit=net, source=source))
                lines.append(JournalLine(day, "PAYROLL", ref, chart["transfer"][0], credit=net, source=source))
        lines.extend(_bank_lines(db, chart, start, end))
        lines.extend(_cheque_lines(db, chart, since, until))
        lines.extend(_channel_lines(db, chart, since, until))
    return lines


def _channel_lines(db: Session, chart: Chart, since: datetime, until: datetime) -> list[JournalLine]:
    """A delivery app's payout clears what it owed: the bank gets the payout, the commission it kept is expense."""
    lines: list[JournalLine] = []
    for payout in channel_service.payouts_between(db, since, until):
        day, ref, source = (
            _day(payout.received_at),
            payout.reference or str(payout.id)[:8].upper(),
            f"payout:{payout.id}",
        )
        if payout.amount_cents:
            lines.append(
                JournalLine(day, "CHANNELS", ref, chart["transfer"][0], debit=payout.amount_cents, source=source)
            )
        if payout.commission_cents:
            lines.append(
                JournalLine(
                    day, "CHANNELS", ref, chart["channel_commission"][0], debit=payout.commission_cents, source=source
                )
            )
        settled = payout.amount_cents + payout.commission_cents
        if settled:
            lines.append(JournalLine(day, "CHANNELS", ref, chart["channel"][0], credit=settled, source=source))
    return lines


TRADE_IN_PAYOUT_ACCOUNTS = {"CASH": "cash", "STORE_CREDIT": "store_credit", "SALE_CREDIT": "trade_in"}


def _trade_in_lines(db: Session, chart: Chart, start: date, end: date, store_id: uuid.UUID | None) -> list[JournalLine]:
    lines: list[JournalLine] = []
    for trade_in in trade_in_service.period_trade_ins(db, start, end, store_id):
        if not trade_in.offer_cents:
            continue
        day, source = _day(trade_in.created_at), f"tradein:{trade_in.id}"
        payout = chart[TRADE_IN_PAYOUT_ACCOUNTS[trade_in.payout]][0]
        lines.append(
            JournalLine(
                day,
                "TRADEINS",
                trade_in.number,
                chart["inventory"][0],
                debit=trade_in.offer_cents,
                memo=f"Grade {trade_in.grade}",
                source=source,
            )
        )
        lines.append(JournalLine(day, "TRADEINS", trade_in.number, payout, credit=trade_in.offer_cents, source=source))
    return lines


def _expense_lines(db: Session, chart: Chart, start: date, end: date, store_id: uuid.UUID | None) -> list[JournalLine]:
    registered = load_settings(db).vat_registered
    lines: list[JournalLine] = []
    for expense in expense_service.period_expenses(db, start, end, store_id):
        recoverable = expense_service.recoverable_tax(expense, registered)
        account = chart[f"expense_{expense.category.lower()}"][0]
        source = f"expense:{expense.id}"
        lines.append(
            JournalLine(
                expense.spent_on,
                "EXPENSES",
                expense.number,
                account,
                debit=expense.total_cents - recoverable,
                memo=expense.description,
                source=source,
            )
        )
        if recoverable:
            lines.append(
                JournalLine(
                    expense.spent_on,
                    "EXPENSES",
                    expense.number,
                    chart["vat_input"][0],
                    debit=recoverable,
                    source=source,
                )
            )
        paid_from = chart[EXPENSE_PAID_FROM.get(expense.paid_from, "transfer")][0]
        lines.append(
            JournalLine(
                expense.spent_on, "EXPENSES", expense.number, paid_from, credit=expense.total_cents, source=source
            )
        )
    since, until = _bounds(start, end)
    for entry in expense_service.petty_cash_moves(db, since, until):
        if store_id is not None and entry.store_id != store_id:
            continue
        day, ref = _day(entry.created_at), f"PETTY {str(entry.id)[:8].upper()}"
        source = f"petty:{entry.id}"
        if entry.kind == "TOPUP":
            other = chart["cash"][0] if entry.source == "till" else chart["transfer"][0]
        else:
            other = chart["expense_other"][0]
        debit, credit = (chart["petty_cash"][0], other) if entry.amount_cents > 0 else (other, chart["petty_cash"][0])
        amount = abs(entry.amount_cents)
        lines.append(JournalLine(day, "EXPENSES", ref, debit, debit=amount, memo=entry.note, source=source))
        lines.append(JournalLine(day, "EXPENSES", ref, credit, credit=amount, source=source))
    return lines


SUPPLIER_PAYMENT_ACCOUNTS = {"cash": "cash", "transfer": "transfer", "card": "transfer", "cheque": "cheques_issued"}


def _payables_lines(db: Session, chart: Chart, start: date, end: date, store_id: uuid.UUID | None) -> list[JournalLine]:
    """Bills: stock lines clear "stock received, not billed" (the receipt already put the stock on the books);
    other lines are purchases. Payments settle payables; supplier cheques sit in cheques issued until cleared."""
    lines: list[JournalLine] = []
    bills = select(SupplierBill).where(
        SupplierBill.bill_date >= start, SupplierBill.bill_date <= end, SupplierBill.status != "VOID"
    )
    if store_id is not None:
        bills = bills.where(SupplierBill.store_id == store_id)
    for bill in db.scalars(bills).unique():
        ref, source, day = f"BILL {bill.number}", f"bill:{bill.id}", bill.bill_date
        stock = sum(line.quantity * line.unit_cost_cents for line in bill.lines if line.product_id is not None)
        if stock:
            lines.append(JournalLine(day, "PURCHASES", ref, chart["grni"][0], debit=stock, source=source))
        if bill.subtotal_cents - stock:
            lines.append(
                JournalLine(
                    day, "PURCHASES", ref, chart["other_purchases"][0], debit=bill.subtotal_cents - stock, source=source
                )
            )
        if bill.tax_cents:
            lines.append(JournalLine(day, "PURCHASES", ref, chart["vat_input"][0], debit=bill.tax_cents, source=source))
        lines.append(JournalLine(day, "PURCHASES", ref, chart["payables"][0], credit=bill.total_cents, source=source))
    if store_id is not None:
        return lines
    payments = select(SupplierPayment).where(
        SupplierPayment.paid_on >= start, SupplierPayment.paid_on <= end, SupplierPayment.status != "VOID"
    )
    for payment in db.scalars(payments).unique():
        ref = payment.reference or (f"CHQ {payment.cheque_number}" if payment.cheque_number else str(payment.id)[:8])
        source = f"payment:{payment.id}"
        account = chart[SUPPLIER_PAYMENT_ACCOUNTS.get(payment.method, "cash")][0]
        lines.append(
            JournalLine(
                payment.paid_on, "PAYMENTS", ref, chart["payables"][0], debit=payment.amount_cents, source=source
            )
        )
        lines.append(JournalLine(payment.paid_on, "PAYMENTS", ref, account, credit=payment.amount_cents, source=source))
    since, until = _bounds(start, end)
    cleared = select(SupplierPayment).where(
        SupplierPayment.status == "CLEARED", SupplierPayment.cleared_at >= since, SupplierPayment.cleared_at < until
    )
    for payment in db.scalars(cleared).unique():
        day, ref = _day(payment.cleared_at), f"CHQ {payment.cheque_number}"  # type: ignore[arg-type]
        source = f"cheque_clear:{payment.id}"
        lines.append(
            JournalLine(day, "PAYMENTS", ref, chart["cheques_issued"][0], debit=payment.amount_cents, source=source)
        )
        lines.append(
            JournalLine(day, "PAYMENTS", ref, chart["transfer"][0], credit=payment.amount_cents, source=source)
        )
    return lines


def _stock_lines(
    db: Session, chart: Chart, since: datetime, until: datetime, store_id: uuid.UUID | None
) -> list[JournalLine]:
    """Stock coming in at cost (purchase-order receipts and imported purchase batches) and stock written off."""
    lines: list[JournalLine] = []
    receipts = select(GoodsReceipt).where(GoodsReceipt.created_at >= since, GoodsReceipt.created_at < until)
    if store_id is not None:
        receipts = receipts.where(GoodsReceipt.store_id == store_id)
    for receipt in db.scalars(receipts).unique():
        costs = {
            row.id: row.unit_cost_cents
            for row in db.scalars(
                select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == receipt.purchase_order_id)
            )
        }
        value = sum(line.quantity * costs.get(line.purchase_order_line_id, 0) for line in receipt.lines)
        if value:
            day, source = _day(receipt.created_at), f"grn:{receipt.id}"
            lines.append(JournalLine(day, "STOCK", receipt.number, chart["inventory"][0], debit=value, source=source))
            lines.append(JournalLine(day, "STOCK", receipt.number, chart["grni"][0], credit=value, source=source))
    trade_in_items = select(TradeIn.batch_item_id).where(TradeIn.batch_item_id.is_not(None))
    batches = (
        select(PurchaseBatch)
        .where(
            PurchaseBatch.created_at >= since,
            PurchaseBatch.created_at < until,
            PurchaseBatch.status != "REVERSED",
            ~PurchaseBatch.items.any(BatchItem.id.in_(trade_in_items)),
        )
        .options(selectinload(PurchaseBatch.items))
    )
    if store_id is not None:
        batches = batches.where(PurchaseBatch.store_id == store_id)
    for batch in db.scalars(batches).unique():
        value = sum(item.quantity_imported * item.purchase_cost_per_unit for item in batch.items)
        if value:
            day, source = _day(batch.created_at), f"batch:{batch.id}"
            ref = batch.batch_number
            lines.append(JournalLine(day, "STOCK", ref, chart["inventory"][0], debit=value, source=source))
            lines.append(JournalLine(day, "STOCK", ref, chart["grni"][0], credit=value, source=source))
    shrink: dict[tuple[uuid.UUID, date], int] = defaultdict(int)
    for when, store, value in management_reports.shrinkage(db, since, until, store_id):
        shrink[(store, _day(when))] += value
    codes = {row.id: row.code for row in db.scalars(select(Store))}
    for (store, day), value in shrink.items():
        if not value:
            continue
        ref, source = f"SHRINK {codes.get(store, '')} {day.isoformat()}", f"shrink:{store}:{day.isoformat()}"
        loss, stock = chart["shrinkage"][0], chart["inventory"][0]
        debit, credit = (loss, stock) if value > 0 else (stock, loss)
        lines.append(
            JournalLine(day, "STOCK", ref, debit, debit=abs(value), memo="Adjustments and counts", source=source)
        )
        lines.append(JournalLine(day, "STOCK", ref, credit, credit=abs(value), source=source))
    return lines


def _bank_lines(db: Session, chart: Chart, start: date, end: date) -> list[JournalLine]:
    """Card and QR takings reach the bank: the gross leaves the settlement account (the fee is its own expense)."""
    lines: list[JournalLine] = []
    matched = select(BankStatementLine).where(
        BankStatementLine.status == "MATCHED",
        BankStatementLine.booked_on >= start,
        BankStatementLine.booked_on <= end,
        BankStatementLine.matched_key.like("card:%")
        | BankStatementLine.matched_key.like("qr:%")
        | BankStatementLine.matched_key.like("bnpl:%"),
    )
    for row in db.scalars(matched):
        prefix = (row.matched_key or "").split(":", 1)[0]
        clearing = chart[prefix if prefix in ("qr", "bnpl") else "card"][0]
        gross = row.amount_cents + row.fee_cents
        ref, source = (row.reference or row.matched_label)[:80], f"bankline:{row.id}"
        lines.append(
            JournalLine(
                row.booked_on, "BANK", ref, chart["transfer"][0], debit=gross, memo=row.matched_label, source=source
            )
        )
        lines.append(JournalLine(row.booked_on, "BANK", ref, clearing, credit=gross, source=source))
    return lines


def _cheque_lines(db: Session, chart: Chart, since: datetime, until: datetime) -> list[JournalLine]:
    """Customer cheques: cleared ones move from cheques in hand to the bank; bounced or returned ones go back onto
    the customer's account, with any bounce fee as other income."""
    lines: list[JournalLine] = []
    events = db.execute(
        select(ChequeEvent, Cheque)
        .join(Cheque, ChequeEvent.cheque_id == Cheque.id)
        .where(
            ChequeEvent.occurred_at >= since,
            ChequeEvent.occurred_at < until,
            ChequeEvent.to_status.in_(("CLEARED", "BOUNCED", "CANCELLED")),
        )
    )
    for event, cheque in events:
        day, ref = _day(event.occurred_at), f"CHQ {cheque.cheque_number}"
        source = f"cheque:{event.id}"
        held = chart["cheque"][0]
        if event.to_status == "CLEARED":
            lines.append(
                JournalLine(day, "CHEQUES", ref, chart["transfer"][0], debit=cheque.amount_cents, source=source)
            )
            lines.append(JournalLine(day, "CHEQUES", ref, held, credit=cheque.amount_cents, source=source))
            continue
        memo = "Bounced" if event.to_status == "BOUNCED" else "Returned to customer"
        lines.append(
            JournalLine(
                day, "CHEQUES", ref, chart["on_account"][0], debit=cheque.amount_cents, memo=memo, source=source
            )
        )
        lines.append(JournalLine(day, "CHEQUES", ref, held, credit=cheque.amount_cents, source=source))
        if event.to_status == "BOUNCED" and cheque.bounce_fee_cents:
            fee = cheque.bounce_fee_cents
            lines.append(
                JournalLine(day, "CHEQUES", ref, chart["on_account"][0], debit=fee, memo="Bounce fee", source=source)
            )
            lines.append(JournalLine(day, "CHEQUES", ref, chart["other_income"][0], credit=fee, source=source))
    return lines


def journal_csv(lines: list[JournalLine], currency: str, chart: Chart | None = None) -> str:
    names = {code: name for code, name in (chart or ACCOUNTS).values()}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "journal", "reference", "account", "account_name", "debit", "credit", "currency", "memo"])
    for line in sorted(lines, key=lambda row: (row.day, row.journal, row.reference)):
        writer.writerow(
            [
                line.day.isoformat(),
                line.journal,
                line.reference,
                line.account,
                names.get(line.account, ""),
                f"{line.debit / 100:.2f}" if line.debit else "",
                f"{line.credit / 100:.2f}" if line.credit else "",
                currency,
                line.memo,
            ]
        )
    return buffer.getvalue()


# --- PINT AE ---------------------------------------------------------------------------------------

UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
ET.register_namespace("", UBL)
ET.register_namespace("cac", CAC)
ET.register_namespace("cbc", CBC)
TAX_CODES = {"STANDARD": "S", "ZERO": "Z", "EXEMPT": "E"}


def _tax_code(item, product, rate: int) -> str:
    """UBL tax category: S when VAT was charged; E or Z for the customer's relief on the line; else the
    product's own category (a standard-rated product charged no VAT is zero-rated)."""
    if rate:
        return "S"
    if item.tax_treatment == "EXEMPT":
        return "E"
    if item.tax_treatment in ("ZERO_EXPORT", "DESIGNATED_ZONE"):
        return "Z"
    category = product.tax_category if product else "STANDARD"
    return TAX_CODES.get(category, "S") if category != "STANDARD" else "Z"


def _el(parent: ET.Element, ns: str, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)
    if text is not None:
        node.text = text
    return node


def _amount(parent: ET.Element, tag: str, cents: int, currency: str) -> None:
    _el(parent, CBC, tag, f"{cents / 100:.2f}", currencyID=currency)


def _party(
    parent: ET.Element, tag: str, *, name: str, trn: str | None, address: str | None, emirate: str | None
) -> None:
    holder = _el(parent, CAC, tag)
    party = _el(holder, CAC, "Party")
    if trn:
        _el(party, CBC, "EndpointID", trn, schemeID="0235")
    postal = _el(party, CAC, "PostalAddress")
    if address:
        _el(postal, CBC, "StreetName", address)
    if emirate:
        _el(postal, CBC, "CountrySubentity", emirate)
    _el(_el(postal, CAC, "Country"), CBC, "IdentificationCode", "AE")
    if trn:
        scheme = _el(party, CAC, "PartyTaxScheme")
        _el(scheme, CBC, "CompanyID", trn)
        _el(_el(scheme, CAC, "TaxScheme"), CBC, "ID", "VAT")
    legal = _el(party, CAC, "PartyLegalEntity")
    _el(legal, CBC, "RegistrationName", name)


def pint_ae_invoice(db: Session, sale_id: uuid.UUID, store_scope: uuid.UUID | None) -> bytes:
    """UBL 2.1 tax invoice following the PINT AE profile (UAE e-invoicing)."""
    sale = (
        db.scalars(
            select(Sale).options(selectinload(Sale.items)).where(Sale.id == sale_id, Sale.is_quote_proforma.is_(False))
        )
        .unique()
        .one_or_none()
    )
    if sale is None or (store_scope is not None and sale.store_id != store_scope):
        raise ApiError(404, "not_found", "Sale was not found.")
    settings = load_settings(db)
    store = db.get(Store, sale.store_id)
    customer = db.get(Customer, sale.customer_id) if sale.customer_id else None
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in sale.items})))
    }
    currency = sale.currency
    root = ET.Element(f"{{{UBL}}}Invoice")
    _el(root, CBC, "CustomizationID", "urn:peppol:pint:billing-1@ae-1")
    _el(root, CBC, "ProfileID", "urn:peppol:bis:billing")
    _el(root, CBC, "ID", sale.invoice_number or sale.client_sale_id[:8].upper())
    issued = sale.created_at if sale.created_at.tzinfo else sale.created_at.replace(tzinfo=UTC)
    _el(root, CBC, "IssueDate", f"{issued:%Y-%m-%d}")
    _el(root, CBC, "IssueTime", f"{issued:%H:%M:%S}")
    if sale.due_date is not None:
        _el(root, CBC, "DueDate", f"{sale.due_date:%Y-%m-%d}")
    _el(root, CBC, "InvoiceTypeCode", "380")
    _el(root, CBC, "DocumentCurrencyCode", currency)
    _el(root, CBC, "TaxCurrencyCode", currency)
    _party(
        root,
        "AccountingSupplierParty",
        name=settings.legal_name or (store.name if store else "Seller"),
        trn=settings.trn,
        address=store.address if store else None,
        emirate=store.emirate if store else None,
    )
    _party(
        root,
        "AccountingCustomerParty",
        name=(customer.company_name or customer.name) if customer else "Walk-in customer",
        trn=customer.trn_vat_number if customer else None,
        address=customer.address if customer else None,
        emirate=None,
    )
    groups: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for item in sale.items:
        product = products.get(item.product_id)
        rate = item.tax_rate_bps if item.tax_rate_bps is not None else (500 if item.tax_cents else 0)
        bucket = groups[(_tax_code(item, product, rate), rate)]
        bucket[0] += item.line_total_cents - item.tax_cents
        bucket[1] += item.tax_cents
    tax_total = _el(root, CAC, "TaxTotal")
    _amount(tax_total, "TaxAmount", sale.tax_cents, currency)
    for (code, rate), (taxable, tax) in groups.items():
        subtotal = _el(tax_total, CAC, "TaxSubtotal")
        _amount(subtotal, "TaxableAmount", taxable, currency)
        _amount(subtotal, "TaxAmount", tax, currency)
        category = _el(subtotal, CAC, "TaxCategory")
        _el(category, CBC, "ID", code)
        _el(category, CBC, "Percent", f"{rate / 100:g}")
        _el(_el(category, CAC, "TaxScheme"), CBC, "ID", "VAT")
    totals = _el(root, CAC, "LegalMonetaryTotal")
    net = sale.total_cents - sale.tax_cents
    _amount(totals, "LineExtensionAmount", net, currency)
    _amount(totals, "TaxExclusiveAmount", net, currency)
    _amount(totals, "TaxInclusiveAmount", sale.total_cents, currency)
    _amount(totals, "PrepaidAmount", sale.amount_paid_cents, currency)
    _amount(totals, "PayableAmount", sale.total_cents - sale.amount_paid_cents, currency)
    for position, item in enumerate(sale.items, start=1):
        product = products.get(item.product_id)
        line = _el(root, CAC, "InvoiceLine")
        _el(line, CBC, "ID", str(position))
        _el(line, CBC, "InvoicedQuantity", str(item.quantity), unitCode="H87")
        _amount(line, "LineExtensionAmount", item.line_total_cents - item.tax_cents, currency)
        details = _el(line, CAC, "Item")
        _el(details, CBC, "Name", item.description or (product.name if product else "Item"))
        if product is not None:
            _el(_el(details, CAC, "SellersItemIdentification"), CBC, "ID", product.sku)
        category = _el(details, CAC, "ClassifiedTaxCategory")
        rate = item.tax_rate_bps if item.tax_rate_bps is not None else (500 if item.tax_cents else 0)
        _el(category, CBC, "ID", _tax_code(item, product, rate))
        _el(category, CBC, "Percent", f"{rate / 100:g}")
        _el(_el(category, CAC, "TaxScheme"), CBC, "ID", "VAT")
        price = _el(line, CAC, "Price")
        unit_net = (item.line_total_cents - item.tax_cents) / max(1, item.quantity)
        _el(price, CBC, "PriceAmount", f"{unit_net / 100:.2f}", currencyID=currency)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def pint_ae_zip(db: Session, start: date, end: date, store_scope: uuid.UUID | None) -> bytes:
    since, until = _bounds(start, end)
    query = select(Sale.id, Sale.invoice_number, Sale.client_sale_id).where(
        Sale.created_at >= since, Sale.created_at < until, Sale.is_quote_proforma.is_(False), Sale.status.in_(POSTED)
    )
    if store_scope is not None:
        query = query.where(Sale.store_id == store_scope)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for sale_id, number, client_id in db.execute(query):
            archive.writestr(f"{number or client_id[:8].upper()}.xml", pint_ae_invoice(db, sale_id, store_scope))
    return buffer.getvalue()
