# O2 acceptance report

O2 is **PASSED WITH LIMITATIONS**.

No production deployment. No developer database, inventory-acceptance database, or production database was opened or migrated. Alembic revision `20261122_0124` adds a nullable `devices.device_public_key_thumbprint` and was not applied. API tests used in-memory SQLite (`sqlite://` from `tests/conftest.py`). Register tests used temporary directories, not the installed register's `terminal.bin`.

The native Tauri window was not started, stopped, or taken offline. A browser preview was not used as evidence. The library tests below ran on this Windows machine and do call DPAPI.

A disconnected register cannot learn a remote suspension, plan change, or permission change until it syncs. The last valid entitlement stays in force while it is offline.

## What was implemented

- `POST /api/v1/terminals/activate` signs an Ed25519 permanent entitlement when the register sends a device public key. The same terminal row is reused. A different public key on `POST /api/v1/terminals/entitlement` is 409 `device_binding`. A new activation key is the rebind.
- The register verifies the signature in Rust before it stores version 2 state. The seal is Windows DPAPI for the current user, with the existing entropy `ai-pos-terminal-config-v1`.
- Ordinary selling ignores the 24-hour subscription lease when verification is `VALID_PERMANENT_ENTITLEMENT`. A missing entitlement on an already activated O1 file keeps the lease. An invalid signature, unknown key, or binding mismatch blocks selling.
- Pharmacy medicine checkout stays blocked while offline. A server-reported subscription block still blocks selling. Permissions and the stock ledger are not bypassed.
- Readiness is an explicit code. `OFFLINE_READY` means this baseline only. It does not mean stock is partitioned between tills.

## Commands and counts

Run from `apps/api` with `apps/api/.venv`:

`python -m pytest tests/test_entitlement.py tests/test_permanent_entitlement.py tests/test_terminal_activation.py tests/test_sync.py::test_duplicate_event_does_not_apply_twice -q --tb=line`

14 passed.

Run from `apps/desktop/src-tauri`:

`cargo test --lib -- --test-threads=8`

35 passed, 0 failed. That includes signature, tamper, wrong key, binding, clock, readiness, O1 storage upgrade, corrupt-file retention, DPAPI seal/unseal, and the sealed-file reload that verifies an entitlement 30 days after issue, enqueues one sale, and rejects a second insert of the same idempotency key. The machine clock was not changed.

Run from `apps/desktop`:

`pnpm exec vitest run src/features/checkout/checkout.entitlement.test.ts src/features/checkout/checkout.pharmacy.test.ts src/components/RegisterErrorBoundary.test.tsx`

10 passed (4 entitlement gate, 3 pharmacy, 3 error boundary).

## Matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| Backend issues a signed entitlement | PASSED | The 14 API tests. Signatures verify with `cryptography`. The response text does not contain the seed. |
| Desktop verifies the entitlement | PASSED | Rust `verify` tests in the 35. |
| Device binding enforced | PASSED | Rust mismatch test and API 409 `device_binding`. |
| Tenant and branch binding enforced | PASSED | Rust mismatch tests. |
| Private key stays on the server | PASSED | Release `production_trusted_keys` has no test seed. The test key id `o2-test-1` is compiled only under `cfg(test)`. |
| DPAPI protects persisted state | PASSED | `sealed_config_round_trips` and the sealed restart test on this Windows machine. |
| O1 activation still loads | PASSED | `o1_storage_upgrades_without_replacing_the_identity` keeps the register id and device token. |
| Restart works offline | PASSED WITH LIMITATIONS | The sealed file reloads with no HTTP call. The Tauri window was not restarted. |
| More than 24 hours does not block a valid entitlement | PASSED | Rust clock argument and `checkout.entitlement.test.ts`. The machine clock was not changed. |
| Bootstrap readiness is explicit | PASSED | `readiness_order_is_explicit`. |
| Existing sales queue remains | PASSED | Restart test writes `sync_queue`. Duplicate server apply: `test_duplicate_event_does_not_apply_twice`. |
| Pharmacy stays blocked offline | PASSED | `checkout.pharmacy.test.ts` and the entitlement gate test. |
| Existing permissions stay enforced | PASSED WITH LIMITATIONS | The entitlement document's `capabilities` list is empty and is not applied as rights. The full permission suite was not re-run. |
| Inventory ledger unchanged | PASSED | `apps/api/app/services/inventory.py` has no diff. O2 does not change `move_stock` or stock tables. |
| Protected environments untouched | PASSED | In-memory SQLite and temp files only. Alembic `20261122_0124` was not applied. |

## Limitations

- A release build has no compiled-in production public key, so it fail-closes with `UNKNOWN_SIGNING_KEY` until `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY` are set at build time. Those values are public keys only.
- Native Windows activation of a window, offline restart of that window, and the WebView/GPU blank surface were not run.
- `ONLINE_SYNC_REQUIRED` means the queue has pending rows or the last server snapshot said the subscription was blocked. It does not itself close selling when the entitlement is valid.
- Per-terminal stock allocation and local staff management were not implemented.
- O3 through O8 were not implemented.

## O2 files

API: `app/services/entitlement_service.py`, `app/services/device_service.py`, `app/routers/v1/terminals.py`, `app/schemas/devices.py`, `app/models/device.py`, `app/core/config.py`, `alembic/versions/20261122_0124_device_entitlement.py`, `tests/test_entitlement.py`, `tests/test_permanent_entitlement.py`, `tests/conftest.py`.

Register: `src-tauri/src/entitlement.rs`, `src-tauri/src/terminal.rs`, `src-tauri/src/lib.rs`, `src-tauri/src/db.rs`, `src-tauri/src/demo.rs`, `src-tauri/Cargo.toml`, `src/features/checkout/checkout.ts`, `src/features/checkout/checkout.entitlement.test.ts`, `src/features/returns/returnsClient.ts`, `src/lib/capabilities.ts`, `src/lib/tauri.ts`, `src/components/shell/KeyboardStatusBar.tsx`.
