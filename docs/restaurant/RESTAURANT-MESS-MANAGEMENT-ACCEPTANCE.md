# Mess management

Status: **BLOCKED**

Date: 22-11-2026

## Audit

No mess member, meal plan, meal schedule, consumption, or mess billing tables or routers exist. Customers and `customer_ledger_entries` are the only account records.

## Why it was not built in this pass

Monthly mess charges must become normal invoices and ledger entries, and a retry must not create a second invoice. There is no billing-period key to reuse. Adding a new charge writer without that key and without a disposable-database test would risk duplicate receivables.

No POS navigation was added for Mess. No migration was added. No offline consumption queue was added.

## Next phase

1. Add member, plan, and consumption tables that reference `customers.id`.
2. Give them their own permission keys, not a cashier-wide grant.
3. Generate the period invoice through the existing sale and `ledger_service.post_sale` path, keyed by tenant, member, and billing period.
4. Take repayments through `POST /api/v1/customers/{id}/payments`.
5. Prove one retry does not create a second invoice on a disposable database.
