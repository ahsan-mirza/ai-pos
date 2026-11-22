# Offline acceptance report

No production deployment. No production, developer, or inventory-acceptance migration.

## Carried from the laundry register

- `RegisterErrorBoundary` stops a render throw from leaving the native WebView empty. `pnpm exec vitest run src/components/RegisterErrorBoundary.test.tsx` — 3 passed.
- The scan form mounts only on Scan Garment.
- The native station walk was not repeated. The earlier white client area is recorded in `docs/laundry/LAUNDRY-PHASE-3.2-NATIVE-POS-UX-ACCEPTANCE.md`.
- Business Pro `/laundry/production` was not opened.
- Orders LD-7B77A286, LD-9584F748, and LD-4F3A07CA were not modified.

## Platform

| Gate | Status |
| --- | --- |
| O1 Architecture audit | PASSED |
| O2 Permanent activation | PASSED WITH LIMITATIONS |
| O3 Bootstrap and incremental pull | PASSED WITH LIMITATIONS |
| O4 Local-first checkout and transaction persistence | PASSED WITH LIMITATIONS |
| O5 Conflict resolution | PASSED WITH LIMITATIONS |
| O6 Stock allocation | PASSED WITH LIMITATIONS |
| O7 Local staff administration | PASSED WITH LIMITATIONS |
| O8 Full offline integration | PASSED WITH LIMITATIONS |
| O8.2 Acceptance closure | IN PROGRESS |
| O8.3 Security and native closure | IN PROGRESS |
| O8.4 Technical closure | IN PROGRESS |

Overall offline platform: IN PROGRESS.

O2 permanent entitlement is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O2-ACCEPTANCE-REPORT.md`. The sealed-file restart and DPAPI round trip ran in the desktop library tests. The Tauri window was not restarted. The WebView/GPU blank surface remains a separate blocker.

O3 catalogue bootstrap and incremental pull is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O3-ACCEPTANCE-REPORT.md`. The product snapshot, commit-ordered feed, and local generation tests ran. PostgreSQL row-level security and the native register window did not. Per-terminal stock allocation and local staff administration were not built in that O3 run.

O4 local checkout persistence is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O4-ACCEPTANCE-REPORT.md`. The catalogue generation now includes one frozen currency and tax document. A queued sale keeps its price, tax, and `tax_rate_bps` after a later rate change, and the sale or return queue row is committed with the event. This run: API 17 passed in 21.19s, desktop library 40 passed, checkout vitest 8 passed. The O3 report's 15, 37, and 7 are that phase's own results. Native Windows and PostgreSQL RLS remain not run. Those O4 counts are not O5 results.

O5 event conflicts are PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O5-ACCEPTANCE-REPORT.md`. A reused idempotency key with the same payload stays a duplicate. A reused key with a different payload is quarantined as `conflict` and is not retried. This run: API 24 passed in 25.90s, desktop library 42 passed, status and checkout-gate vitest 23 passed. Financial adjustment of a conflict is AWAITING APPROVAL. Native Windows and PostgreSQL RLS were not run. O6 through O8 were not started in that O5 run.

O6 per-terminal stock allocation is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O6-ACCEPTANCE-REPORT.md`. Grants reserve `quantity_reserved` and sales still post through `move_stock`. This run: API 24 passed in 18.55s, desktop library 46 passed, allocation and pharmacy vitest 4 passed. A disconnected terminal does not lose its reservation. Native Windows and PostgreSQL RLS were not run. O7 and O8 were not started in that O6 run.

O7 local staff administration is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O7-ACCEPTANCE-REPORT.md`. A cashier created on one register unlocks there while marked `LOCAL ACTIVE · PENDING SERVER PROVISIONING`, and another register receives the Argon2 verifier only after the server accepts the event. That run: API 27 passed in 20.58s, desktop library 50 passed, staff, allocation, and pharmacy vitest 6 passed. The financial `sync_queue` shape was not changed. Native Windows and PostgreSQL RLS were not run. The Staff & Access screen did not yet submit create or disable in that O7 run.

O8 integration is PASSED WITH LIMITATIONS. Evidence is in `docs/offline/O8-FINAL-ACCEPTANCE-REPORT.md`. Offline product selection uses the verified SQLite allocation remainder, Staff & Access submits create, edit, PIN reset, and disable, and online PIN login verifies an Argon2 verifier. That O8 run: API 28 passed in 28.21s, desktop library 51 passed, allocation, pharmacy, and staff vitest 7 passed. Native Windows and PostgreSQL RLS were not run in that O8 run. The production entitlement public key is AWAITING APPROVAL.

`docs/offline/O8.2-INTEGRATION-ACCEPTANCE-REPORT.md` records a later integration pass: API 20 passed in 16.00s, desktop library 53 passed, vitest 7 passed. At the time that note was written, revision `20261122_0130` had not been executed.

O8.2 closure is IN PROGRESS. Evidence is the O8.2 section of `docs/offline/O8-FINAL-ACCEPTANCE-REPORT.md`. This run: API 28 passed in 27.37s, desktop library 53 passed in 11.21s, vitest 7 passed. PostgreSQL RLS as `ai_pos_app` on disposable database `axizpos_o82` at `127.0.0.1:55941` is PASSED WITH LIMITATIONS (`o82_rls_disposable.py`, 15 passed, 0 failed). Native Windows is NOT RUN. The production public key, lost-terminal write-off, and financial conflict adjustment stay AWAITING APPROVAL. Alembic `20261122_0130` was applied only to that disposable database, which was then stopped and deleted. No protected database was opened. Nothing was deployed. The platform is not fully accepted.

O8.3 is PASSED WITH LIMITATIONS in `docs/offline/O8.3-SECURITY-NATIVE-CLOSURE-REPORT.md`. That note's run was API 21 passed in 16.14s, desktop library 54 passed, and vitest 39 passed. Native Windows was not run there. The production public key stays AWAITING APPROVAL.

A later O8.3 pass is IN PROGRESS. Evidence is `docs/offline/O8.3-TECHNICAL-LIMITATION-CLOSURE-REPORT.md`. This pass: API 31 passed in 24.95s on SQLite, and disposable RLS `axizpos_o83` on `127.0.0.1:55942` as `ai_pos_app` was 13 passed, 0 failed, including FastAPI `GET /api/v1/users` and `GET /api/v1/products`. Revision `20261122_0131` was applied only there, then the cluster was deleted. Native Windows is BLOCKED. Write-off and conflict posting stay AWAITING APPROVAL. Nothing was deployed.

O8.4 is PASSED WITH LIMITATIONS. Evidence is `docs/offline/O8.4-FINAL-TECHNICAL-CLOSURE-REPORT.md`. This run: API 26 passed in 15.87s, and disposable RLS `axizpos_o84` on `127.0.0.1:55952` as `ai_pos_app` was 14 passed, 0 failed, including a FastAPI allocation list. The pharmacy acceptance executable launched, moved, and restored. Full native checkout and the five profile walks were not completed. Production key, stock write-off posting, and financial posting stay AWAITING APPROVAL. The disposable cluster was deleted. Nothing was deployed.

The checkout follow-up is IN PROGRESS. Evidence is `docs/offline/O8.4-ACTIVATION-TO-CHECKOUT-ACCEPTANCE-REPORT.md`. The grocery register completed an online cash sale, an offline allocation sale, and an overdraw block. Process at the end of that pass was 36972, window `0x2608D8`. Staff, barcode hardware, and the other four profiles were not walked.

The activation follow-up is IN PROGRESS. Evidence is `docs/offline/O8.4-ACTIVATED-NATIVE-ACCEPTANCE-REPORT.md`. The register activated through the screen against disposable `axizpos_o84act` on `127.0.0.1:55944`, process 37880, window `0xD0658`, and stopped at username unlock. Checkout was not opened.

A later O8.4 pass is IN PROGRESS. Evidence is `docs/offline/O8.4-NATIVE-AND-FINAL-ACCEPTANCE-REPORT.md`. This pass built and launched `com.axizpos.offline.acceptance`, process 40664, window `0x671290`. The activation form stayed drawn after move, resize, minimize, restore, and being covered. Desktop library 54 passed in 11.22s. Vitest 266 passed in 4.79s. API 41 passed in 33.81s. Disposable RLS `axizpos_o84` on `127.0.0.1:55943` was 16 passed, 0 failed, then the cluster was deleted. Checkout and the five profile walks were not run. The production key and both postings stay AWAITING APPROVAL. Nothing was deployed.
