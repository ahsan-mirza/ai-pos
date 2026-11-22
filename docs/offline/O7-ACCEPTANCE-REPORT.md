# O7 acceptance report

Status: **PASSED WITH LIMITATIONS**.

A cashier created on one register is stored there as pending, can unlock that register, and is not on another register until the server accepts the event and that register imports the Argon2 verifier. No production deployment. No developer, inventory-acceptance, laundry, or production database was opened. Alembic `20261122_0128` was not applied to those databases. O8 was not started.

## What was executed

- A Store Manager on the server cannot assign another branch (`store_scope`) and cannot provision a Store Manager (`role_not_allowed`). Super Admin and Platform Super Admin are refused. A cashier token cannot call `POST /api/v1/users/provision`.
- The same event id and the same body return `duplicate` and do not create a second user. A changed body on that id returns 409 `provisioning_conflict` and leaves the original name in place.
- A plaintext PIN is refused (`invalid_verifier`). The stored value is the `$argon2id$` verifier. The fixture PIN digits are absent from the rejection text and from the staff feed body.
- With `limit_value("staff")` patched to the number of active users already present, creation returns 409 `plan_limit` and no user row is inserted. The patch is removed afterward. The production cap still comes from `limit_value`, which is `None` when tenancy is off.
- After acceptance, `GET /api/v1/users/staff-feed` with a device key returns that cashier. A bearer user token receives 401. A following disable leaves `is_active` false. A conflicting replay of the disable does not turn the account back on. The feed then reports `is_active: false`.
- On the register, a local cashier is `pending`, the PIN is not in `pin_hash` or the outbox payload, and the row is still pending after the SQLite file is reopened. A missing seat limit is refused. A second create at a full seat limit is refused. Super Admin cannot be granted locally.
- Five wrong PINs lock the local cashier. The correct PIN is refused with the existing lockout message.
- Disabling locally sets `is_active` to 0. Marking that disable event rejected leaves `is_active` at 0. Audit rows remain.
- A second SQLite file has no such user until `import_accepted`. The imported verifier checks with Argon2. A non-Argon2 string and a Platform Super Admin role are refused.
- The O2 entitlement, O5 sync, and O6 allocation tests in the same API command still passed. Pharmacy offline checkout tests still fail closed. The allocation cart test still passed.

## Commands and counts

`node scripts/python.mjs -m pytest tests/test_staff_provision.py tests/test_allocations.py tests/test_sync.py tests/test_permanent_entitlement.py -q --tb=line`

27 passed in 20.58s.

`cargo test --lib -- --test-threads=8` from `apps/desktop/src-tauri`

50 passed.

`pnpm exec vitest run src/features/settings/staffAccess.test.ts src/features/checkout/allocation.test.ts src/features/checkout/checkout.pharmacy.test.ts` from `apps/desktop`

6 passed. Two of those cover staff status labels, the cashier denial, and the seat text. One covers the allocation offline message. Three cover pharmacy offline checkout, which still fails closed.

These counts are this O7 run. The O6 report's 24, 46, and 4 are that phase's own results.

## Files

- `apps/api/app/models/staff_provisioning.py`
- `apps/api/app/models/__init__.py`
- `apps/api/app/services/staff_provision_service.py`
- `apps/api/app/routers/v1/users.py`
- `apps/api/alembic/versions/20261122_0128_staff_provisioning.py`
- `apps/api/tests/test_staff_provision.py`
- `apps/desktop/src-tauri/src/staff.rs`
- `apps/desktop/src-tauri/src/auth.rs`
- `apps/desktop/src-tauri/src/db.rs`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src/features/settings/staffAccess.ts`
- `apps/desktop/src/features/settings/staffAccess.test.ts`
- `apps/desktop/src/features/settings/SettingsPage.tsx`

`sync_queue` columns were not changed. `allocation_service.py`, `terminal_allocation.py`, and `allocation.rs` were not changed in this phase. Staff events are not written into the financial queue.

## Preserved behaviour

- Existing offline unlock still uses Argon2, five-attempt lockout, and `pos:access`. A local unlock still has no access token.
- Sale and return queue semantics from O5 were not redesigned. The O5 collision test passed in this run.
- O6 grants, signatures, and device binding were not modified. Lost-terminal stock write-off remains AWAITING APPROVAL. The product card still does not load the terminal allocation balance from SQLite.
- Pharmacy offline medicine checkout remains blocked.
- Card, QR, and pay-later still require a verified provider PAID. This phase did not touch payment code.
- No protected database was modified. No production register was driven. No production deployment occurred.

## Limitations

- Native Tauri window: **NOT RUN**. The Staff & Access section was not clicked in a register window. Browser status helpers are not native acceptance.
- PostgreSQL RLS with `ai_pos_app`: **NOT RUN**.
- The settings section is gated by role and `users:create`. Create, edit, PIN reset, and disable are implemented in the register library and the API. The screen does not yet submit those actions.
- The local outbox has no separate columns for tenant id, originating terminal id, schema version, or base server version. Those facts are either inside the payload or taken from the authenticated request.
- Server outcomes used here are `accepted`, `duplicate`, `rejected`, and `provisioning_conflict`. `retryable` and `awaiting_review` are not separate statuses. A transport failure leaves the local event `pending`.
- The API stores the Argon2 verifier and does not verify it with `verify_pin`. Another register checks the pulled verifier locally. An online PIN login of that verifier against the API is not available.
- The register blocks creation when the caller does not pass a seat limit. It does not read the signed entitlement document itself.
- Creating another tenant Super Admin remains on the existing online user API. The register provision path does not offer it.
- Remote staff changes still reach a disconnected register only after that register pulls.
- Production builds still need `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`. The test signing key is not a production key.
- O5 financial adjustment of a conflict remains AWAITING APPROVAL.
- O8 full business-profile acceptance: **NOT STARTED**.
