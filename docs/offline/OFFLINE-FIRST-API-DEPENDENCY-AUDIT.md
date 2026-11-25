# Offline-first API dependency — audit

Date: 25-11-2026

The unlock screen used to throw `Cannot reach the API at http://localhost:8000. Check that the backend is running.` from `apps/desktop/src/lib/api.ts` whenever a fetch failed. That client uses `VITE_API_BASE_URL`, which in development is `http://localhost:8000`. A failed fetch now uses the offline notice. The keypad replaces any leftover localhost sentence with a local-PIN message. A cashier who has unlocked online on this browser can enter the PIN again while the server is unreachable. That check uses a saved verifier, not an access token. The desktop window still uses the Rust Argon2 cache.

## What was calling it

The status bar asked `peripheralSnapshot()` through that browser client on every register, including the Tauri app. A failed fetch became the API light. The Rust process was already using the URL stored at activation (`DesktopConfig.api_base_url`). Until activation that URL is `http://not-activated.invalid`, and calls fail as offline. `POS_DEV_ENV_CONFIG` can still point a developer build at `API_BASE_URL`.

Local SQLite is opened in the Tauri setup before any of those requests. Catalogue, cashiers, checkout, held carts, and the sale `sync_queue` already have desktop paths that do not use the Vite URL. Expenses, settings identity, and several retail screens still call the server through `retail_request` and show an error when it is down.

## What stays remote

Sales, returns, and allocations keep the existing O5/O6 `sync_queue`. Staff provisioning keeps its own outbox. Expenses are not inserted into `sync_queue`. A new `local_expenses` table holds them.

Business settings are still refused offline. This pass does not queue identity edits.

## What changed

The desktop status probe calls the activated server's `/health`, not `VITE_API_BASE_URL`. Localhost is a development endpoint only. A remote `http://` server is not called. The stored URL is not replaced. When the probe fails, the register stays open and the status says local operations remain available.
