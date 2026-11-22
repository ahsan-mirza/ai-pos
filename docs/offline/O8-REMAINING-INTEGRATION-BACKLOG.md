# O8 remaining integration backlog

O8.11 is **IN PROGRESS**. The checkout sync flush now commits the signed menu and floor snapshot. Downtown Till A (`com.axizpos.restaurant.acceptance`, executable SHA-256 `A3EFA32F6C63D62EA6D6EDD76984B5D63FF7B0CD40674E96256C1AC413D4C851`) stored 3 menu rows and Downtown Room plus table 5, and the setup-incomplete chip cleared. Takeaway #3E55 stayed quantity 11 and settled once as cash invoice `O810-DTA-000001` on the disposable SQLite API. Dine-in, delivery, a second till, PostgreSQL, Electronics, Fashion, Laundry, occlusion, a scanner, and full regression remain open. See `docs/offline/O8.11-RESTAURANT-BOOTSTRAP-AND-NATIVE-CHECKOUT.md`.

O8.10 is **IN PROGRESS**. Downtown Till A was activated in `com.axizpos.restaurant.acceptance` against `http://127.0.0.1:18089` and SQLite `%TEMP%\axiz-o810\axizpos_o810.sqlite`. The business-wide owner set the Restaurant preset. The window showed O810 Grill at USD 18.00 and opened takeaway Order #3E55 with 11 of that item at USD 207.90. The ticket was not charged. Electronics, Fashion, Laundry, occlusion, a physical scanner, full regression, and PostgreSQL reconciliation of that ticket remain open. See `docs/offline/O8.10-RESTAURANT-NATIVE-ACCEPTANCE.md`.

O8.9 is **IN PROGRESS**. A business-wide owner enabled the Restaurant preset on disposable `axizpos_o89` (`127.0.0.1:55971`, `ai_pos_app`). That run was 20 passed, 0 failed, then the cluster was deleted. `pytest tests/test_order_authorization.py` was 1 passed in 3.19s. Those two counts stay separate. Native Restaurant, Electronics, Fashion, and Laundry walks, Chromium occlusion, a physical scanner, full regression, and SQLite/PostgreSQL reconciliation remain open. See `docs/offline/O8.9-ORDERS-AUTHORIZATION-REPORT.md`.

O8.8 is **PASSED WITH LIMITATIONS**. `GET /api/v1/orders` returned 403 `capability_disabled` because Open orders & tabs was off. A store-bound admin cannot turn that module on. `pytest tests/test_order_authorization.py` was 1 passed in 2.83s. Restaurant, Electronics, Fashion, and Laundry native walks remain open. See `docs/offline/O8.8-POSTGRES-ORDER-AUTHORIZATION-ACCEPTANCE.md`.

O8.7 is **PASSED WITH LIMITATIONS**. The acceptance executable was rebuilt and cashier `o85till2` was created in that window and accepted on the disposable grocery API as the same UUID. Register provisioning accepts a pos token. Disposable Postgres `axizpos_o87` on `127.0.0.1:55970` was 9 passed and 1 failed, then deleted. Restaurant, Electronics, Fashion, and Laundry were not walked. See `docs/offline/O8.7-STAFF-NATIVE-ACCEPTANCE.md`.

O8.6 menu and floor changes use the catalogue feed, and a second dine-in on a busy table is kept for manager review. `cargo test --lib` was 55 passed, 0 failed, 9.87s, exit 0. `pytest tests/test_restaurant_sync.py tests/test_orders.py tests/test_bootstrap.py tests/test_approvals_manager.py` was 22 passed, 0 failed, 34.01s, exit 0. The 30-day sale rule was not changed. Production key and both postings stay **AWAITING APPROVAL**.

O8.5 native checkout is **PASSED WITH LIMITATIONS** in `docs/offline/O8.5-NATIVE-END-TO-END-ACCEPTANCE-REPORT.md`. Grocery cash, offline allocation, overdraw, and sync ran on the isolated pharmacy acceptance window. Staff create failed without a stored row. Barcode hardware, Chromium occlusion, and the other four profile walks stay open. The restaurant inventory is `docs/offline/O8.5-RESTAURANT-FEATURE-INVENTORY.md`. The menu and floor feed and the table-review row are in the O8.6 source. A native restaurant walk and a second Postgres tenant are still open. The 30-day sale rule stays. `test_approvals_manager.py` now uses a sale date inside that window and asserts a 31-day sale is refused. Production key and both postings stay **AWAITING APPROVAL**.

O8.4 closed the application-role bypass on `users`, `products`, and `sync_events`, and a missing `app.store_id` now hides store-scoped allocations. Request queues exist for a lost terminal and a sync conflict. Posting those decisions stays **AWAITING APPROVAL**. `com.axizpos.offline.acceptance` completed a grocery cash sale, an offline allocation sale, and an overdraw block against disposable `axizpos_o84act`. Staff & Access, barcode hardware, and the other four profile walks are still open. Do not apply `20261122_0131` to a protected database.

## 1. Critical security defects

| Item | Status | Work |
| --- | --- | --- |
| Release trust variable is the wrong name | Build contract implemented. Production key **AWAITING APPROVAL** | `build.rs` publishes the singular pair and `POS_ENTITLEMENT_PUBLIC_KEYS`. `production_trusted_keys` reads both. A production release with none of them set fails the build. No key was generated. |
| New tables have no RLS | PASSED WITH LIMITATIONS on disposable Postgres | `20261122_0131` removes the session bypass flag. It was applied only to `axizpos_o83` on `127.0.0.1:55942` as `ai_pos_app`, including FastAPI. The cluster was then deleted. |
| Staff feed returns a verifier | Implemented, device-scoped | `accepted_staff` includes `pin_verifier` for `require_device` only. `UserOut` does not. Do not add the hash to a user route. |
| Online PIN cannot check an Argon2 verifier | PASSED in `tests/test_security.py` | `verify_pin` accepts scrypt and `$argon2id$`. Other `$` prefixes fail closed. |

`o2-test-1` is compiled only under `cfg(test)`. Leave that gate in place.

## 2. Critical inventory and allocation integration

Status: **PASSED WITH LIMITATIONS**. Offline `enqueue_events` calls `allocation::commit_queued`. An online sale sends no allocation payload and can spend only unreserved branch stock. `test_online_sale_spends_unreserved_stock_and_leaves_both_grants` covers terminals A and B, a duplicate, and an idempotency conflict. Native checkout was not repeated.

O8.2 should:

1. Expose `allocation::install`, a remaining-quantity read, and `allocation::sell` as commands. `sell` stays inside `Db::consume_allocation` so the balance and the `sync_queue` row commit together.
2. Attach the SQLite remainder in `Db::search_products` and in the barcode path that uses it, including `VariantPicker`.
3. Put `allocation_id`, `sequence`, and `quantity` on the sale payload in `queue.ts` so `sale_service` reaches `consume_for_sale`.
4. Keep services, recipes, open-price lines, and untracked items on the existing `stockError` exemptions.
5. Keep `inventory_levels` and `stock_movements` as the ledger. Do not auto-expire a reservation.
6. Leave `transition_serial(..., allow_reserved=True)` as a recorded exception until a separate decision. Do not widen it.

Tests that are missing: a command-level test that a sale without a local grant does not enqueue; a test that search, barcode, and variant selection return the same remainder; a test that the queued payload's sequence is the sequence `consume_allocation` stored.

## 3. Staff provisioning and authentication

Status: **library and API implemented, UI and command path not implemented**. Online verification of a provisioned verifier is **partially implemented**.

O8.2 should:

1. Extend `security.verify_pin` so an `$argon2id$` verifier verifies with Argon2 and a `scrypt$` verifier still uses the pepper. Keep `POST /api/v1/auth/login-pin` and `POST /api/v1/auth/unlock`. Do not add a login route.
2. Teach `unlock_by_id` that a pending local cashier on this register can unlock locally when the server has no such user yet. A 403 for a disabled account stays a refusal. Do not treat every 401 as "try the local PIN" for an arbitrary username.
3. Add commands that call `create_local`, `disable_local`, `mark_provisioning`, and `import_accepted`. Add the missing local edit and PIN-reset operations only as new outbox events that carry an Argon2 verifier, or leave them out of the screen until those functions exist. Do not point the screen at `POST /users/{id}/pin`, which sends a plaintext PIN and stores scrypt.
4. Push `staff_provisioning` with `POST /api/v1/users/provision`. On `accepted` or `duplicate`, call `mark_provisioning`. On `provisioning_conflict` or `rejected`, record the rejection. A transport error leaves the row `pending`. A rejected `event_id` is not reusable. Retry uses a new id.
5. Pull `GET /api/v1/users/staff-feed` with the device credential and pass each accepted verifier to `import_accepted`.
6. Replace the paragraph in `SettingsPage.tsx` with the list, status from `staffStatus`, seat label, and the actions the commands support. Keep `canManageStaff`. Do not offer Platform Super Admin.

Missing tests: UI submit of create and disable; command unlock of a pending cashier while the API returns 401 for an unknown user; `login-pin` success against an accepted Argon2 verifier; feed import on a second database file through the command, not a direct function call.

## 4. Release-key configuration

Status: **AWAITING APPROVAL** for the key material, **BLOCKED** for a production release that must verify entitlements.

Dependencies: an authorized public key and key id from outside this repo. The private key stays off the register. After they exist, the release build passes `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`. Confirm `production_trusted_keys` returns that one key and still excludes `o2-test-1`. Allocation manifests use the same list, so this blocks grant install on a release build as well.

## 5. PostgreSQL RLS acceptance

Status: **NOT RUN**. Policies for the O3–O7 tables are **not implemented**.

Do this before any apply of `0125`–`0128` to a database that holds more than one tenant. The procedure is `O8-NATIVE-AND-RLS-TEST-PLAN.md`. Use a new disposable cluster and login `ai_pos_app` with `NOSUPERUSER NOBYPASSRLS`. Do not open a protected database. Do not use SQLite as the result.

## 6. Native Windows acceptance

Status: **NOT RUN**.

Use a dedicated acceptance identity, data directory, and API. Verify the executable path, PID, and window before any input. Do not touch `com.aipos.desktop`. The procedure is in the native test plan. The white WebView after a move or a click is still an open defect. A browser preview is not evidence.

## 7. Business-profile integration tests

Status: **NOT STARTED** as an offline matrix. The profile ids exist. The per-profile cases are in `O8-BUSINESS-PROFILE-TEST-PLAN.md`.

Pharmacy offline medicine sale stays blocked. Laundry keeps Orders and does not mount retail Checkout. Laundry's separate UI report is not evidence for this item.

Run these after items 2 and 3, because allocation and staff are part of every profile's row.

## 8. Performance and reliability

Status: **NOT RUN**, and it waits on items 2, 5, and 6.

- Catalogue pull at a production-sized count. O3 timed 102 products.
- Two overlapping HTTP requests for one idempotency key. O5 tested the sequential path only.
- A socket that closes after the server commits. The register must leave the batch `pending` and the retry must be `duplicate`.
- SQLite busy and a failed commit. O4 covered rollback in library transactions and did not inject a disk fault.
- No backoff jitter was added in O5. Add it only if a measured retry storm shows up. Do not change the conflict rule.

## Explicitly out of this backlog

- Destroying a lost terminal's reserved units. **AWAITING APPROVAL**. Quarantine keeps the hold.
- Rewriting money or stock after an O5 `conflict`. **AWAITING APPROVAL**.
- A new draft, catalogue, or authentication system.
- Production deployment.
