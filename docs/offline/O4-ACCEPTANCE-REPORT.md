# O4 acceptance report

O4 is **PASSED WITH LIMITATIONS**.

No production deployment. No developer database, inventory-acceptance database, or production database was opened or migrated. Alembic `20261122_0124`, `20261122_0125`, and `20261122_0126` were not applied to those databases. API tests used in-memory SQLite. Register tests used temporary database files. The installed register was not started.

`sync_queue` was not replaced. `inventory_levels` and `stock_movements` were not given a new meaning. No per-terminal stock allocation was added. Staff administration was not added. Pharmacy medicine checkout stays blocked while offline. O2 entitlement behaviour was not weakened. O5, O6, O7, and O8 were not started.

## What was implemented

- The bootstrap allowlist is `products` and `checkout_settings`.
- `checkout_settings` is one frozen document per session in `bootstrap_setting_snapshots`: currency, VAT registration, prices-include-VAT, standard rate, tax authority, TRN, legal names, and receipt JSON.
- A `BusinessSettings` insert or update writes a `catalog_changes` row with operation `settings` in the same flush as the feed counter.
- The register activates products and that settings document in one SQLite transaction. A short generation does not replace either, and does not touch `sync_queue`.
- A settings pull updates `business_settings` and `last_seq` together. A gap does not advance the cursor.
- `queue.ts` `saleItems` stores `tax_rate_bps` with the line price and tax.
- `sale_service.py` `price_lines` checks a line that carries `tax_rate_bps` against that rate, not against a later policy rate.
- Sale and return queue behaviour already in `Db::enqueue` and `returns.rs` `enqueue` was covered by the desktop tests below.

## Commands and counts

These are this run. The O3 report's 15 API tests, 37 library tests, and 7 checkout tests stay the historical O3 figures and are not added into these totals.

From `apps/api`, using `apps/api/.venv`:

`.\.venv\Scripts\python.exe -m pytest tests/test_bootstrap.py tests/test_terminal_activation.py tests/test_permanent_entitlement.py tests/test_sync.py::test_duplicate_event_does_not_apply_twice -q --tb=line`

17 passed in 21.19s. That includes the new checkout-settings snapshot and queued-rate test, the existing product snapshot and two-writer tests, and the O2 activation, entitlement, and duplicate-sale tests.

From `apps/desktop/src-tauri`:

`cargo test --lib -- --test-threads=8`

40 passed, 0 failed. That includes the O3 staging and gap tests, the queued-sale restart test, the return-and-queue test, and the checkout-settings activation test.

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/checkout.snapshot.test.ts src/features/checkout/checkout.entitlement.test.ts src/features/checkout/checkout.pharmacy.test.ts`

8 passed. Snapshot 1, entitlement 4, pharmacy 3.

`tests/test_migrations.py::test_upgrade_and_downgrade_from_the_supported_baseline` was run once with the suite above and failed while upgrading `20261118_0114` because `categories` was not present. That revision is older than O4. Alembic was not run against a protected database. The migration chain test is not counted as an O4 pass.

## Matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| Checkout dependencies audited | PASSED | `O4-CHECKOUT-DATA-DEPENDENCY-AUDIT.md` |
| Currency and tax available locally with the catalogue | PASSED | Settings page frozen at 500 bps; live row then moved to 1000 |
| O3 product snapshot and pull still work | PASSED | Existing bootstrap tests in the 17 |
| Partial configuration does not activate | PASSED | Short second generation leaves currency and the queued sale |
| Financial calculation path unchanged | PASSED | `checkout.snapshot.test.ts` expects 75 cents tax on 1500 at 500 bps, the existing `lineTax` result |
| Queued tax is not recalculated from a later rate | PASSED | `price_lines` keeps 500 bps when the policy is 1000; a line without `tax_rate_bps` is rejected |
| Sale and queue commit together | PASSED | Duplicate idempotency key does not create a second pending batch |
| Return and queue commit together | PASSED | Rust return test; a mismatched cashier leaves `pending_count` at 0 |
| Restart keeps the queued payload | PASSED | Sale and return tests reopen the temp database |
| Later price or tax does not rewrite the queued sale | PASSED | Rust sale and settings tests |
| Cash underpayment stays blocked | NOT RUN | `tenders.ts` cash branch was not modified. No new cash test was executed in this run |
| Card, QR, and pay-later need a paid intent | NOT RUN | `tenders.ts` was not modified and no offline approval was added. No new provider test was executed in this run |
| Pharmacy offline block | PASSED | 3 pharmacy vitest tests |
| O2 entitlement | PASSED | Entitlement pytest and 4 checkout entitlement tests |
| Stock ledger unchanged | PASSED | No inventory-service edit. Snapshot quantity is still `products_out` |
| Multi-till offline inventory selling | PASSED | Not enabled |
| PostgreSQL RLS with the application role | NOT RUN | Not executed |
| Native Tauri window | NOT RUN | The register window was not started |
| Injected disk failure and SQLite busy | NOT RUN | Rollback covered by transaction tests only |

## Files

API: `app/services/bootstrap_service.py`, `app/services/sale_service.py`, `app/models/bootstrap.py`, `app/models/__init__.py`, `app/schemas/payloads.py`, `alembic/versions/20261122_0126_checkout_settings_snapshot.py`, `tests/test_bootstrap.py`.

Shared types: `packages/shared-types/src/sale-item.ts`.

Register: `src-tauri/src/db.rs`, `src-tauri/src/bootstrap.rs`, `src-tauri/src/sync.rs`, `src/features/checkout/queue.ts`, `src/features/checkout/checkout.snapshot.test.ts`.

## Limitations carried forward

- PostgreSQL row-level security with the real application role was not run.
- The native Tauri window was not started. Browser vitest is not that proof. The WebView/GPU blank surface was not retested.
- Release builds still need `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`.
- A disconnected till does not see a remote price, tax, promotion, staff, or subscription change until it syncs.
- Snapshot quantity is the branch cache, not a terminal allocation.
- Staff PIN hashes are not in the bootstrap.
- Promotions, customers, and serials keep their existing caches. They are not in this generation. The serial cache does not reserve stock against another till.
- `test_migrations.py` upgrade-from-baseline was not made green. The failure is on `20261118_0114`, before the O4 revision.
