# O7 staff architecture audit

This is the staff, permission, and credential baseline O7 builds on. It does not change those systems.

## Roles

System role names stay as they are. The register treats them as follows.

| Role name in the database | Who that is on the register |
| --- | --- |
| Store Manager | Store Admin. Role id `00000000-0000-4000-8000-0000000000a2`. |
| Super Admin | Tenant Super Admin. Role id `00000000-0000-4000-8000-0000000000a1`. |
| Cashier | Register operator. Role id `00000000-0000-4000-8000-0000000000a3`. |

There is no tenant role named Platform Super Admin. The register refuses that name. A register also refuses to create or grant Super Admin.

Permission identifiers used by this phase:

- `users:create` — open staff administration and submit provisioning.
- `users:update` — included in the local Store Manager ceiling.
- `pos:access` — required to unlock a register.
- `inventory:adjust_stock` — included in the local Store Manager ceiling. It does not change stock allocations.

The lists live in `apps/api/app/core/permissions.py` (`SYSTEM_ROLES`). Grant checks live in `apps/api/app/services/rbac_service.py` (`_assert_can_grant`, `_assert_store_scope`). Creating a user online still goes through `create_user` in that file. O7 does not replace that path.

## Server user record

`apps/api/app/models/user.py`, table `users`.

Fields that matter here: `username`, `email`, `full_name`, `hashed_password`, `hashed_pin` (`String(255)`), `is_active`, `store_id`, `role_id`, `has_pos_access`, `has_portal_access`, `failed_login_attempts`, `locked_until`, `token_version`.

Usernames and emails are unique per tenant. Staff are not hard-deleted by the offline flow. Disablement sets `is_active` false and increments `token_version`.

Existing routes in `apps/api/app/routers/v1/users.py`:

- `POST /api/v1/users` requires `users:create` and calls `rbac_service.create_user`. The body carries a plaintext PIN, which the server hashes with scrypt.
- `PATCH /api/v1/users/{id}` requires `users:update`.
- `POST /api/v1/users/{id}/pin` resets a PIN through the same scrypt path.
- `GET /api/v1/users/register-staff` returns display names for "Served by". It does not return PIN material.
- `DELETE /api/v1/users/{id}` remains the existing online delete. The offline flow does not call it.

## Credentials

Two verifiers already existed, and they are not interchangeable.

- The register (`apps/desktop/src-tauri/src/auth.rs`, `hash_pin` / `verify_pin`) uses the `argon2` 0.5 crate, `Argon2::default()`, and a fresh `SaltString` from `OsRng`. The stored value is the PHC string. Offline unlock compares the PIN to that string.
- The API (`apps/api/app/core/security.py`, `hash_pin` / `verify_pin`) peppers the PIN with HMAC-SHA256 and stores `scrypt$salt$digest`. `apps/api/requirements.txt` does not include an Argon2 package. Server `verify_pin` does not accept a `$argon2` string.

A PIN on the register is four digits (`apps/api/app/schemas/auth.py`). Offline lockout is five failures (`LOCAL_MAX_ATTEMPTS` in `auth.rs`). `finish_offline` still requires `pos:access` and still returns no access token. A local unlock is not a signed user token. Protected online APIs still require one. Login with a PIN still requires `X-Api-Key` or `X-Terminal-Token`.

## How a terminal already received staff

O3 product bootstrap does not download staff PIN hashes. A cashier who unlocked online is cached in SQLite `cached_users` (`apps/desktop/src-tauri/src/db.rs`). That cache is what `finish_offline` reads. Before O7 the cache had no provisioning status. Server-synced rows now default to `provisioning_status = 'server'` and `is_active = 1`, so an existing cached cashier still unlocks.

## Entitlement

`apps/api/app/console/plan_limits.py` `limit_value("staff")` reads the tenant plan. `None` means the plan is not capping staff (including when tenancy is off, which is the in-memory test database). `assert_room` returns 409 `plan_limit` when the number of active users has reached the cap. `create_user` counts `User.is_active == True`. Disabled users do not consume a seat on the server. O7 does not invent a cap.

## What O7 added beside this baseline

A separate outbox, not a change to `sync_queue`:

- SQLite `staff_provisioning` and `staff_audit` in `db.rs`.
- PostgreSQL `staff_provisioning_events` in `apps/api/app/models/staff_provisioning.py`. Alembic `20261122_0128` creates that table. It was not applied to a protected database. Tests create it with `create_all` on `sqlite://`.

`cached_users` gained `provisioning_status` and `is_active`. The `sync_queue` column list was not changed.
