# Stage 3F.1 verification closure

Date: 2026-11-19. No production tenant was activated. No production migration was run. The persistent development database was not used. The inventory acceptance container on port 55433 was not touched.

Software implementation: `TECHNICALLY COMPLETE WITH LIMITATIONS`

Production authorization: `APPROVAL PENDING`

## Verification matrix

| Item | Evidence required | Result |
|---|---|---|
| Return tests use a sale inside the 30-day sync window | `test_returns.py` passes, and a sale older than 30 days is still refused | PASSED. Default stamp is the current time. `test_sale_older_than_the_sync_window_is_refused` still expects the refusal. `test_outside_window_requires_override` still backdates the stored sale by 45 days. |
| Electronics cannot enable FEFO | Profile update returns `module_not_available` and grocery FEFO tests still pass | PASSED. `test_electronics_cannot_enable_fefo`. Grocery tests call the grocery profile. The electronics rule was not changed. |
| Wider sqlite suite | Pharmacy, return, and FEFO modules | PASSED. 63 tests, exit 0. |
| Concurrent sale of one lot | Disposable PostgreSQL race | PASSED on `pharmacy_fefo_race.py`. One sale succeeded. The other was `SyncRejected` with 1 unit left. On-hand 1, one movement, one allocation, no negative quantity. |
| Two sales of a two-lot balance | Same race | PASSED. One sale, two allocations, 2 remaining. |
| Unreleased lot is not used to fill a concurrent sale | Same race | PASSED. The loser was refused with "not released for sale." Remaining 4. |
| Concurrent release of an unreleased lot | `pharmacy_release_race.py` | PASSED. One release. The other was `already_released`. |
| Concurrent quarantine clearance | Same script | PASSED. One clearance. The other was `already_released`. |
| Duplicate pharmacist request | `pharmacy_governance_race.py` | PASSED. One `ok`, one `already_pending`. |
| Revoke versus release, and approval race | Same script | PASSED. |
| Alembic upgrade from empty | Disposable database | PASSED. Baseline empty. Final `20261119_0120`. A second `upgrade head` applied nothing. |
| Alembic downgrade and re-upgrade | Release and governance races | PASSED. Downgrade to `20261118_0116` and to `20261118_0117`, then back to `20261119_0120`. Lot quantity stayed. The dropped tables stayed dropped until the second upgrade. |
| RLS as `ai_pos_app` | Login, not a superuser `SET ROLE` | PASSED. See the role section. |
| Supplier-return and customer-return races on PostgreSQL | Disposable PostgreSQL | NOT RUN. Customer-return quarantine is covered by the sqlite test only. |
| Multi-line sale rollback on PostgreSQL | Disposable PostgreSQL | NOT RUN. Covered by the sqlite pharmacy FEFO test. |
| Concurrent recall against an in-flight sale | Disposable PostgreSQL | NOT RUN. |
| Windows double-click, header states, offline pharmacy, grocery queue | Identified pharmacy acceptance window | NOT RUN. The only Axiz process was inventory acceptance pid 12812, `acceptance\inventory\target\release\ai-pos-desktop.exe`. It was not driven. |
| Tenant cache reactivation | Same webview, both tenants | NOT RUN in this stage. Stage 3E.6.1 evidence was not repeated. |
| Business Pro portal return | Portal UI | NOT RUN. |
| Installer signing | `AXIZPOS_SIGN_THUMBPRINT` | BLOCKED — CERTIFICATE REQUIRED. The variable is unset. Signing was not disabled. |
| Damaged stock, licence, natural person, return resale, procedure approval | External approval | APPROVAL PENDING. No workflow was added. |

## Sqlite commands

```
node scripts/python.mjs --env=test -m pytest tests/test_returns.py tests/test_fefo.py -q --tb=line
```

19 passed.

```
node scripts/python.mjs --env=test -m pytest tests/test_pharmacy_fefo.py tests/test_pharmacy_lots.py tests/test_pharmacy_release.py tests/test_pharmacy_governance.py tests/test_pharmacy_lifecycle.py tests/test_pharmacy_catalog.py tests/test_returns.py tests/test_fefo.py -q --tb=line
```

63 passed in 48.71s. Exit 0.

Desktop header labels were not re-run in this stage. The previous `registerStatus.test.ts` pass still stands for the label function only.

## PostgreSQL

Container `axizpos-3f1-disp-pg`, Postgres 16, `127.0.0.1:55442`, no volume, removed after the run. It was not the inventory acceptance database and not the Compose development volume.

Operational upgrade of database `stage3f1_alembic`: empty baseline to `20261119_0120`. Pharmacy tables `batch_items`, `batch_item_events`, `pharmacist_authorizations`, `pharmacy_governance_officers`, `pharmacy_recalls`, `pharmacy_recall_lots`, `pharmacy_supplier_returns`, and `pharmacy_supplier_return_lines` have row security enabled and forced. `products` does too. A grocery product row inserted and remained readable to its own tenant.

Race databases were created and dropped by the scripts: `stage3d_disp_25834476`, `stage3e_disp_d1ca5c83`, `stage3e_disp_cdf397c4`.

The race sessions logged in as the container bootstrap role `axizpos_3f1`, which is a superuser with `BYPASSRLS`. Those passes are row-lock results. They are not application-role isolation.

### Application role

Role `ai_pos_app`: `LOGIN`, `rolsuper=false`, `rolbypassrls=false`, `rolcreatedb=false`.

`tests/stage3f1_rls_probe.py` connected as that role:

| Check | Result |
|---|---|
| Empty tenant context, recall count | 0 |
| Empty tenant context, product count | 0 |
| Insert while the tenant context is empty | `ProgrammingError` |
| Other tenant, recalls and products | 0 and 0 |
| Own tenant | 1 recall and 1 product |

The release race also printed `rls policy=tenant_isolation other_tenant_rows=0 own_tenant_rows=1` through a `SET ROLE` probe. The governance race printed `other_officers=0 other_grants=0 own_officers=2`. Those probes are supporting evidence. The login above is the application-role result.

## Performance

Host: Intel Core Ultra 9 285HX, 63.4 GB RAM. Database: the disposable Postgres 16 container, one recall row and one product row.

One hundred open-recall lookups as `ai_pos_app`, own tenant: 49.5 ms total, about 0.49 ms each. This is not a load test and is not an acceptance target.

The FEFO race, including its migration, finished in about 20 seconds. The contended part was two threads against 5 units, then 3+3, then 4 released plus 4 unreleased. No lock-wait timeout and no negative quantity were reported.

No pharmacy-specific metric was added. API errors already carry a `request_id`. There is still no separate counter for rejected allocations, recalls, quarantine, authorization changes, or sync failures.

## Installer

`scripts/require-pos-signing.mjs` still exits when `AXIZPOS_SIGN_THUMBPRINT` is missing or not 40 hex characters. The variable is unset in this environment. Status: `BLOCKED — CERTIFICATE REQUIRED`.

## Policy

Unchanged and still pending external approval:

- Damaged-stock handling. Option A is a recommendation only.
- Customer-return resale. A returned medicine stays quarantined. No release-on-return path was added.
- Natural-person identity.
- Licence verification.
- Separation of duties beyond two accounts.
- Release, quarantine, and recall operating-procedure approval.

## Cleanup

`docker stop axizpos-3f1-disp-pg` removed the container (`--rm`, no volume). A following `docker ps` filter showed no container of that name. Race databases had already been dropped. The inventory acceptance process was still running and was not stopped.

## Not claimed

Windows acceptance, tenant-cache reactivation, and the Business Pro portal were not run. PostgreSQL did not cover supplier returns, customer returns, multi-line rollback, or a recall racing a sale. Those stay open. Production is not approved.
