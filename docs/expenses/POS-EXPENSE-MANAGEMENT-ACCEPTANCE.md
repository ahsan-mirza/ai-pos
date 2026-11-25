# POS expense management — acceptance

Status: **PASSED WITH LIMITATIONS**

Phase 2 adds tenant categories, the supplier id already on the expense, and one compressed bill. Native Windows acceptance of that flow was not run. See `EXPENSE-NATIVE-BIDIRECTIONAL-ACCEPTANCE.md`.

The register Expenses page uses `GET/POST /api/v1/expenses` and the petty-cash routes. Totals, VAT, and the float come back from those responses. The page does not keep its own ledger.

## What matches Business Pro

- Sidebar item **Expenses**, shown only when the signed-in user has `expenses:manage`.
- Cards for spent in the period, recoverable VAT, and petty cash.
- Branch, from, and to filters. A user tied to one branch stays on that branch.
- Record form fields: category, date, what for, paid to, total paid, VAT treatment, tax invoice, supplier TRN, paid from, reference.
- Category list is the shared enum. VAT preview uses `businessTax().standard_rate_bps` and the same half-up inclusive split as the API. The request omits `tax_cents`, so the server amount is the one that is stored.
- Currency comes from the business setting, then from the stored expense row.
- Void asks for a reason and calls the existing void route.
- On the desktop register, an offline expense is stored in SQLite as Pending Sync or Pending Review. It is not a ledger posting until `/api/v1/expenses` accepts it. The browser preview still cannot save an expense without the API. See `docs/offline/POS-OFFLINE-STARTUP-AND-API-CONNECTIVITY-ACCEPTANCE.md`.

## Limitations

- Native window and a signed-in browser pass were not run. The preview was on the unlock screen, and the PIN was not entered.
- No search, pagination, PDF, or print. Business Pro’s list does not have those either.
- No second approval step. Recorded expenses are corrected by void, which is the existing rule.
- Bank and card store `paid_from` and a reference. They do not select a bank account.

## Automated checks

- `apps/desktop/src/features/expenses/expenseForm.test.ts` covers the VAT split and the first invalid field.
- `tests/test_expenses.py::test_register_pin_can_read_expenses` covers a till token with the permission and a cashier without it.
