# Offline architecture audit

Status: mapped from the current register and API. This is an audit, not an implementation of permanent activation, per-terminal allocation, or local staff administration.

No database was migrated. No production, developer, or inventory-acceptance database was opened.

## Windows POS

The register is Tauri 2 with a Rust backend and a React frontend.

Local persistence is one SQLite file per tenant under the application data directory. `apps/desktop/src-tauri/src/db.rs` creates:

- `products` — catalogue cache, including price, tax category, weight, packs, and stock quantity.
- `sync_queue` — the existing offline sales queue. Columns include `idempotency_key`, `entity_type`, `operation`, `payload`, `status`, `attempts`, and `last_error`.
- `cached_users` — cashier directory for offline PIN unlock. `pin_hash` is Argon2, written by `auth.rs`. Failed attempts and `locked_until` are stored.
- `cashier_directory`, `register_session`, `user_preferences`.

Activation is the existing one-time store code and activation key. The Rust process stores the device credential with Windows CryptProtectData and refuses a developer data directory on an acceptance build. There is no signed permanent offline entitlement, no public verification key in the app, and no entitlement version. A disconnected terminal cannot be told about a remote suspension because nothing in the current activation record carries a revocation cursor.

The bearer token for an online unlock stays in a Rust mutex. Offline unlock clears that token and records an offline login. The browser preview keeps the cashier profile in `localStorage` and the token in memory only. PINs are not written to `localStorage`.

Network state is inferred from request failure (`status` 0, code `offline`) and from the update check. A reachable API is not treated as a signed-in cashier. The status bar says so.

The retail command whitelist in `retail.rs` is the only path from the native window to the API. `/api/v1/laundry` is on that list. A path outside the list is refused before it leaves the register.

Printers and scanners are local device features of the existing register. This audit did not retest them.

Restart recovery restores the encrypted activation and the SQLite file. The React view is memory only, so a reload returns to Checkout.

## Backend

FastAPI, PostgreSQL, tenant middleware, and RLS remain the server. The disposable laundry proof uses `ai_pos_app` as `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`. That was not re-run for this audit.

`POST /api/v1/sync/push` accepts up to the configured batch size. Results today are only `applied` and `duplicate`. A rejected event rolls back the whole batch as HTTP 422. There is no per-event `CONFLICT`, `UNAUTHORIZED`, `RETRYABLE_FAILURE`, or `SCHEMA_INCOMPATIBLE`, and no server change cursor for incremental pull.

Known sync entity types are store, product, serial number, sale, repair ticket, sale return, customer, open order, and laundry order. A laundry stage event is not one of them. The register already refuses to enqueue `laundry_stage`.

Inventory stock is the server ledger. The register caches `stock_quantity` on the product row. There is no terminal allocation table. Two offline registers can each sell the cached quantity.

## What already works offline

- PIN unlock against the Argon2 cache, with lockout fields on `cached_users`.
- Product lookup from the SQLite catalogue.
- Sale and return enqueue into `sync_queue`, with idempotency keys.
- Push of a completed sale or return when the API returns.
- Duplicate idempotency keys are recognized by the server as `duplicate`.
- Pharmacy medicine sales are blocked offline in `checkout.ts` (`blockPharmacyOfflineSale`). The register does not try to infer a medicine from a lot snapshot.
- A non-express, zero-deposit laundry intake can be queued locally when the server is unreachable. Express and deposits stay offline-unsafe. Production, batch, and machine changes stay disabled offline.

## What is only partial

- Catalogue refresh is a snapshot, not a cursor. Reconnection can re-read products; it does not apply a bounded change feed.
- Sync status is pending, attempts, and last error. It does not match the required outbox states.
- Permission snapshots travel with the cached cashier. A Store Admin cannot create a new cashier on the register. New accounts exist only after a server user is created and the register is unlocked online.
- Customer, price-list, tax, and promotion data are whatever the last catalogue payload contained. There is no separate Offline Ready gate.
- Restaurant open orders have a sync entity. Kitchen-ticket duplicate protection was not retested here.
- Laundry orders sync as `laundry_order`. Garment stage, tag, photo, batch, and machine changes do not.

## Online-only

- Terminal activation and device-token rotation.
- Staff creation, role assignment, and seat limits.
- Stock allocation, reservation, and ledger posting.
- Payments that need a live processor.
- Pharmacy lot release and medicine sales.
- Laundry production mutations.
- Remote revocation. The register has no way to learn it until a request is rejected.

## Concurrency

The product cache is a shared number. Nothing stops two disconnected terminals from selling the same unit. That is the gap Decision 2 closes. The existing queue can carry consumption events; it should be extended, not replaced. Replacing it is not justified: sales already survive restart and replay by idempotency key.

## Profile restrictions to keep

| Profile | Keep |
| --- | --- |
| Grocery | Weight and PLU stay on the product cache. Allocated weight must use the configured precision. |
| Fashion | Variants and returns stay against cached sales. |
| Electronics and wholesale | Serial or IMEI sale only when that serial is on the terminal. Credit only inside an approved offline limit. |
| Restaurant, cafe, quick service | Menu, modifiers, and tickets. Do not double-send a kitchen ticket. |
| Laundry | Garments in process are not saleable stock. Production mutations stay online. |
| Pharmacy | Medicine sales stay blocked offline. A local lot row must not enable them. |

## Proposed increments

1. Keep `sync_queue` and add the missing statuses and a dependency order. Do not add a second queue.
2. Add a signed entitlement as a new server response on the existing activation call. The private key stays on the server. The register stores only the public key and the signed document in Windows-protected storage. No expiry field.
3. Add terminal allocation as server rows on the existing ledger, then a local allocation table the sale transaction decrements in the same SQLite transaction as the outbox row.
4. Add local staff provisioning as outbox events. The new cashier is usable only on the terminal that created the account until the server accepts it.
5. Do this on disposable databases. Do not migrate the developer, inventory-acceptance, or production databases.

## Not done in this audit

Permanent activation, bootstrap, the local-first transaction engine, incremental pull, stock allocation, offline staff administration, and native acceptance of those flows are not implemented. Business Pro `/laundry/production` was not opened.
