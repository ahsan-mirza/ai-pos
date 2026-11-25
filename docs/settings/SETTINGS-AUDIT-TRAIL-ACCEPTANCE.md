# Settings audit trail

Status: **PASSED WITH LIMITATIONS**

Date: 25-11-2026

## What was wrong

POS Settings → Audit trail could say `No business-settings timestamp was returned. The trail is read-only.` on a desktop register even after the API had stored `updated_at` on `business_settings`.

The desktop screen copied the native settings snapshot and set `updated_at` to an empty string. The empty string was treated as "no timestamp".

## What the path does now

`business_settings.updated_at` is returned by `GET /api/v1/settings`. The Rust settings DTO keeps it, with `updated_by_name`, `country`, `location`, `timezone`, and `entitlement_revision`, and writes that object into the native tax JSON. The Tauri snapshot exposes those fields. The POS audit page formats a real instant as `DD-MM-YYYY HH:mm`.

The clock uses the business timezone on the settings row. The default display zone is `Asia/Dubai` when the row does not name one. The stored value remains the UTC instant. `2026-11-22T20:15:00Z` displays as `23-11-2026 00:15` in `Asia/Dubai`.

An empty, blank, or unparseable instant still uses the empty sentence. An invalid timezone does too. The page does not substitute the current time. A missing actor omits `by`.

A cached tax revision that is newer than the response is not replaced. An older response cannot clear a newer timestamp.

## Audit log versus the settings timestamp

The settings row supplies the latest timestamp and actor. It is not a history. `PUT /api/v1/settings/identity` writes one `settings.identity` audit event through the existing audit service, with `source` `pos` or `business_pro` and `client_device` `desktop` or `web`. POS does not invent that event. The event list itself stays `GET /api/v1/audit-logs` in Business Pro. POS does not render that list.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsAudit.test.ts src/features/settings/settingsIdentity.test.ts src/features/settings/settingsRoutes.test.ts --reporter=dot`

3 files, 9 tests, 0 failed, exit 0. Duration 1.69s.

`pnpm exec tsc -p tsconfig.json --noEmit` — exit 0.

From `apps/desktop/src-tauri`:

`cargo test --lib settings::` — 3 passed, 0 failed, exit 0. Covers a valid timestamp, a missing timestamp, an invalid timestamp left unchanged, country and location, and rejection of an older revision.

## Limitation

A native register was not restarted to watch SQLite reload the timestamp. The cache write stores the same JSON the unit test builds. The historical event list is still not on the POS page.
