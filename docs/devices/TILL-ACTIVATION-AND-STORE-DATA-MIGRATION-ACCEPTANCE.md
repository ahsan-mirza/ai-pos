# Till activation and store data migration

Date: 27-11-2026

No production signing key was generated. No deployment was made.

## Signing

The API signs a permanent entitlement only when `ENTITLEMENT_SIGNING_SEED` (or `ENTITLEMENT_SIGNING_SEED_FILE`) and a key id are set. The key id is `ENTITLEMENT_SIGNING_KEY_ID`, or `POS_ENTITLEMENT_KEY_ID` when the server id is empty. If both ids are set they must be the same.

`POS_ENTITLEMENT_PUBLIC_KEY` and `POS_ENTITLEMENT_PUBLIC_KEYS` are public. When either is set, the derived public key and the active key id must match that desktop trust list. A mismatch returns `entitlement_key_mismatch` and does not consume the activation key. A missing seed returns `entitlement_unconfigured` with the message `The server cannot currently issue a permanent device entitlement. Contact your administrator.` That message is the server's real configuration result. It is not replaced with a sync or export message. The same-store and different-store rules that followed this note are in `TILL-ACTIVATION-ERRORS-AND-STORE-MIGRATION-ACCEPTANCE.md`.

Business Pro calls `GET /api/v1/devices/activation-preflight` before an activation key is offered. The response includes the key id and public key when signing is ready, and never the seed. The local `.env` has no signing seed, so a live till on this machine still cannot be signed until an approved secret is configured.

## Same store

Register a till and choose **Existing store**. The operator picks a branch of the current tenant. The new register gets its own code, invoice series, and device identity. The activation screen does not ask for an export. After the key is accepted, the register downloads that tenant's catalogue through the existing bootstrap. Printer and drawer settings stay on the machine.

## Different restaurant

Choosing **Different restaurant** does not copy this tenant. The other store uses its own activation key. Master data can move only through the existing catalogue workbook (`GET /api/v1/catalogue/workbook/export`, preview, then confirm). That workbook carries categories, products, SKUs, barcodes, units, brands, portions, and modifiers. It does not carry sales, payments, credit, cash balances, stock movements, device keys, or passwords. Opening stock stays on the inventory opening workflow. Recipes are not in this workbook. A CSV importer was not added; the Excel workbook is the validated transfer.

## Stages

The till activation screen shows seven stages: store identified, register assigned, entitlement signing verified, activation credential validated, device activated, initial synchronization started, and synchronization completed or requiring attention. A failure marks the stage that matches the API code (`entitlement_unconfigured`, `entitlement_key_mismatch`, `activation_invalid`, `plan_limit`, `device_binding`, `pending_offline`, or network). Success marks the device activated and leaves synchronization as the restart step. It does not claim the catalogue download has finished.

## Tests recorded

API, from `apps/api`:

`pytest tests/test_entitlement.py tests/test_permanent_entitlement.py tests/test_catalogue_workbook.py -q --tb=line`

Result: 19 passed in 13.90s. Exit code 0.

That run includes a missing seed that does not consume the activation key, a desktop public-key mismatch that does not consume the key, preflight with a seed file plus matching `POS_ENTITLEMENT_KEY_ID` and public key, reimport without duplicate products, an invalid workbook that writes nothing, and an import that does not change stock.

Desktop typecheck, from `apps/desktop`: `tsc -p tsconfig.json --noEmit`. Exit code 0.

Admin portal typecheck, from `apps/web`: `tsc -p tsconfig.json --noEmit`. Exit code 0.

Rust, from `apps/desktop/src-tauri`: `cargo test --lib entitlement:: -- --test-threads=8`

Result: 7 passed; 0 failed; 120 filtered out. Exit code 0. Finished `test` profile in 26.80s, tests in 0.03s.

## Not exercised on hardware

A second physical till, a restart, and offline unlock were not run. Those paths stay on the existing activation and bootstrap contracts. A live activation on this machine remains blocked until an approved signing secret is installed. No key was created to remove that block.
