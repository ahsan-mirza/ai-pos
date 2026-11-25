# Settings section-by-section acceptance

Overall: **IN PROGRESS**

Date: 25-11-2026

A section is not passed because its page renders or because a unit test exists. Cross-application rounds for every shared setting have not been run. No production tenant was changed.

| # | Section | Status |
|---|---|---|
| 1 | Settings audit and canonical registry | PASSED WITH LIMITATIONS |
| 2 | Business settings | PASSED WITH LIMITATIONS |
| 3 | Finance | IN PROGRESS |
| 4 | Tax & invoices | IN PROGRESS |
| 5 | Sales rules | IN PROGRESS |
| 6 | Products | IN PROGRESS |
| 7 | Customers | IN PROGRESS |
| 8 | Staff & access | IN PROGRESS |
| 9 | Modules | IN PROGRESS |
| 10 | Workflows | IN PROGRESS |
| 11 | Integrations | IN PROGRESS |
| 12 | Alerts | IN PROGRESS |
| 13 | Audit trail | PASSED WITH LIMITATIONS |
| 14 | Register | IN PROGRESS |
| 15 | Printer & drawer | IN PROGRESS |
| 16 | Connectivity | IN PROGRESS |
| 17 | Security | IN PROGRESS |
| 18 | Appearance | IN PROGRESS |
| 19 | Shortcuts | NOT APPLICABLE as a shared setting |
| 20 | Sync & data | IN PROGRESS |
| 21 | Updates | IN PROGRESS |
| 22 | Diagnostics | IN PROGRESS |

## 1. Settings audit and canonical registry

Status: **PASSED WITH LIMITATIONS**

The inventory and ownership matrix are in `SETTINGS-COMPLETE-PARITY-AUDIT.md`. The canonical record remains `business_settings`. No second settings table was added.

Limitation: individual keys are not each given a new registry row. They already live on that table and its JSON fields. Round-trip tests for every key were not run.

## 2. Business settings

Status: **PASSED WITH LIMITATIONS**

Legal name, Arabic legal name, country, and location are saved on the one `business_settings` row through `PUT /api/v1/settings/identity`. POS and Business Pro both use that route. A different payload must send the revision the caller read. The same payload does not bump the revision. Country on this route does not change the VAT rate. Evidence is in `BUSINESS-SETTINGS-BIDIRECTIONAL-SYNC-ACCEPTANCE.md`.

Limitation: two live registers and screenshots were not run. The VAT screen can still write the same columns through `PUT /api/v1/settings/tax`, and a country change there still retunes tax.

## 3–12 and 14–22

Status: **IN PROGRESS**

Each section was classified in the audit matrix. Editable behavior was not rebuilt, and the happy-path, negative-path, and edge-case matrix was not executed. Shortcuts have no shared editor, so that section is not a synchronization target.

## 13. Audit trail

Status: **PASSED WITH LIMITATIONS**

The native snapshot keeps the settings timestamp, actor, country, location, timezone, and revision. A valid instant renders as `DD-MM-YYYY HH:mm` in the business timezone. A missing or invalid instant stays on the empty sentence. Details are in `SETTINGS-AUDIT-TRAIL-ACCEPTANCE.md`.

Limitation: the POS page still does not list historical `settings.*` events. Business Pro remains that list. A native application restart was not observed on a register.

## Commands

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsAudit.test.ts src/features/settings/settingsIdentity.test.ts src/features/settings/settingsRoutes.test.ts --reporter=dot`

3 files, 9 tests, 0 failed, exit 0. Duration 1.69s. Node printed a localStorage-path warning. It did not fail the run.

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0. The same command from `apps/web` also exited 0.

From `apps/desktop/src-tauri`:

`cargo test --lib settings::` — 3 passed, 0 failed, exit 0.

`cargo test --lib retail::` — 4 passed, 0 failed, exit 0.

From the repo root:

`node scripts/python.mjs -m pytest tests/test_settings.py -q --tb=short`

The identity rejection test failed once because the branch store was not seeded and because a disabled PIN login returns 403. After those fixes, the full file passed: 7 passed, 0 failed, 6.42s, exit 0. Super Admin tests were not run. No migration was added.
