# Settings audit trail

Status: **IN PROGRESS**

Date: 23-11-2026

## What was wrong

POS Settings → Audit trail could say `No business-settings timestamp was returned. The trail is read-only.` on a desktop register even after the API had stored `updated_at` on `business_settings`.

The desktop screen copied the native settings snapshot and set `updated_at` to an empty string. The empty string was treated as "no timestamp".

## What changed

`GET /api/v1/settings` already returns `updated_at` and `updated_by_name`. The native settings fetch now keeps those fields, plus country and location, in the cached tax JSON. The audit page formats a real instant as `DD-MM-YYYY HH:mm` and includes the actor when the row has one.

An empty, blank, or unparseable value still uses the empty sentence. The page does not substitute the current time.

The event list is still the Business Pro audit log. POS does not yet render each `settings.*` row, and it does not add filters. That is why this section is not passed.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsAudit.test.ts --reporter=dot`

1 file, 2 tests, 0 failed, exit 0. Duration 2.64s. Node printed a localStorage-path warning. It did not fail the run.

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

The native parser change was not executed against a live register in this pass. A register that has not fetched settings since this build will still show the empty sentence until the next successful settings fetch.

## Not claimed

- A full chronological event list on POS.
- Filters by user, category, and date on POS.
- Screenshots of the Branch Portion Restaurant trail.
- A new audit table.
