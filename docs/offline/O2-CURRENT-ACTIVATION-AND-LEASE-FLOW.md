# O2.1 — Current activation and lease flow

Traced from the O1 code. The selling callers listed below are the lease path. O2 leaves that path in place for a register with no permanent entitlement, and skips only the 24-hour lease when Rust has returned `VALID_PERMANENT_ENTITLEMENT`.

## Activation

1. The register sends `POST /api/v1/terminals/activate` with `X-Tenant-Domain`, `activation_key`, and `machine_name`. `apps/desktop/src-tauri/src/terminal.rs` `activate`.
2. The API throttles guesses, then `device_service.activate_terminal` hashes the key and loads `DeviceActivation`. Unknown, used, or expired keys return 401 `activation_invalid`. The key itself expires 24 hours after issue (`ACTIVATION_TTL`). That expiry is the one-time key, not an offline entitlement.
3. A match rotates the device token. `replace_device_token` / `_new_key` creates `aipos_` plus a random URL-safe secret. Only the SHA-256 digest is stored. The plaintext token is returned once.
4. The response fields stored by the register are tenant slug, name, domain, and URL, store id, code, and name, register id, code, and name, and `device_token`. There is no separate device key pair. The register id is the server device UUID. The store id is the branch id in this codebase.
5. `terminal::save` JSON-encodes `TerminalConfig` and seals it with `CryptProtectData`. The flag is `CRYPTPROTECT_UI_FORBIDDEN` only. `CRYPTPROTECT_LOCAL_MACHINE` is not set, so the scope is the current Windows user. Extra entropy is the literal `ai-pos-terminal-config-v1`. The file is `terminal.bin`. A `.bin.tmp` file is renamed over it. There is no storage version field. There is no backup file.
6. Startup calls `terminal::load`. Missing file means not activated. A DPAPI failure returns "This terminal was activated under another Windows account" and the process does not mint a new device identity. A damaged JSON file is also an error. The current startup then falls through to the developer `.env` config when that mode is enabled. An acceptance build ignores `.env`.
7. The device token stays in the sealed file and in the Rust API client. `TerminalStatus` omits it. The frontend does not decide activation trust.

There is no signed entitlement, public verification key, or `key_id` on this path.

## Capability cache and the 24-hour lease

`apps/desktop/src/lib/capabilities.ts` stores a snapshot in `localStorage` under `ai-pos.register-capabilities.v1:{environment}:{tenant}`.

`subscription_seen_at` is set when a snapshot includes `subscription_operational`. `SUBSCRIPTION_LEASE_MS` is 24 hours.

`subscriptionIsLocked()` is true when:

- the snapshot says `subscription_operational === false`, or
- that flag was true and `subscription_seen_at` is older than 24 hours.

Callers that block ordinary selling on this lock:

- `chargeGate` and `preparePermittedBatch` in `apps/desktop/src/features/checkout/checkout.ts`
- `submitCharge` in the same file
- `submitReturn` in `apps/desktop/src/features/returns/returnsClient.ts`

The message is "New sales stay closed until the subscription is verified." Returns use the same lock with their own message.

Separate time rules that are not this lease:

- `entitlement_until` drops purchased capabilities after that timestamp.
- `promotional_until` drops promotional capabilities.
- `OFFLINE_ADDON_SECONDS` (24 hours) drops paid add-ons on an offline unlock. Core selling stays on the store profile.

The server still enforces subscription state on its own requests. This lease is only the register's local copy.

## Offline queue

`Db::enqueue` writes `sync_queue` in the tenant SQLite file. Sales and returns use that table. Push results are `applied` and `duplicate` (`SyncPushResult` in `apps/api/app/schemas/payloads.py`). A duplicate idempotency key does not apply the sale twice (`tests/test_sync.py`).

## Pharmacy

`blockPharmacyOfflineSale` refuses medicine checkout when the profile has `pharmacy_catalog` and the session is offline. The cached catalogue is not treated as a lot release.

## What this flow cannot do

- Prove a permanent offline entitlement.
- Tell a stale 24-hour lease from a remote suspension except by the boolean already in the snapshot.
- Bind a copied configuration to a device key. Copy protection is DPAPI current-user scope plus the secret device token inside the same file.
- Allocate stock to one terminal. Offline sales use the cached branch quantity.
