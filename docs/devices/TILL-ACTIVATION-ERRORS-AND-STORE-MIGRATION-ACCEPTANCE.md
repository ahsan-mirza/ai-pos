# Till activation errors and store migration

Date: 27-11-2026

Verdict: PASSED WITH LIMITATIONS.

No production signing key was generated. No deployment was made. Native Windows activation, restart persistence on a built till, and a second physical till were not run.

## Root causes

`Permanent entitlement signing is not configured.` came from a missing approved signing seed, not from a key the server is allowed to invent. `ENTITLEMENT_SIGNING_SEED` and `ENTITLEMENT_SIGNING_SEED_FILE` were empty on this machine. The API now returns `entitlement_unconfigured` with `The server cannot currently issue a permanent device entitlement. Contact your administrator.`

The pending-sale stop came from the desktop refusing every activation whenever the local queue had rows, before it asked which store the key belonged to. Same-store pending records are no longer a refusal. A different tenant with pending records opens the migration assistant.

## Signing readiness

The server loads the seed from `ENTITLEMENT_SIGNING_SEED`, then from `ENTITLEMENT_SIGNING_SEED_FILE`. It does not create either value.

The key id is `ENTITLEMENT_SIGNING_KEY_ID`. `POS_ENTITLEMENT_KEY_ID` is used only when the server id is empty. If both are set and they differ, the code is `entitlement_key_mismatch` and the message is `The active signing key does not match a trusted desktop public key. Contact your administrator.`

`POS_ENTITLEMENT_PUBLIC_KEY` and `POS_ENTITLEMENT_PUBLIC_KEYS` (`id:base64`, comma-separated) are the desktop trust list. When that list is non-empty, the derived public key and the active key id must match an entry. A mismatch uses the same `entitlement_key_mismatch` code. An invalid seed uses `entitlement_unconfigured`. The seed is never returned.

Business Pro calls `GET /api/v1/devices/activation-preflight` when Registers loads. A till whose status is Activation pending can still open **Activation key**. Other tills stay disabled while `ready` is false, and the menu shows the administrator message. The yellow banner is not restored.

Signing runs before the one-time key is marked used and before the device token is rotated. A failed sign rolls back with the request. Preflight does not write.

## Structured activation decision

`POST /api/v1/terminals/activation-preflight` takes the store code, the activation key, and the local register context: tenant id, store id, register id, device public key, and pending sales, returns, and cash movements. It does not mark the key used.

Comparison uses tenant, store, and register ids as 32 hex characters. Store names are not compared.

| Situation | `code` | Blocks activation |
| --- | --- | --- |
| Key missing, used, or expired | `activation_invalid` | Yes |
| Other tenant, any local pending row | `pending_different_store` | Yes, until sync or a local archive marker |
| Signing seed missing, invalid, or not trusted | `entitlement_unconfigured` or `entitlement_key_mismatch` | Yes |
| Target till is revoked and the package has no free seat | `plan_limit` | Yes |
| Same tenant, same register, pending sales | `pending_same_store` | No. Message asks to sync before that register identity is retired |
| Same tenant, another till, pending rows | `pending_same_store` | No. Existing-store sentence |
| Server still has unsynced rows for the target device | `pending_offline` | No on preflight. `POST /activate` still returns 409 with the sync sentence and does not consume the key |
| Otherwise | `ready` | No |

Messages:

- Same store, additional till: `Existing store detected. Your pending records will remain associated with this store and register.`
- Replacement or server unsynced sales: `1 sale is waiting to sync. Synchronize it before retiring the previous register identity.` The count is plural when it is not 1.
- Different store: `This device contains transactions belonging to another store. Sync or export them before changing stores.`
- API unreachable while local rows exist: `Your records are محفوظ locally. Reconnect to the original store to synchronize before migration.`
- Signing unavailable: `The server cannot currently issue a permanent device entitlement. Contact your administrator.`

A response that is not one of these codes is shown only when it does not look like a traceback or a database exception. Those become `Activation could not be completed. Contact your administrator.`

## Same store

An additional till, or a replacement of the same register id, does not show the different-store assistant and does not ask for Excel or CSV. Local SQLite stays on the tenant database file. Before the new config is saved, pending queue rows with an empty origin are stamped with the current register id. A later upload sends that `device_id` for those batches only. New sales use the new till. Invoice numbers and idempotency keys are not rewritten. If the upload cannot run, the queue and the stamped id stay. Same-store activation is not refused only because those rows are still local.

After a successful activation the existing restart path downloads that store's catalogue, pricing, settings, and staff. This run did not watch that download on a built till.

## Different store

When the key's tenant id differs and the device still has pending sales, returns, or cash movements, the till shows the migration assistant before it changes identity. Counts are listed by type.

- **Sync to original store** calls the existing upload, then checks the decision again. This is the preferred path.
- **Export pending data** writes `exports/pending-records.csv` and `exports/pending-records.xls` (SpreadsheetML). The copy is for review. It is not a sync and not a settlement. The queue is not deleted. Old-store sales are not imported as new-store sales. Payment, cash, VAT, and inventory ledgers are not moved.
- **Cancel migration** closes the assistant.
- **Archive locally and change store** writes `migration-archive.json` next to the terminal file with the target store, the counts, and `queue_cleared: false`. Only that marker lets a different-store activation continue. The old tenant SQLite file stays at `tenants/{slug}/ai-pos.db`. The new tenant opens its own empty database and bootstraps its own catalogue.

A different tenant with zero pending rows is `different_store` and is not blocked.

## Tests recorded

API, from `apps/api`, 27-11-2026:

`node ../../scripts/python.mjs --env=test -m pytest tests/test_activation_preflight.py tests/test_entitlement.py tests/test_permanent_entitlement.py -q --tb=short`

Result: 15 passed in 11.80s. Exit code 0. Ruff on the activation files passed.

That run covers a missing seed, an invalid seed, a key-id mismatch, a trusted public key that does not contain the active id, a matching test key pair, activate refused then accepted on the same unused key, same-store additional till with pending sales and cash movements, same-store replacement, different-store pending rows that do not consume the key, and a different tenant with no pending rows. The test key is the RFC 8032 seed used only inside the test process. It is not written to server configuration.

An earlier run the same day of `tests/test_activation_preflight.py`, `tests/test_entitlement.py`, `tests/test_permanent_entitlement.py`, and `tests/test_till_release.py` was 18 passed in 11.82s.

Rust, from `apps/desktop/src-tauri`:

`cargo test --lib -- --test-threads=8 terminal::tests preference_tests entitlement:: sync::`

Result: 17 passed in 2.02s. Exit code 0. This includes the pending-queue identity test (original register id and invoice payload kept, export rows still present), the activation-block sentences, permanent entitlement verification, and sync batch behaviour.

Desktop, from `apps/desktop`: Vitest `src/features/activation/messages.test.ts` — 1 passed. `tsc -p tsconfig.json --noEmit` — exit code 0.

Business Pro, from `apps/web`: `tsc -p tsconfig.json --noEmit` — exit code 0. Vitest `src/features/registers/status.test.ts` and `businessCode.test.ts` — 8 passed.

## Not run

- Native Windows activation of a built till, including persistence after restart.
- A second physical till, live original-store upload of a preserved queue, and opening the exported CSV and Excel files on Windows.
- Two disposable tenant databases proving a sale row cannot be inserted into the other tenant. The API test classifies a foreign tenant id; it does not copy sales.
- Production configuration of an approved signing seed. Until that secret is installed, this server still cannot issue a permanent entitlement for a live till.
