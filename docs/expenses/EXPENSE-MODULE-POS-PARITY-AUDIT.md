# Expense module — POS parity audit

Audited before the register page was added. The register is a client of the existing expense API. No second expense table, petty-cash balance, or VAT calculator was added.

## Business Pro feature inventory

`apps/web/src/features/expenses/ExpensesPage.tsx` is the working module.

- Summary cards: spent in the period, recoverable VAT, petty cash balance.
- Filters: branch, from date, to date.
- Expense table: date, description, category, payee, number, void reason, paid from, VAT, total, void.
- Side panels: spending by category, petty cash book (latest entries).
- Record expense: category, date, what for, paid to, total paid, VAT treatment, tax-invoice toggle, supplier TRN, paid from (petty cash, bank, card), reference.
- Petty cash top-up from bank or till, and a physical count that posts the difference.
- Void is the correction path. There is no in-place edit of a recorded expense.

Finance navigation in Business Pro already lists Expenses behind `expenses:manage`.

## Existing backend

| Piece | Location |
|---|---|
| Routes | `GET/POST /api/v1/expenses`, `POST /api/v1/expenses/{id}/void`, `GET /api/v1/expenses/petty-cash/{store_id}`, `POST /api/v1/expenses/petty-cash/top-up`, `POST /api/v1/expenses/petty-cash/count` |
| Service | `apps/api/app/services/expense_service.py` |
| Schema | `apps/api/app/schemas/expenses.py` |
| Shared types | `packages/shared-types/src/expenses.ts` |

The router has no separate capability flag. Access is `expenses:manage`. Register PIN tokens were portal-only; they now use the same portal-and-pos scope already used for customers and sales. The permission check is unchanged. Cashiers do not have `expenses:manage`.

## Database schema

Table `expenses`: number, store, closed category enum, description, free-text payee, optional 15-digit payee TRN, date, net, tax, total, currency, tax-invoice flag, paid from, reference, status `RECORDED` or `VOID`, creator, voider, void reason.

Checks: total greater than zero, tax from zero up to but not including the total.

Table `petty_cash_entries` is append-only: kind `TOPUP`, `EXPENSE`, `VOID`, or `COUNT`, signed amount, `balance_after`, optional expense link, top-up source `bank` or `till`, note, user. The balance is the latest `balance_after`. There is no mutable balance column.

`expenses.supplier_id` optionally points at `suppliers`. `expense_categories` holds the tenant types, including the original nine codes. `expenses.category_id` points at one of them. `expense_attachments` stores one compressed bill per expense outside the public media folder.

## Payment behavior

- Petty cash: the service refuses the expense when the branch float is short (`petty_cash_short`), then posts one negative `EXPENSE` entry. Void posts one positive `VOID` entry for the same total.
- Bank and card: stored as `paid_from` plus an optional reference. The expense service does not pick a bank account and does not authorize a card.
- One request creates one expense. Petty cash is the only payment source that also writes the float ledger.
- A count posts the difference immediately. That is the existing Business Pro count, not a separate approval table.

## VAT

When the client omits `tax_cents`, the service uses the tenant tax policy:

`tax = div_half_up(total_cents * rate, 10_000 + rate)` for a standard rate, and zero for zero-rated or exempt.

Recoverable VAT is that tax only when the business is VAT-registered and the expense is marked as having a tax invoice. A tax invoice with tax and no 15-digit TRN is rejected (`trn_required`). Business Pro’s VAT card mentions VAT201 box 9. That sentence is portal copy for the current return, not a second calculator. The register states the same rule without hard-coding a box or a 5% rate.

## Supplier relationship

`supplier_id` is the supplier record. Payee remains optional text, and the TRN remains the tax-invoice identifier. A paid expense does not create an accounts-payable bill.

## Petty cash workflow

Top-up records branch, amount, source, note, and user. Count shows the book balance, accepts the counted cash and a note of at least three characters, and posts the difference. The book lists opening movements, top-ups, expenses, voids, and counts with a running `balance_after`.

## Attachments

Business Pro does not store a bill image on an expense. There is no expense file service to reuse. Adding one only on the register would split the two apps.

## Permissions

One key: `expenses:manage` (“Record expenses and petty cash”). It sits with the back-office manager permissions, so Store Manager and Super Admin have it. Cashier does not. Super Admin already grants or revokes it from the existing role screen. Separate keys such as `expenses.view` or `expenses.manage_categories` do not exist and were not added.

## What the register did not have

The desktop app had no Expenses page and the native retail allow-list did not include `/api/v1/expenses`. Both now call the routes above. Expense creation stays online. It is not placed on the sale sync queue.

## Still absent from the authoritative model

- Search, pagination, and print beyond the period list.
- PDF bills. Only JPEG, PNG, and WebP are stored, as one compressed WebP.
- A bank-account picker or card authorization.
- Offline expense creation. The API has no idempotency key, so an offline queue could post the same expense twice.
