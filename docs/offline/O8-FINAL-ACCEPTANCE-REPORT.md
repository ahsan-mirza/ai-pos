# O8 final acceptance report

O8.2 is **IN PROGRESS**. The O8 result below is unchanged.

Status: **PASSED WITH LIMITATIONS**.

The offline platform is not fully accepted. Native Windows, PostgreSQL RLS, and a production entitlement public key are still open. No production deployment occurred. No protected database was opened or migrated.

## What this run changed

- Offline product selection stamps `allocation_remaining` from `terminal_allocation_balances`. That command returns only manifests that still verify for this device. The product card shows branch on-hand and the register remainder. The cart blocks when the remainder is missing or too small, including a serialized line that carries the field. Online selling does not attach the field.
- Staff & Access creates, edits, resets a PIN, and disables through the register session. The seat cap comes from the signed entitlement `limits.staff`. An unverified document blocks creation. Pending staff stay on the originating database until `import_accepted`.
- Local provisioning rows store tenant id, originating terminal id, and schema version. Server events store `origin_terminal_id`, `schema_version`, and `base_version`.
- Online `login-pin` verifies an Argon2 verifier. User list responses do not include it.
- A local transport failure can be marked `retryable` on the same event. `awaiting_review` was not added.

`sync_queue` columns were not changed. Allocation issuing and `move_stock` were not redesigned. Pharmacy medicine checkout stays blocked. Card, QR, and pay-later still need a verified provider PAID. Lost-terminal write-off and financial conflict adjustment stay awaiting approval.

## Commands and counts

`node scripts/python.mjs -m pytest tests/test_staff_provision.py tests/test_allocations.py tests/test_sync.py tests/test_permanent_entitlement.py -q --tb=line`

28 passed in 28.21s. That includes the new Argon2 login test.

`cargo test --lib -- --test-threads=8` from `apps/desktop/src-tauri`

51 passed. That includes the allocation remainder after restart, the tampered-manifest omission, the staff lockout, and the release-key exclusion.

`pnpm exec vitest run src/features/checkout/allocation.test.ts src/features/checkout/checkout.pharmacy.test.ts src/features/settings/staffAccess.test.ts` from `apps/desktop`

7 passed. Pharmacy offline medicine checkout still fails closed.

These counts are this O8 run. Earlier phase reports keep their own counts.

## Files

- `apps/desktop/src-tauri/src/allocation.rs`
- `apps/desktop/src-tauri/src/staff.rs`
- `apps/desktop/src-tauri/src/auth.rs`
- `apps/desktop/src-tauri/src/db.rs`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src-tauri/src/entitlement.rs`
- `apps/desktop/src/features/checkout/allocationBalance.ts`
- `apps/desktop/src/features/checkout/allocation.test.ts`
- `apps/desktop/src/features/checkout/cart.ts`
- `apps/desktop/src/features/checkout/CheckoutPage.tsx`
- `apps/desktop/src/features/checkout/ProductCard.tsx`
- `apps/desktop/src/features/settings/staffAccess.ts`
- `apps/desktop/src/features/settings/staffAccess.test.ts`
- `apps/desktop/src/features/settings/StaffAccessPanel.tsx`
- `apps/desktop/src/features/settings/SettingsPage.tsx`
- `apps/desktop/src/lib/tauri.ts`
- `apps/api/app/core/security.py`
- `apps/api/app/services/staff_provision_service.py`
- `apps/api/app/models/staff_provisioning.py`
- `apps/api/app/routers/v1/users.py`
- `apps/api/requirements.txt`
- `apps/api/alembic/versions/20261122_0129_staff_provisioning_metadata.py`
- `apps/api/tests/test_staff_provision.py`

Alembic `20261122_0129` was not applied outside the in-memory test database.

## Acceptance that is still open

| Item | Status |
| --- | --- |
| Native Tauri window, including WebView occlusion | NOT RUN |
| PostgreSQL RLS with `ai_pos_app` | NOT RUN |
| Production entitlement public key | AWAITING APPROVAL |
| Lost-terminal stock write-off | AWAITING APPROVAL |
| Financial or stock conflict adjustment | AWAITING APPROVAL |
| Separate performance study | NOT RUN |
| Each business profile on a register window | NOT_TESTED in the capability matrix |
| `awaiting_review` provisioning queue | Not implemented. Domain refusals stay `rejected`. |

## What is safe to say

One register can verify a permanent entitlement in tests, sell only inside a verified local allocation, keep that sale and the queue row together, and create a cashier who unlocks that register before the server accepts them. Another register does not receive that cashier until acceptance and import. Pharmacy medicine sales stay offline-blocked. None of that was demonstrated on a native window or under PostgreSQL row-level security.

## O8.2 closure

Status: **IN PROGRESS**. The platform is not fully accepted. Nothing was deployed.

O8.2 commands, separate from the O8 counts above:

`node scripts/python.mjs -m pytest tests/test_staff_provision.py tests/test_allocations.py tests/test_sync.py tests/test_permanent_entitlement.py -q --tb=line`

28 passed in 27.37s. In-memory SQLite. This is not the O8 28.21s run.

`cargo test --lib -- --test-threads=8` from `apps/desktop/src-tauri`

53 passed in 11.21s. That includes `a_rotation_list_keeps_named_public_keys_and_drops_a_bad_entry` and `the_test_signing_key_is_not_a_release_key`. The O8 count of 51 does not include this run.

`pnpm exec vitest run src/features/checkout/allocation.test.ts src/features/checkout/checkout.pharmacy.test.ts src/features/settings/staffAccess.test.ts` from `apps/desktop`

7 passed. Pharmacy medicine checkout still fails closed.

PostgreSQL: `apps/api/scripts/o82_rls_disposable.py` reported 15 passed, 0 failed, against `axizpos_o82` on `127.0.0.1:55941` only. The login was `ai_pos_app`, with `LOGIN`, `NOSUPERUSER`, and `NOBYPASSRLS`. Follow-up queries are in `O8-POSTGRESQL-RLS-FINAL-ACCEPTANCE.md`. Alembic `20261122_0130` was applied only there, then the cluster was stopped and its temp data directory was deleted. No protected database was opened or migrated.

| O8.2 item | Status |
| --- | --- |
| Native Windows, scenarios A–D, WebView occlusion | NOT RUN. The blank surface was not cleared |
| PostgreSQL RLS as `ai_pos_app` | PASSED WITH LIMITATIONS. Tenant isolation holds. A set `app.store_id` hides the other allocation. The application sets only `app.tenant_id`, so a normal request does not. Older `users`, `products`, and `sync_events` policies still open when `app.bypass_rls` is on |
| Production public key | AWAITING APPROVAL |
| Business profiles | No profile fully accepted. Native UI NOT_TESTED |
| Two-terminal allocation | PASSED WITH LIMITATIONS. API and library. Product card was not clicked |
| Staff & Access screen | PASSED WITH LIMITATIONS. API and library. The panel was not clicked |
| Lost-terminal write-off | AWAITING APPROVAL |
| Financial conflict adjustment | AWAITING APPROVAL |

O8.2 files:

- `apps/api/alembic/versions/20261122_0130_offline_rls.py`
- `apps/api/scripts/o82_rls_disposable.py`
- `apps/api/scripts/o82_rls_extra.py`
- `apps/api/scripts/o82_rls_closed.py`
- `apps/desktop/src-tauri/src/entitlement.rs`
- `apps/desktop/src-tauri/src/db.rs` (removed a duplicated `cached_user_by_id`)
- `docs/offline/O8-NATIVE-WINDOWS-FINAL-ACCEPTANCE.md`
- `docs/offline/O8-POSTGRESQL-RLS-FINAL-ACCEPTANCE.md`
- `docs/offline/O8-PRODUCTION-KEY-READINESS.md`
- `docs/offline/O8-BUSINESS-PROFILE-CAPABILITY-MATRIX.md`
- `docs/offline/O8-TWO-TERMINAL-ALLOCATION-ACCEPTANCE.md`
- `docs/offline/O8-STAFF-ACCESS-FINAL-ACCEPTANCE.md`
- `docs/offline/O8-OUTSTANDING-BUSINESS-APPROVALS.md`

The duplicate method removal is a compile fix. Allocation issuing, `sync_queue`, pharmacy blocking, and provider PAID rules were not weakened. No production key was created. No write-off or conflict adjustment was implemented.
