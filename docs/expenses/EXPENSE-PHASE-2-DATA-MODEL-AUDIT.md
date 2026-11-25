# Expense phase 2 — data model audit

Inspected before the additive migration `20261125_0139`. Existing expense rows stay in `expenses`. No second ledger was added.

## Current expense schema

`expenses` already stores number, branch, category code, description, payee text, supplier TRN, supplier id (from `20261125_0138`), amounts, currency, tax-invoice flag, payment source, reference, and void status.

Category was a 12-character code: `RENT`, `UTILITIES`, `SALARIES`, `TRANSPORT`, `MARKETING`, `MAINTENANCE`, `OFFICE`, `BANK_FEES`, `OTHER`. There was no category table.

## Supplier model

`suppliers` is the existing directory (`id`, `name`, `code`, phone, email, TRN, active flag). Expenses already point at it with nullable `supplier_id`. Payables remain a separate bill workflow.

## File storage

Product photos go through `media_storage` and are served without sign-in at `/media/{tenant}/{key}`. Repair files sit under `storage/repairs` and download only through an authorized route. Expense bills follow the repair pattern: bytes under `storage/expense-bills`, metadata in `expense_attachments`, download only through `GET /api/v1/expenses/{id}/bill`.

## Additive changes

- `expense_categories`: id, tenant, code, name, normalized name, description, active flag, sort order, created and updated by, timestamps. Unique per tenant on code and on the normalized name.
- `expenses.category` widened to 32 characters. Existing codes are unchanged.
- `expenses.category_id` nullable. The application links an old code to the seeded category. A code that does not match is left as text.
- `expense_attachments`: one row per expense, file name, content type, original size, stored size, storage key, checksum, status `STORED`, uploader, timestamp. The image bytes are not in the database.
- Both new tables use the same tenant row-level policy as the other operational tables.

The nine original names are inserted for the tenant the first time categories are read. They are not renamed.

## Backward compatibility

Old clients may still send `category: "UTILITIES"`. New clients send `category_id`. A repeated category name returns the existing row instead of inserting a second one. Historical expenses keep their code and, once linked, their category name even after that category is deactivated.
