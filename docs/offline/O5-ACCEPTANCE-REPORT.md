# O5 acceptance report

Status: **PASSED WITH LIMITATIONS**.

O5 extends `sync_queue` and the existing idempotency hash. It does not replace the queue. No production deployment. No developer, inventory-acceptance, laundry, or production database was opened. No Alembic revision was added.

## What was implemented

- Same key and same payload stays `applied` / `duplicate`. A second dispatch does not run.
- Same key and a different payload stays HTTP 409 `idempotency_conflict`. The register stores `status = 'conflict'` and does not auto-retry.
- After a unique-key `IntegrityError`, a batch whose keys already exist with the same hash returns `duplicate` instead of a generic 409. A different hash still returns `idempotency_conflict`.
- 422 and 413 stay `rejected` and are not selected by `next_pending_batch`.
- Network, 401, and 5xx stay `pending` and retry the original key.
- A later pass keeps that rule and lets the next independent batch upload when one batch returns HTTP 500. See `SYNC-CENTER-PENDING-UPLOAD-ROOT-CAUSE-AND-FIX.md`. `sync_queue.last_attempt_at` records the last try.
- The status bar shows a conflict chip when a conflict batch exists, including when the pending count is zero.
- No reconciliation endpoint was added. Financial and stock adjustments remain **AWAITING APPROVAL**.

## Files

- `apps/api/app/services/sync_service.py` — `_duplicates_after_rollback`
- `apps/api/tests/test_sync.py` — changed sale payload does not replace the original total
- `apps/desktop/src-tauri/src/sync.rs` — `queue_status_for`, conflict quarantine
- `apps/desktop/src-tauri/src/sync_center.rs`, `erp.rs`, `lib.rs` — `conflict_count`
- `apps/desktop/src-tauri/src/bootstrap.rs` — conflict row survives restart
- `apps/desktop/src/lib/syncActivity.ts`, `tauri.ts`
- `apps/desktop/src/components/shell/statusBar.ts`, `KeyboardStatusBar.tsx`, `statusBar.test.ts`
- The O5 documents in `docs/offline/`

`sync_queue` later gained `last_attempt_at` for Sync Center. See the pending-upload report. Inventory services were not edited. Staff administration was not added. Pharmacy offline medicine checkout was not enabled. Card, QR, and pay-later still require a verified provider `PAID` result. `single_terminal_offline_stock_enabled` was not switched on.

## Executed tests

API, from the repo root:

`node scripts/python.mjs -m pytest tests/test_bootstrap.py tests/test_terminal_activation.py tests/test_permanent_entitlement.py tests/test_sync.py -q --tb=line`

24 passed in 25.90s. This includes the existing duplicate, stock-once, idempotency-conflict, and batch-rollback tests, plus `test_a_changed_sale_payload_does_not_replace_the_original`.

Desktop library, from `apps/desktop/src-tauri`:

`cargo test --lib -- --test-threads=8`

42 passed. This includes `a_payload_collision_is_not_a_successful_sync` and `a_conflict_stays_out_of_the_pending_queue_and_keeps_its_payload`.

Vitest, from `apps/desktop`:

`pnpm exec vitest run src/components/shell/statusBar.test.ts src/features/checkout/checkout.pharmacy.test.ts src/features/checkout/checkout.entitlement.test.ts`

23 passed. The new status-bar case expects `Queue · 1 conflict` when pending and failed are zero.

These counts are this O5 run. They are not the O4 counts.

## Limitations

- Native Tauri window: **NOT RUN**. Browser tests are not native acceptance. The WebView/GPU blank surface is unchanged.
- PostgreSQL RLS with `ai_pos_app`: **NOT RUN**.
- Two simultaneous HTTP requests for one key were not executed. The recovery function is in `push_batch`, and the sequential duplicate and hash-mismatch tests passed.
- A socket that dies after commit was not killed in a test. The register leaves that batch `pending` and the server duplicate path is what the retry hits.
- No backoff jitter was added.
- No approved financial or stock reconciliation action exists. Those conflicts stay stored. Adjustment is **AWAITING APPROVAL**.
- Remote suspension and staff permission changes still apply only after the terminal syncs.
- Multi-terminal offline stock safety is not established. Stock allocation was not implemented.
- Release builds still require the production entitlement public key. The test key is not a production key.
- One request is still atomic. A conflict or rejection rolls back that request. Mixed `applied` and `conflict` results are not returned in one HTTP 200.

## Carry-forward

O1 remains PASSED. O2, O3, and O4 remain PASSED WITH LIMITATIONS. O6, O7, and O8 remain NOT STARTED. The offline platform remains IN PROGRESS.
