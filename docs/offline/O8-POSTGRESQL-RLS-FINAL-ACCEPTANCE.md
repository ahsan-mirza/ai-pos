# O8.2 PostgreSQL RLS acceptance

Status: **PASSED WITH LIMITATIONS**.

The session that ran the checks logged in as `ai_pos_app`. `SET ROLE` was not used. `pg_roles` reported `rolcanlogin` true, `rolsuper` false, and `rolbypassrls` false. `current_user` and `session_user` were `ai_pos_app`.

## Target

A new PostgreSQL 18 cluster was created under the temp directory `axiz-o82-pg`. It listened only on `127.0.0.1:55941`. The database name was `axizpos_o82`. The cluster superuser `o82boot` ran Alembic. It was not used as the isolation proof.

`APP_ENV=acceptance`. No acceptance env file exists, so the developer, test, inventory, and laundry env files were not loaded. `CONTROL_DATABASE_URL` was empty. Alembic received the disposable URL through `Config.attributes["database_url"]`.

Alembic upgraded that database to `20261122_0130`. The log includes `20261122_0129 -> 20261122_0130`. That revision enables and forces row-level security on:

- `bootstrap_sessions`
- `bootstrap_snapshot_items`
- `bootstrap_setting_snapshots`
- `catalog_feed_counters`
- `catalog_changes`
- `terminal_allocations`
- `terminal_allocation_consumptions`
- `staff_provisioning_events`

The policy matches `app.tenant_id`. The bypass function returns true only when `app.bypass_rls` is `on` and `session_user` is the table owner.

Confirmed from `pg_class` on this database: `users`, `products`, `sync_events`, `bootstrap_sessions`, `catalog_changes`, `terminal_allocations`, and `staff_provisioning_events` have row security enabled and forced.

The cluster was stopped and the temp data directory was deleted after the queries. No other database was migrated.

The executed policy on `terminal_allocations` and `bootstrap_sessions` matches tenant, and also store and device when `app.store_id` or `app.device_id` is set. An empty setting does not filter. `catalog_changes` and `staff_provisioning_events` are tenant-only. `users`, `products`, and `sync_events` still use the older any-role bypass.

`app/core/database.py` sets `app.tenant_id` only. A normal request does not set the store or device settings, so those clauses stay open on the request path.

## Direct SQL as `ai_pos_app`

| Case | Result |
| --- | --- |
| Tenant A reads its own staff events and sync events | 1 and 1 |
| Tenant A reads Tenant B staff events | 0 |
| Tenant A inserts a Tenant B staff event | rejected |
| Tenant A updates Tenant B staff events | 0 rows |
| Tenant A deletes Tenant B staff events | 0 rows |
| Tenant A users visible, Tenant B users visible | 1 and 0 |
| Tenant B sync events visible to Tenant A | 0 |
| Empty `app.tenant_id` | 0 staff, 0 users, 0 sync events |
| Unknown tenant id, bypass off | 0 users, 0 sync events, 0 allocations, 0 staff events |
| Next transaction after a committed tenant setting | 0 staff events |
| `app.bypass_rls=on` on staff events, as `ai_pos_app` | still 1. The app role is not the owner |
| `app.bypass_rls=on` on users, as `ai_pos_app` | 2. Both tenants became visible |
| Store and device settings empty | both allocations visible, count 2 |
| `app.store_id` set to one branch | the other allocation hidden, count 1 |
| Unknown `app.store_id` | 0 allocations |

## Limitations

With store and device settings empty, Tenant A still sees both allocations. That is the request-path behaviour, because the application sets only `app.tenant_id`. The store clause was proved by setting `app.store_id` in this SQL session. The device clause is in the same policy and was not given a separate count.

`users`, `products`, and `sync_events` still let any role read every tenant when `app.bypass_rls` is `on`. With that flag on, the users count became 2. Those policies were not rewritten. With the flag off, an unknown tenant and an empty tenant returned 0.

`accepted_staff()` does not add a branch filter. Staff-feed branch scope was not given its own API test on this database. Product catalogue changes are tenant-only. Conflict rows are not a separate table. `sync_events` are tenant scoped.

The FastAPI request path was not pointed at this PostgreSQL. Those API tests used in-memory SQLite. Direct SQL is the evidence above.

## Commands

`apps/api/scripts/o82_rls_disposable.py` — 15 passed, 0 failed. This is the run against the current revision text.

`apps/api/scripts/o82_rls_extra.py` — role flags, policies, and the users bypass result.

`apps/api/scripts/o82_rls_closed.py` — unknown tenant and empty tenant with bypass off.
