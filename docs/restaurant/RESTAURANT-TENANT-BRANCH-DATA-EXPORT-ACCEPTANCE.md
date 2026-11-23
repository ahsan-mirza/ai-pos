# Tenant and branch data export

Status: **PASSED WITH LIMITATIONS**

Date: 22-11-2026

## Reused

`GET /api/v1/sales?limit=200` for users with `portal:reports_read`. The API applies `principal.store_id`, so a branch user does not receive other branches.

`GET /api/v1/customers?limit=200` for users with `customers:manage`. The customer section is hidden without that permission. A direct call is still rejected by the API.

## Added

Restaurant and Cafe **Export Data** downloads a JSON file with a manifest: version, time, scope text, module, format, and record count, plus the rows. The page states the scope is the signed-in store, or every branch that sign-in may already see when `store_id` is null.

The file is built from the API JSON. It does not include password hashes, tokens, or database credentials, because those fields are not on the sale or customer responses.

## Limits

- Not a ZIP, XLSX, PDF package, or database backup.
- Not a background job. The list is at most 200 rows and does not freeze on a server export worker because no such job exists for this data.
- Inventory, recipes, payments, and mess modules are not exported here.
- Offline export is refused.
- No native download was captured.

## Tests

Desktop typecheck exit 0. Rust `retail::tests` 4 passed, exit 0, including the new `/api/v1/sales` whitelist. No API export test was run.
