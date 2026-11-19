# Stage 3F.2 verification report

Date: 2026-11-19. No production tenant was activated. No production migration was run. The persistent development database was not used. The inventory acceptance database on `127.0.0.1:55433` was not used.

Software implementation: `TECHNICALLY COMPLETE WITH LIMITATIONS`

Production authorization: `APPROVAL PENDING`

## Environment

Disposable container `axizpos-3f2-disp-pg`, id `1573d8331ff145ac6ae87b2b65775acf3a8edb87dbf81f15b5613b8f98e4ba4f`, image `postgres:16-alpine`, published only on `127.0.0.1:55444`. It was removed with `docker stop` after the run.

| Use | Database | Login |
|---|---|---|
| Create, migrate, and grant | `stage3f2_ops`, `stage3f2_from_0119` | Container bootstrap role `axizpos_3f2` |
| Stock, return, recall, and RLS statements | Same databases | `ai_pos_app`, `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE` |

`current_user` and `session_user` were both `ai_pos_app` on every operational session. `SET ROLE` was not used. The application role was granted `USAGE` on `public` and `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the tables. It was not the table owner.

Tenants: pharmacy `11111111-1111-4111-8111-111111111111`, grocery `22222222-2222-4222-8222-222222222222`.

The only Axiz desktop process at the end of the stage was pid 59572, `D:\Work\ai-pos\acceptance\inventory\target\release\ai-pos-desktop.exe`. It was not stopped, driven, or joined by another Axiz desktop. `AXIZPOS_SIGN_THUMBPRINT` is unset.

Harness: `apps/api/tests/stage3f2_app_role.py`. Result of that run: 14 passed, 0 failed.

## Backend PostgreSQL

### 3F2-LOGIN — application login and tenant context

- Environment: `stage3f2_ops` on `127.0.0.1:55444`.
- Role: `ai_pos_app`. `rolsuper` false, `rolbypassrls` false, `rolcanlogin` true. `current_user` = `session_user` = `ai_pos_app`.
- Tenant: pharmacy, then grocery.
- Setup: pharmacy profile on tenant A and grocery profile on tenant B, seeded by the bootstrap role.
- Expected: the application login sees its own profile, and grocery does not gain the pharmacy catalogue.
- Actual: pharmacy session tenant setting was `11111111-1111-4111-8111-111111111111`, profile `pharmacy`, pharmacy catalogue on. Grocery profile `grocery`, pharmacy catalogue off.
- Evidence: role flags `(False, False, True, False)` and the two profile reads.
- Result: `PASSED`.

### 3F2-SR-FULL — one lot cannot be returned twice

- Environment and role: `stage3f2_ops`, login `ai_pos_app`, session user `ai_pos_app`.
- Tenant: pharmacy.
- Setup: one unreleased lot, quantity 5. Two sessions each tried to return all 5.
- Expected: one return, one refusal, remaining 0, status `SUPPLIER_RETURN`, one reversal, no negative quantity.
- Actual: one `ok`, one `ApiError` `insufficient_stock`. Remaining 0. Status `SUPPLIER_RETURN`. One supplier-return line and one `PURCHASE_REVERSAL`.
- Evidence: attempts `[('ok', 'ai_pos_app'), ('ApiError', 'insufficient_stock')]`.
- Result: `PASSED`.

### 3F2-SR-PARTIAL — partial return keeps the layer status

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: one unreleased lot, quantity 6. Two sessions each returned 2. A third return then sent the last 2.
- Expected: both partials succeed, status stays `UNRELEASED` while quantity remains, and the closing return sets `SUPPLIER_RETURN` at zero.
- Actual: both partials `ok`. After them, remaining 2 and status `UNRELEASED`. The closing return `ok`. Final remaining 0, status `SUPPLIER_RETURN`, three reversal movements.
- Evidence: `opened={'remaining': 2, 'status': 'UNRELEASED'}`, final `{'remaining': 0, 'status': 'SUPPLIER_RETURN'}`.
- Result: `PASSED`.

The first attempt did not pass. Both partials committed, but each had read the lot before taking a lock and then wrote the same remaining quantity. The ledger ended at 0 while the lot still showed 2. `return_to_supplier` now locks the branch balance and then the lot, and reads the quantity after that lock. The result above is the rerun. Existing sqlite supplier-return and customer-return tests still passed (`2 passed`).

### 3F2-SR-STATUS — partial return does not clear a recall

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: a recalled lot of 4, with its recall row, and a return of 1.
- Expected: remaining 3, status still `RECALLED`.
- Actual: `ok`, remaining 3, status `RECALLED`.
- Evidence: `layer={'remaining': 3, 'status': 'RECALLED'}`.
- Result: `PASSED`.

### 3F2-CR-RACE — customer returns cannot exceed the sale

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: a released lot of 4. One sale of 2. Two sessions each returned 1 of that sale, using the sale-row lock and the same restore, movement, and hold sequence as the return service. A third return of 1 followed, then another sale.
- Expected: both one-unit returns are accepted, the extra return is refused, the whole layer is quarantined, and the remaining units cannot be sold.
- Actual: both returns `ok`. The third was `SyncRejected`: return quantity exceeds what is left. Remaining 4, status `QUARANTINED`. Two `RETURN_IN` movements. One `pharmacy.lot_quarantined` audit. The later sale was `lot_quarantined`.
- Evidence: return ids `3ce870e2-b721-44c1-85f4-125e258236a3` and `4075b11a-9998-44a9-b9f3-9c25f324be7f`.
- Result: `PASSED`.

### 3F2-CR-STATUS — other layer statuses stay put

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: four released layers were sold one unit each, then set to `RECALLED`, `UNRELEASED`, `DAMAGED`, and `SUPPLIER_RETURN` before `hold_customer_return`. The recalled layer had a recall row, which the check constraint requires.
- Expected: the hold does not replace those statuses.
- Actual: each layer kept the status it had before the hold. Remaining on each was 1.
- Evidence: the four status reads after the hold.
- Result: `PASSED`.

### 3F2-CR-GROCERY — grocery return is unchanged

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: grocery. Pharmacy catalogue off.
- Setup: a grocery product with no pharmacy details, quantity 3. Sell 1, return 1, sell 1 again.
- Expected: the return restores quantity and does not quarantine the layer. A later sale still works.
- Actual: return `ok`, lot status null, remaining 3, resale `ok`.
- Evidence: `layer={'remaining': 3, 'status': None}`.
- Result: `PASSED`.

### 3F2-ROLLBACK — a failed later line leaves no stock movement

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: one transaction sold 2 from a released lot and then 1 from an unreleased lot. The sale and its cash tender were in that same transaction.
- Expected: the unreleased line rejects the transaction, and the first line's allocation, sale, tender, and movements are gone.
- Actual: `lot_unreleased`. Both on-hand quantities stayed 3. The sale row was absent, tenders 0, movements for that sale 0. `sync_events` stayed 0. This stock path does not write a sync event.
- Evidence: `good=3 bad=3 sale_left=False tenders=0 movements=0 sync=0`.
- Result: `PASSED`.

### 3F2-RECALL-FIRST — a recall that commits first blocks the sale

- Environment and role: `stage3f2_ops`, login `ai_pos_app`.
- Tenant: pharmacy.
- Setup: recall lot `RECALL-FIRST`, then attempt a sale of 1.
- Expected: the sale is refused and the quantity stays 4.
- Actual: recall `ok`. Sale `SyncRejected` `lot_recalled`. Remaining 4, status `RECALLED`.
- Evidence: `sale=('SyncRejected', 'lot_recalled Recall first is recalled and cannot be sold.')`.
- Result: `PASSED`.

### 3F2-RECALL-INFLIGHT — the transaction that holds the row lock finishes first

- Environment and role: `stage3f2_ops`, login `ai_pos_app`. A bootstrap connection only sampled `pg_stat_activity`.
- Tenant: pharmacy.
- Setup: the sale locked the released lot of 4 inside `move_stock` and held that transaction open. The recall of manufacturer lot `SALE-HOLDS` started after the lock.
- Expected: no assumption about the winner. A sale may commit only if the lot was eligible at its locked validation. Nothing negative, duplicated, or half-applied remains.
- Actual: the sale committed while it held the lock. The recall session was observed as `Lock/transactionid/active`, then its recall committed. Remaining 3, status `RECALLED`. A following sale was `lot_recalled`. One `SALE_OUT` movement.
- Evidence: outcomes `sale_committed` then recall `RF-2` `ok`. Wait sample included `Lock/transactionid/active`.
- Result: `PASSED`. The sale won because it already held the row lock. The recall applied to the units still on the layer after that commit.

### 3F2-RLS — tenant isolation under the application login

- Environment and role: `stage3f2_ops`, login `ai_pos_app`. `session_user` was `ai_pos_app`.
- Tenants: pharmacy session and grocery session, plus a connection with an empty `app.tenant_id`.
- Setup: both tenants had products, inventory, a governance officer, and a pharmacist authorization. Pharmacy also had lots, events, recalls, recall lots, and supplier returns.
- Expected: each session sees its own rows. A cross-tenant insert and an insert with no tenant raise SQLSTATE `42501`. `app.bypass_rls=on` does not reveal the other tenant, because this login is not the table owner.
- Actual: pharmacy session saw 12 lots, 20 events, 4 recalls, 4 recall lots, 1 authorization, 1 officer, 5 supplier returns, 5 supplier-return lines, 12 products, and 12 inventory rows. It saw 0 recalls for the grocery tenant. Grocery session saw 1 lot, 0 events, 0 recalls, 1 authorization, 1 officer, 1 product, and 1 inventory row. Cross-tenant insert raised `ProgrammingError` SQLSTATE `42501`. Empty tenant read 0 products and the insert raised SQLSTATE `42501`. With bypass set on, products belonging to pharmacy were still 0 in the grocery session.
- Evidence: those counts and SQLSTATE `42501`. An unclassified `ProgrammingError` was not accepted on its own.
- Result: `PASSED`.

### 3F2-MIGRATE — upgrade from the recorded previous revision

- Environment: `stage3f2_from_0119` on the same container. Migrated by `axizpos_3f2`. Read and cross-tenant insert by `ai_pos_app`.
- Previous revision: `20261119_0119`. That is the `down_revision` of `20261119_0120` and the operational parent recorded in `docs/pharmacy/STAGE-3F-PRODUCTION-READINESS.md`. It was not chosen as a guess.
- Setup: at `20261119_0119`, two tenants had a product, an inventory row, a lot, and one purchase movement. Pharmacy quantity 7, grocery quantity 4.
- Expected: upgrade to `20261119_0120` keeps those quantities, movement ids, and tenant ids. The application role sees only its tenant. A cross-tenant insert is SQLSTATE `42501`. A second upgrade does not move the head.
- Actual: version before the final upgrade was `20261119_0119`. Version after two upgrades to head was `20261119_0120`. Prior-A and Prior-B quantities, tenants, and movement ids were unchanged (`ffa531a1-62a1-44cd-93c1-c7b52a2d54c1` and `5fda4a4b-f32f-4be9-af30-890a5f843133`). The pharmacy login saw 1 `PRIOR-A` and 0 `PRIOR-B`. The cross-tenant insert SQLSTATE was `42501`.
- Evidence: the before and after snapshots were equal.
- Result: `PASSED`.

### 3F2-PERF — measured, not accepted

- Environment: `stage3f2_ops`, login `ai_pos_app`, pharmacy tenant.
- Machine: Intel Core Ultra 9 285HX, 63.4 GB RAM. Database size 22 MB.
- Volume: 214 batch items, 222 batch events, 15 products, 5 recalls, 2 tenants. The timed product had 200 released one-unit layers.
- Method: five eligibility lookups timed with `perf_counter`, including the session-identity statement. One one-unit sale, one two-line sale, and one recall timed once. No agreed threshold.
- Actual: eligibility min 5.4 ms, median 6.1 ms, max 7.2 ms, 3 statements each. Sale 34.0 ms. Two-line sale 38.4 ms. Recall 18.8 ms. The in-flight recall wait is the lock sample in `3F2-RECALL-INFLIGHT`, not a separate duration.
- Evidence: `pg_database_size` 22 MB and the row counts above.
- Result: `PASSED` as a measurement. This is not a performance acceptance.

## Windows and portal

These were not run. They are not covered by the PostgreSQL results above.

| Test | Result | Why |
|---|---|---|
| Tenant-cache reactivation in the desktop webview | `NOT RUN` | The inventory acceptance register was still running. |
| Windows double-click Charge, offline pharmacy, PIN, header counts, grocery sync, restart, tenant isolation | `NOT RUN` | Same register, pid 59572, `acceptance\inventory\target\release\ai-pos-desktop.exe`. No second Axiz desktop was started. |
| Business Pro portal customer return | `NOT RUN` | The portal UI was not opened. The backend return path is `3F2-CR-RACE`, `3F2-CR-STATUS`, and `3F2-CR-GROCERY`. |
| Installer signing | `BLOCKED` | `AXIZPOS_SIGN_THUMBPRINT` is unset. Signing was not disabled and no thumbprint was invented. |

## Still outside this stage

No approval was recorded or implemented for damaged stock, customer-return resale, natural-person identity, professional licence verification, separation of duties beyond accounts, or release, quarantine, and recall operating procedures.

## Final status

Software implementation: `TECHNICALLY COMPLETE WITH LIMITATIONS`

The PostgreSQL races, application-role RLS, and the upgrade from `20261119_0119` were run on a disposable database. Supplier-return concurrency needed a lock so the lot quantity could not drift from the ledger. Windows register, tenant-cache reactivation, and the portal return screen were not run. Signing remains blocked. Performance was measured and not accepted.

Production authorization: `APPROVAL PENDING`

No production deployment, production migration, or production tenant activation was done.
