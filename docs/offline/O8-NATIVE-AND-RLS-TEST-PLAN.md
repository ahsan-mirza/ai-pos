# O8 native Windows and PostgreSQL RLS test plan

O8.11 rebuilt the Restaurant acceptance executable (SHA-256 `A3EFA32F6C63D62EA6D6EDD76984B5D63FF7B0CD40674E96256C1AC413D4C851`, PID 1908) and committed the signed catalogue on Downtown Till A. Cash invoice `O810-DTA-000001` synced once to the disposable SQLite API. No PostgreSQL cluster was created. Dine-in, a second till, occlusion, and the other profile windows remain open.

O8.10 activated Downtown Till A in `AxizPOS Restaurant Acceptance` (PID 49244) against disposable SQLite `axizpos_o810` on `127.0.0.1:18089`. The cashier opened takeaway Order #3E55. Dine-in, a second till, occlusion, and the other profile windows remain open. The O8.9 cluster `axizpos_o89` was not rerun.

O8.9 ran disposable `axizpos_o89` on `127.0.0.1:55971` as `ai_pos_app`: 20 passed, 0 failed, then the cluster was deleted. The business-wide owner enabled the Restaurant preset. The store-bound Downtown admin could not. Native Restaurant, Electronics, Fashion, and Laundry windows and Chromium occlusion remain open. The original O8.1 procedure below is unchanged.

O8.4 executed a disposable RLS run and a pharmacy acceptance launch. O8.5 then ran grocery cash checkout, an offline allocation sale, an overdraw refusal, and sync on `com.axizpos.pharmacy.acceptance`. O8.7 rebuilt that executable and accepted cashier `o85till2` on the disposable grocery API. Disposable RLS `axizpos_o87` on `127.0.0.1:55970` was 9 passed and 1 failed, then deleted. O8.8 reran that cluster: the order list 403 is `capability_disabled`, and the cluster was deleted again. Occlusion by another Chromium window and the Electronics, Fashion, Restaurant, and Laundry walks remain open. The original O8.1 procedure below is unchanged.

## PostgreSQL RLS

### Why SQLite cannot stand in

The API tests use in-memory SQLite. SQLite does not enforce the policies in Alembic. A test that passes there says nothing about `ai_pos_app`.

### Cluster

Create a new disposable PostgreSQL that is not the developer database, not the inventory-acceptance database, not the laundry-acceptance database, and not production. Record the host, port, and database name in the O8 execution report. Refuse to run if the port or database name matches a known protected environment.

Apply the migration chain on that empty database as the migration owner. Before `20261122_0125` is applied, add the missing policies in a new revision. O8.1 did not write that revision. The tables that need `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and a `tenant_isolation` policy are:

- `bootstrap_sessions`
- `bootstrap_snapshot_items`
- `catalog_feed_counters`
- `catalog_changes`
- `bootstrap_setting_snapshots`
- `terminal_allocations`
- `terminal_allocation_consumptions`
- `staff_provisioning_events`

Use the pharmacy-table predicate from `20261119_0119`: the row is visible when `tenant_id` equals `current_setting('app.tenant_id', true)`, or when `app_owner_may_bypass(table)` is true. Do not copy the older predicate that treats `app.bypass_rls = 'on'` as enough for every role. That older predicate is still on the tables created by `20261024_0071`. The suite below includes one of those tables so the bypass setting is checked for `ai_pos_app`.

### Login

Create `ai_pos_app` on this cluster only:

`LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`.

Grant `CONNECT`, schema `USAGE`, and `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the application tables. Connect with that username and password. Do not `SET ROLE`. The first query records `current_user`, `session_user`, `rolsuper`, and `rolbypassrls`. The run stops if the user is a superuser or `rolbypassrls` is true.

The migration owner may insert fixtures. The assertions run on the `ai_pos_app` connection.

### Cases

Set `app.tenant_id` with `set_config` in the same transaction as the query. Clear it between cases.

| Case | Setup | Expect on the `ai_pos_app` connection |
| --- | --- | --- |
| Tenant isolation | Two tenants, one product row each, in a table that already has the `0071` policy, and one `catalog_changes` row each after the new policy | With tenant A set, tenant B's row is absent. With the setting cleared, both are absent. `SET app.bypass_rls = 'on'` does not reveal tenant B. |
| Branch isolation | Two `terminal_allocations` in one tenant and two `store_id` values | RLS will show both, because there is no branch policy. The service query used by `consume_for_sale` (`store_id` and `device_id`) must still return one row. Record RLS and the service filter as separate results. |
| Terminal allocation isolation | Grant for device A and device B, same tenant | A select as the application role with tenant A set returns both rows. `consume_for_sale` for device A rejects device B's id. A second tenant's grant is absent under tenant A's setting. |
| Staff provisioning isolation | One `staff_provisioning_events` row in tenant A and one in tenant B | Tenant A's setting hides tenant B. A user-token request to `GET /api/v1/users/staff-feed` is 401. A device token for tenant A does not receive tenant B's `pin_verifier`. |
| Bootstrap isolation | `bootstrap_sessions` for two devices in one tenant, and a session in another tenant | Cross-tenant session is hidden. The other device in the same tenant is hidden by the bootstrap service's device check, which is an application filter, not RLS. |
| Sync event isolation | Two `sync_events` rows, two tenants, same idempotency key text | Tenant A's setting returns one row. Inserting the other tenant's id fails the `WITH CHECK`. |
| Conflict isolation | A `sync_queue` conflict is local SQLite and is not this test. The server row is the original `sync_events` hash. | A second request with the same key and a different hash stays `idempotency_conflict` and does not replace the stored payload. Run this on the disposable API as `ai_pos_app`. |

Also confirm `devices` from the `0071` set still hides another tenant after `20261122_0124` adds `device_public_key_thumbprint`. A new column does not need a new policy. The test is there so the column is not an excuse to drop the policy.

### Out of scope

Do not point this suite at a database that already contains acceptance orders or stock grants. Do not read `LD-7B77A286`, `LD-9584F748`, `LD-9584A286`, or `LD-4F3A07CA`.

## Native Windows

### Identities

| Build | Identifier | Config | Data directory | API |
| --- | --- | --- | --- | --- |
| Pharmacy acceptance | `com.axizpos.pharmacy.acceptance` | `tauri.acceptance.conf.json` | `%APPDATA%\com.axizpos.pharmacy.acceptance` | `http://127.0.0.1:18080` |
| Inventory acceptance | `com.axizpos.inventory.acceptance` | `tauri.inventory-acceptance.conf.json` | `%APPDATA%\com.axizpos.inventory.acceptance` | `http://127.0.0.1:18081` |
| Laundry acceptance | `com.axizpos.laundry.acceptance` | `tauri.laundry-acceptance.conf.json` | `%APPDATA%\com.axizpos.laundry.acceptance` | `http://127.0.0.1:18082` |

The installed register is `com.aipos.desktop` from `tauri.conf.json`. Do not start it, do not read its `terminal.bin`, and do not send input to its window.

`build.rs` bakes the API only when `POS_ENV=acceptance` and `ACCEPTANCE_TENANT_URL_TEMPLATE` matches the profile. A binary that does not report that identifier is the wrong process.

### Before any input

1. Start the disposable API for that profile. Confirm the listening port.
2. Start the acceptance executable by its full path.
3. Record the path, the PID, and the window handle.
4. Confirm the process image path is the acceptance exe and the window title belongs to that PID.
5. If more than one AxizPOS window exists, stop. Do not click.

Input goes to that HWND only. Do not use a global mouse or keyboard path that can land on another application. Do not terminate a process whose path was not recorded in this run.

### Walk

Repeat for the pharmacy and inventory identities after the allocation command exists. Laundry uses the Orders screen, not Checkout.

1. Unlock with the disposable staff PIN. Confirm the footer names the disposable tenant.
2. Confirm a product search shows the SQLite allocation remainder, not the branch on-hand, once item 2 of the backlog is implemented. Until then this step is **BLOCKED** and the report says so.
3. Queue one cash sale inside the allocation. Close the process by its PID. Start the same exe. The queued sale and the reduced remainder are still there. No HTTP call is required for that reload.
4. Disconnect the API. Unlock from the local cache. The permanent entitlement still allows the non-pharmacy sale. Pharmacy medicine charge stays blocked.
5. Move the window, minimize it, and restore it. The client area stays drawn. If it goes white, record **FAILED** against the defect in `docs/laundry/LAUNDRY-PHASE-3.2-NATIVE-POS-UX-ACCEPTANCE.md`. Reload may restore the default view. That is not a pass.
6. Open Staff & Access only after the screen has real actions. Create is **BLOCKED** until the commands exist.

### Evidence

The report lists the exe path, PID, window handle, data directory, and API port. A screenshot of the browser preview is not native evidence. A white window is a failed step, not a skipped step.

### Current result

The O8 plan above was NOT RUN at the time it was written. O8.4 later launched `com.axizpos.offline.acceptance` and recorded the result in `O8.4-NATIVE-AND-FINAL-ACCEPTANCE-REPORT.md`. The white surface was not reproduced on that activation window. A later pass activated that register and is recorded in `O8.4-ACTIVATED-NATIVE-ACCEPTANCE-REPORT.md`. Checkout, an offline allocation sale, and an overdraw block are recorded in `O8.4-ACTIVATION-TO-CHECKOUT-ACCEPTANCE-REPORT.md`. The installed register was not used.
