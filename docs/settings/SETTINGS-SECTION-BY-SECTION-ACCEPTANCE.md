# Settings section-by-section acceptance

Overall: **IN PROGRESS**

Date: 23-11-2026

A section is not passed because its page renders or because a unit test exists. Cross-application rounds for every shared setting have not been run. No production tenant was changed.

| # | Section | Status |
|---|---|---|
| 1 | Settings audit and canonical registry | PASSED WITH LIMITATIONS |
| 2 | Business settings | IN PROGRESS |
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
| 13 | Audit trail | IN PROGRESS |
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

Status: **IN PROGRESS**

POS shows legal name, country, location, and store code from the snapshot. Country and location now survive the native cache when the API sends them. Logo, hours, and contact edits stay in Business Pro. No POS-to-Business-Pro edit test was run for those fields.

## 3–12 and 14–22

Status: **IN PROGRESS**

Each section was classified in the audit matrix. Editable behavior was not rebuilt, and the happy-path, negative-path, and edge-case matrix was not executed. Shortcuts have no shared editor, so that section is not a synchronization target.

## 13. Audit trail

Status: **IN PROGRESS**

The blank timestamp caused by discarding `updated_at` is fixed in the native snapshot and the settings screen. Details are in `SETTINGS-AUDIT-TRAIL-ACCEPTANCE.md`.

The POS page still does not list historical `settings.*` events. Business Pro already does, from `audit_logs`.

## Commands

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsAudit.test.ts --reporter=dot`

1 file, 2 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

API pytest, Business Pro tests, Super Admin tests, and Rust tests were not run. The Rust change adds optional fields to the existing settings fetch. No migration was added. `cargo test` was not run.
