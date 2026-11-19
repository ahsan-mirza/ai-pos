# Inventory production readiness

Date: 19 November 2026. No production deployment, production migration, or production tenant activation was performed.

## Implemented in this pass

- Register purchase orders, receiving, and transfers submit every line in one existing API request.
- Store-bound users no longer see category, brand, or model write controls. The API still rejects those writes.
- The stale acceptance runtime device key was replaced with the token already enrolled in `com.axizpos.inventory.acceptance`. Device product list returns 200. Device stock returns 403. Cashier stock returns 403 for missing permission.
- Desktop typecheck passed. `documentLines`, product payload, and inventory tab tests passed: 16 tests.

## Still required before a release review can start

- Windows product create, update, archive, gallery, and the four viewports on the acceptance register.
- Launch the rebuilt acceptance executable `acceptance/inventory/target/release/ai-pos-desktop.exe` (19 November 2026 17:21:46 UTC, identity `com.axizpos.inventory.acceptance`) and complete the Windows checks. It was not opened while the installed register stayed on screen.
- Remaining Business Pro gaps on categories, price lists, price changes, counts, and documents that the API does not model (line discounts, print).
- Profile acceptance for fashion, electronics, food service, and a fresh pharmacy pass.
- An `ai_pos_app` RLS session on a disposable database.
- A signed production installer. `AXIZPOS_SIGN_THUMBPRINT` is unset, so signing stays blocked. The signing check was not disabled.
- A measured performance run and a rehearsed backup restore.

## Environment left running

The installed register PID 33672, `C:\Users\ahsan\AppData\Local\AI POS\ai-pos-desktop.exe`, was not clicked or closed. The acceptance API on `127.0.0.1:18081` and `axizpos-inventory-acceptance-db` on `127.0.0.1:55433` were left up because acceptance is not finished. Developer `.env` and developer app data were not modified.

## Status

| Gate | Outcome |
|---|---|
| Product form | PASSED WITH LIMITATIONS |
| Product CRUD | NOT RUN |
| Images and gallery | NOT RUN |
| Inventory forms parity | IN PROGRESS |
| Multi-line purchasing and transfers | PASSED WITH LIMITATIONS |
| Business profile acceptance | NOT RUN |
| Security and data integrity | PASSED WITH LIMITATIONS |
| Production build | BLOCKED |
| Code signing | BLOCKED — CERTIFICATE REQUIRED |
| Production deployment readiness | BLOCKED |
| Production authorization | APPROVAL PENDING |
