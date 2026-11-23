# Customer credit and repayment

Status: **PASSED WITH LIMITATIONS**

Date: 22-11-2026

## Reused

`customer_ledger_entries` through:

- `GET /api/v1/customers`
- `GET /api/v1/customers/{id}/statement`
- `POST /api/v1/customers/{id}/payments`

`receive_payment` appends a `PAYMENT` entry, allocates oldest open invoice first, and updates `amount_paid_cents`, `due_balance_cents`, and `payment_status`. It does not delete the invoice entry. Checkout on-account sales were already posted by `post_sale` when `b2b_credit` and `pos:credit_sale` are on. That checkout path was not changed.

## Added

Restaurant and Cafe users with `customers:manage` see **Customers**. The list shows name, code, phone, status, and outstanding balance. The detail shows purchased, paid, outstanding, credit remaining, open invoices, and ledger lines.

**Receive credit payment** posts cash, card, or transfer. If `b2b_credit` is off, the form stays closed and says account credit is not enabled. A refused or offline call does not write a local payment.

## Limits

- Allocation is oldest-invoice-first, which is the existing service. The screen does not pick a different invoice.
- The payment route has no idempotency key. The button is disabled while the request runs. A second successful submit is a second payment.
- Cheque payments are left to the existing portal flow because they need cheque details.
- No native walk and no API test was run in this pass. Existing `tests/test_customer_ledger.py` was not re-executed.

## Tests

Desktop typecheck exit 0. No new API test.
