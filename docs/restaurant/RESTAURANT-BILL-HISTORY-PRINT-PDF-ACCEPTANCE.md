# Bill history, reprint, and PDF

Status: **PASSED WITH LIMITATIONS**

Date: 22-11-2026

## Reused

`GET /api/v1/sales?limit=200`, `open_document_pdf` kind `invoice`, and `printReceipt` with `kickDrawer: false`.

## Added

Restaurant and Cafe users who hold `portal:reports_read` see **Bill History**. The list shows invoice, time, customer, total, amount due, and payment status (`Paid`, `Partially Paid`, `Unpaid`). Filters for today, yesterday, this week, this month, invoice or customer text, and payment status run on the loaded rows.

The detail panel shows saved lines, subtotal, tax, total, and paid amount. Print sends a slip titled `DUPLICATE RECEIPT`. Download PDF opens the server invoice for that sale id. A printer or PDF failure leaves the sale unchanged.

## Limits

- The API returns the latest 200 sales, not a custom date query.
- `SaleOut` has no table number, order type, cashier name, or separate discount field. Those are not invented on the screen.
- Item names fall back to the saved line description.
- Offline: the page says a connection is required. It does not invent history.
- No native window was opened, so there is no screenshot.

## Tests

Desktop `tsc -p tsconfig.json --noEmit` exit 0. The duplicate-title case is in `splitReceipts.test.ts` (3 passed, exit 0). No API suite was run.
