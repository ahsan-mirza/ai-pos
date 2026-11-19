# Stage 3F completion audit

Audit date: 2026-11-19. No production tenant was activated. No deployment was made. Persistent development and production databases were not used.

Stage 3B–3E narrative reports are not stored under `docs/pharmacy/`. The implementation record used here is the code, the Alembic revisions `20261118_0114` through `20261119_0120`, the tests under `apps/api/tests/test_pharmacy_*.py`, and the acceptance evidence under `acceptance/pharmacy/evidence/stage-3e-4`, `stage-3e-5`, and `stage-3e-6-1`.

## Classification

| Requirement | Status | Basis |
|---|---|---|
| Medicine catalogue fields and create/edit/archive | IMPLEMENTED BUT NOT FULLY VERIFIED | `pharmacy_catalog` service and `test_pharmacy_catalog.py`. Not re-clicked in Business Pro during this stage. |
| Receiving creates an UNRELEASED manufacturer lot, separate from the receipt number | IMPLEMENTED BUT NOT FULLY VERIFIED | `test_pharmacy_lots.py`. Not repeated in the portal UI this stage. |
| Two-person governance, appointment, approval, revocation | IMPLEMENTED BUT NOT FULLY VERIFIED | `test_pharmacy_governance.py`. Super Admin sync does not grant appointment authority. |
| Pharmacist release, required reason, confirmation | IMPLEMENTED BUT NOT FULLY VERIFIED | `test_pharmacy_release.py`. |
| Quarantine, sale rejection, recalled lots cannot be cleared, expired lots cannot be released | IMPLEMENTED BUT NOT FULLY VERIFIED | Lifecycle and release tests. |
| Recall, descendant transfers, sale and release rejection | IMPLEMENTED BUT NOT FULLY VERIFIED | `test_pharmacy_lifecycle.py`. No regulator or customer notification exists. |
| Transfers of released layers only; destination UNRELEASED; lot, expiry, and cost kept | IMPLEMENTED BUT NOT FULLY VERIFIED | Lifecycle tests. |
| Supplier returns, including partial and full | IMPLEMENTED BUT NOT FULLY VERIFIED | Lifecycle tests. |
| Strict pharmacy FEFO, multi-lot sale, full-sale rollback | IMPLEMENTED BUT NOT FULLY VERIFIED | `test_pharmacy_fefo.py`. |
| Grocery FEFO, including a 3-then-5 layer sale of 4 | IMPLEMENTED AND VERIFIED | New sqlite test `test_grocery_fefo_sells_the_earlier_layer_before_the_later_one`. Grocery still sells expired stock last. Not a Windows UI run. |
| Customer return of a medicine stays unsaleable | IMPLEMENTED AND VERIFIED | Missing hold is now applied in `hold_customer_return`. Sqlite test `test_customer_return_holds_the_medicine_layer`. The whole released layer is quarantined, including units that were not returned. There is no separate approved resale path. |
| Pharmacy offline sale blocked; next online invoice continues | IMPLEMENTED AND VERIFIED | Stage 3E.6.1 live proof: blocked charge left the series at 2; next sale was `ACCEPT-ACC2-000002`. Not repeated in this stage. |
| Tenant capability cache isolation, revisions 4 and 3 | IMPLEMENTED AND VERIFIED | Stage 3E.6.1 same-webview proof, including after register restart. Not repeated in this stage. Webview storage was not cleared to force that result. |
| Header: empty queue is not an online session; restored API does not authenticate a cached PIN | IMPLEMENTED AND VERIFIED | `registerHeaderStatus` and Stage 3E.6.1 grocery header after the reachability fix. |
| Header: connection restored shows the pending count | IMPLEMENTED BUT NOT FULLY VERIFIED | Label function now returns `Connection restored · N pending`. Unit-tested. Not shown on a Windows window in this stage. |
| Header: online sync failure | IMPLEMENTED BUT NOT FULLY VERIFIED | Label `Online · N sync failed` when the rejected-batch count is above zero and the pending queue is empty. Checkout, returns, and settings poll `rejected_count`. Not shown on a Windows window. |
| Double-click Charge | IMPLEMENTED BUT NOT FULLY VERIFIED | `chargeLock` in `CheckoutPage` returns immediately on a second call and clears in `finally`. Not exercised with a rapid double-click on a register. Server replay of the same sale id is covered by the pharmacy FEFO tests. |
| RLS forced, application role NOSUPERUSER and NOBYPASSRLS | IMPLEMENTED AND VERIFIED | Migration `20261119_0119` and Stage 3E.6.1 `isolation.txt` for `ai_pos_app` on the disposable acceptance database. Not re-probed in this stage. |
| Sale upload uses the terminal device token | IMPLEMENTED AND VERIFIED | Existing sync architecture. No defect found that would justify changing it. |
| Damaged-stock workflow | BLOCKED BY BUSINESS APPROVAL | Option A remains the recommendation. Status `DAMAGED` and sale/release rejection stay. No new "mark damaged" action. |
| Verified natural person and pharmacist licence | BLOCKED BY EXTERNAL INTEGRATION | Accounts are user ids. No licence source is connected. |
| Regulatory notification, prescriptions, controlled-drug register, insurance | NOT APPLICABLE | Out of the implemented pharmacy scope. Do not claim them. |
| Production deploy, global pharmacy activation, signed installer publication | NOT APPLICABLE | Explicitly out of this stage. |

## Code changes in this stage

1. `hold_customer_return` quarantines a `RELEASED` medicine layer after a customer return restock. It does not commit on its own. Recalled, quarantined, unreleased, damaged, and supplier-return layers keep their status. Grocery returns are unchanged because they are not lot-controlled medicines.
2. `registerHeaderStatus` shows the pending count on `Connection restored` and a failed-sync label when rejected batches exist and nothing is still pending.
3. Grocery FEFO regression test for 3 units on the earlier layer and 5 on the later layer, selling 4.

## Gaps that stay open

1. Business Pro and Windows screens for receiving, release, quarantine, recall, transfer, and returns were not clicked in this stage.
2. Double-click Charge, the restored-connection pending label, and the sync-failed label were not captured on a register window.
3. The same-webview tenant cache proof was not repeated.
4. Concurrent PostgreSQL races (`pharmacy_fefo_race.py`, `pharmacy_release_race.py`, `pharmacy_governance_race.py`) were not run. They need disposable PostgreSQL, not the sqlite suite.
5. Alembic upgrade and downgrade were not executed on a disposable database in this stage.
6. No query-plan or latency measurement was taken. No index was added.
7. Installer signing was not performed. `require-pos-signing.mjs` still refuses a production build without `AXIZPOS_SIGN_THUMBPRINT`.
8. External approvals listed in the release checklist remain pending.

## Tests in this stage

Sqlite suite, `--env=test`, not a production database:

- `test_customer_return_holds_the_medicine_layer` and `test_grocery_fefo_sells_the_earlier_layer_before_the_later_one`: 2 passed.
- Combined run of `test_pharmacy_fefo`, `test_pharmacy_lots`, `test_pharmacy_release`, `test_pharmacy_governance`, `test_pharmacy_lifecycle`, `test_pharmacy_catalog`, `test_returns`, and `test_fefo`: 47 passed, 14 failed.
- The 14 failures are outside the pharmacy modules. `test_returns.py` stamps sales `2026-10-19T08:00:00Z`, which is now more than 30 days before the test clock, so the existing sale-age rule rejects them. `test_fefo.py` tries to enable FEFO on an electronics profile, and the profile refuses that module. Neither rule was weakened.
- Desktop `registerStatus.test.ts`: 1 file passed.

PostgreSQL race scripts were not run. No Windows register was driven. No screenshot was captured.

## Stage 3F.1

The sqlite suite that failed here later passed: 63 tests, including the date-stamp repair and the electronics FEFO refusal. Disposable PostgreSQL upgrade and the three race scripts passed. Application-role isolation was checked by logging in as `ai_pos_app`. Windows, portal, and tenant-cache reactivation were not repeated. Detail is in `STAGE-3F.1-VERIFICATION-CLOSURE.md`.

## Status

Software implementation: `TECHNICALLY COMPLETE WITH LIMITATIONS`

Production authorization: `APPROVAL PENDING`
