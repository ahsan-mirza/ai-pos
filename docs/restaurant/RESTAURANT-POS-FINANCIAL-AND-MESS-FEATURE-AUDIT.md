# Restaurant POS financial and mess audit

Date: 22-11-2026

## What already existed

| Area | Authority | POS before this pass |
| --- | --- | --- |
| Completed sales | `GET /api/v1/sales` and `GET /api/v1/sales/{id}`, permission `portal:reports_read`. Branch users are limited to `principal.store_id` | Shift Sales inside Sale Shift, local SQLite only. No bill browser |
| Invoice PDF | `GET /api/v1/sales/{id}/invoice.pdf` renders the saved sale via `invoice_pdf.render_sale_invoice` | Last sale only, through `open_document_pdf` |
| Receipt reprint | Local `ReceiptDoc` from the shift row | No `DUPLICATE RECEIPT` marker. Drawer kick is already off for reprints |
| Customer ledger | `customer_ledger_entries`. `ledger_service.post_sale` and `receive_payment` append entries and derive `current_balance_cents`. Oldest open invoice is paid first | Checkout can put a sale on account when `b2b_credit` and `pos:credit_sale` are on. No repayment screen |
| Customer list and statement | `GET /api/v1/customers`, `GET /api/v1/customers/{id}/statement`, `POST /api/v1/customers/{id}/payments`. Permission `customers:manage`. Payments also require the `b2b_credit` module | Customer search at checkout only |
| Split checks | Item checks become separate sales. An equal split is one sale with guest tenders from `equalShares` | No receipt-output choice |
| Export | Portal VAT CSV/PDF at `GET /api/v1/reports/vat/export` for `reports:vat` | No POS export |
| Mess | No member, meal-plan, consumption, or mess-invoice tables | None |

The register passthrough did not allow `/api/v1/sales`. This pass added that prefix so Bill History can call the existing list. It does not add a second sales table.

Cashier system role does not include `portal:reports_read` or `customers:manage`. Those screens stay hidden for that role. The API still rejects a direct call.

## Offline

Bill history, customer repayment, and export call the live API. The register does not keep a complete tenant bill archive, and a failed request does not write a local payment. Ordinary cash sales keep the existing queue. Mess consumption was not added, so there is no new offline queue.

## Not built, and why

Mess Management has no existing customer-linked billing model. A new monthly charge path was not added in this pass, because a retry could post a second invoice. The next phase is a mess schema whose invoices and repayments go through `ledger_service` with a billing-period idempotency key.

A tenant ZIP, XLSX package, and database backup were not added. The register must not see database credentials.
