# Business settings bidirectional sync

Status: **PASSED WITH LIMITATIONS**

Date: 25-11-2026

The 22-section settings project stays **IN PROGRESS**. Finance is the next section and was not changed here.

## Canonical source

One `business_settings` row. POS and Business Pro do not keep a second copy of the tenant identity. The register SQLite table only caches the last accepted response.

Identity columns written by this phase:

| Field | Key | Type | Required | Scope | POS edit | Business Pro edit |
|---|---|---|---|---|---|---|
| Legal name | `legal_name` | string, max 160 | Yes on save | Tenant | Business-wide `settings:manage` | Same permission |
| Arabic legal name | `legal_name_ar` | string, max 160, or null | No | Tenant | Same | Same |
| Country | `country` | ISO code in the country list, or null | No | Tenant | Same | Same |
| Location | `location` | string, max 120, or null | No | Tenant | Same | Same |
| Store code | `store_code` | string | Read only | Tenant | No | No |
| Business type | `business_profile` | existing profile | Read only on this screen | Tenant | No | Existing profile screen, unchanged |

A country save on `PUT /api/v1/settings/identity` does not call the tax retune. `standard_rate_bps` stays as it was. The VAT screen can still send country through `PUT /api/v1/settings/tax`, and that older route still retunes the rate. That is a tax-section behavior and was left in place.

## API

`PUT /api/v1/settings/identity`

The caller must be a signed-in user with `settings:manage`, a portal or POS token, and no branch (`store_id` is null). The body is `legal_name`, `legal_name_ar`, `country`, `location`, and `expected_revision`.

When the four stored values already match, the handler returns the current row and does not increment `cache_generation`. When they differ, `expected_revision` must equal `cache_generation`. A mismatch returns 409 `stale_settings` with the current identity, revision, timestamp, and actor. The row is not overwritten.

An accepted change sets `updated_by_id`, commits, and the existing before-flush listener increments `cache_generation` once. The existing audit service records `settings.identity` with the old and new values. `details.source` is `pos` for a POS token and `business_pro` for a portal token. `client_device` is `desktop` or `web`.

There is no settings WebSocket. Business Pro already reloads `GET /api/v1/settings` every 20 seconds and ignores an older revision. A signed-in POS now does the same, including while Settings is open. The open identity form is not replaced while the cashier is typing. A newer revision is announced and can be reloaded. Save is enabled only after a 2xx response. Offline unlock does not send the change and does not queue it.

## Permissions covered by the API tests

- POS PIN of the business-wide admin saves the identity and does not change the tax rate.
- The same payload sent again with the old revision does not bump the revision and does not add a second audit row.
- A different location with the old revision returns 409.
- A portal token then saves the new location on the next revision.
- `GET /api/v1/settings` shows that location.
- Empty legal name and country `ZZ` return 422.
- Cashier PIN, device key, and a branch user who has `settings:manage` return 403. The legal name is unchanged.
- A disabled admin cannot sign in with the PIN, and a token issued before the account was disabled is rejected with 401.

This database has one tenant settings row. A second tenant was not created. Cross-tenant overwrite is not a separate code path.

## Tests

`node scripts/python.mjs -m pytest tests/test_settings.py -q --tb=line`

7 passed, 0 failed, 6.42s, exit 0. That file includes the identity happy path and the rejection cases.

Desktop: `pnpm exec vitest run src/features/settings/settingsAudit.test.ts src/features/settings/settingsIdentity.test.ts src/features/settings/settingsRoutes.test.ts --reporter=dot` — 3 files, 9 tests, 0 failed, 1.69s, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` and from `apps/web` — both exit 0.

`cargo test --lib settings::` — 3 passed, exit 0. `cargo test --lib retail::` — 4 passed, exit 0. The retail allow-list now includes `/api/v1/settings` so the register can call the identity route with the signed-in user token. The API still enforces permission and branch scope.

## Not claimed

- Screenshots of POS and Business Pro side by side.
- Two running POS terminals.
- A settings WebSocket. Delivery is the existing 20-second settings poll.
- Offline queue for identity. The save is refused while the register is offline. The 25-11-2026 connectivity pass did not add one.
- Removal of legal name and country from the VAT form.
- Finance, tax rates, products, customers, or any other settings section.
