# O3 acceptance report

O3 is **PASSED WITH LIMITATIONS**.

No production deployment. No developer database, inventory-acceptance database, or production database was opened or migrated. Alembic `20261122_0124` and `20261122_0125` were not applied. API tests used in-memory SQLite. The sequence test used a temporary file SQLite database. Register tests used temporary database files. The installed register was not started.

O2 entitlement rules were not changed. A valid permanent entitlement still ignores a stale 24-hour lease. A legacy register with no entitlement still uses that lease. Invalid signatures and binding mismatches still block selling. Pharmacy medicine checkout stays blocked while offline. `sync_queue` was not replaced. Stock was not allocated to a terminal. Staff administration was not added.

A disconnected register still cannot learn a remote suspension, a staff disable, or a permission change until it syncs.

## What was implemented

- `POST /api/v1/terminals/bootstrap/sessions` copies the product catalogue for the authenticated device's branch after locking `catalog_feed_counters`.
- Pages read `bootstrap_snapshot_items`. They do not read live product rows.
- Product insert, update, and delete through the SQLAlchemy `Product` model append `catalog_changes` in the same transaction as the counter update.
- `GET /api/v1/terminals/bootstrap/pull` takes an HMAC cursor bound to the tenant, branch, terminal, and session.
- The register stages pages in `bootstrap_stage` and replaces `products` only when the staged count matches. The queue is not in that transaction.
- Pull batches commit the product change and `last_seq` together. A gap does not move the cursor.

## Commands and counts

From `apps/api` with `apps/api/.venv`:

`node scripts/python.mjs -m pytest tests/test_bootstrap.py tests/test_terminal_activation.py tests/test_permanent_entitlement.py tests/test_sync.py::test_duplicate_event_does_not_apply_twice -q --tb=line`

15 passed in 18.30s. That includes the snapshot, scope, retention, two-writer sequence, and 102-product page tests, plus the O2 activation, entitlement, and duplicate-sale tests.

A separate run of `tests/test_bootstrap.py::test_one_hundred_products_use_five_pages` printed `o3 bootstrap 102 products in 5 pages took 0.099s`. That is the session and page time after the rows were already inserted. It is not a production catalogue.

From `apps/desktop/src-tauri`:

`cargo test --lib -- --test-threads=8`

37 passed, 0 failed. That includes the two bootstrap SQLite tests and the existing entitlement, DPAPI, and sealed-restart tests.

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/checkout.entitlement.test.ts src/features/checkout/checkout.pharmacy.test.ts`

7 passed.

## Matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| Authorized terminal can bootstrap | PASSED | `test_bootstrap.py` session and pages |
| Tenant and branch isolation | PASSED WITH LIMITATIONS | Second device denied. PostgreSQL RLS was not run |
| Snapshot does not mix later edits | PASSED | Rename after the session stays off the repeated page and appears on the pull |
| Pagination is bounded and retryable | PASSED | `limit=1`, page count equals the snapshot count, repeating the first page returns the same rows |
| Partial bootstrap is not complete | PASSED | Rust test activates only when the staged count matches |
| Interrupted bootstrap keeps the previous catalogue | PASSED | Short second generation leaves the first product and the queued sale |
| Change feed is commit-ordered | PASSED | Two threads, sequences 1..24, no gaps |
| Cursor is server-issued and checked | PASSED | Tamper, other terminal, other session, retention |
| Duplicate events do not corrupt rows | PASSED | Repeating sequence 1 keeps the edited name and the snapshot quantity |
| Cursor commits with the data | PASSED | A gap returns an error and `last_seq` stays put |
| Queue and sale idempotency unchanged | PASSED | Queued sale remains. `test_duplicate_event_does_not_apply_twice` passed |
| O2 entitlement behaviour unchanged | PASSED | Entitlement pytest, Rust entitlement tests, checkout vitest |
| Pharmacy offline block unchanged | PASSED | `checkout.pharmacy.test.ts` |
| Stock allocation not implemented | PASSED | No stock-ledger diff. Snapshot quantity is the existing branch cache |
| Staff administration not implemented | PASSED | PIN cache is not a bootstrap dataset |
| Native Tauri window | NOT RUN | The register window was not started |
| Large-catalogue timing | PASSED WITH LIMITATIONS | 102 products, page size 25, 5 pages, 0.099s. A production-sized catalogue was not timed |

## Datasets

Allowlist: `products`.

Not downloaded by this protocol: tax and receipt settings (`settings.rs`), currencies, staff PIN hashes, customers, menus, serials, `inventory_levels`, `stock_movements`, `sync_queue`.

## Files

API: `app/services/bootstrap_service.py`, `app/models/bootstrap.py`, `app/routers/v1/terminals.py`, `alembic/versions/20261122_0125_catalog_bootstrap.py`, `tests/test_bootstrap.py`.

Register: `src-tauri/src/db.rs`, `src-tauri/src/bootstrap.rs`, `src-tauri/src/sync.rs`, `src-tauri/src/entitlement.rs`, `src-tauri/src/lib.rs`, `src-tauri/src/retail.rs`.

## Limitations

- Release builds still need `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`. That O2 limit is unchanged.
- The Tauri window was not restarted offline. The WebView/GPU blank surface was not retested.
- PostgreSQL row-level security was not re-proven.
- Incremental product edits do not replace the branch quantity. A stock movement is not a catalogue event. The next snapshot copies the quantity `products_out` already returns.
- Remote staff and subscription changes still apply only after a sync.
- O4 started after this report. The native, RLS, and production-catalogue limitations above were not cleared by that later work.
