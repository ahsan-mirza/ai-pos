# POS offline startup and API connectivity

Date: 25-11-2026

Software status: **PASSED WITH LIMITATIONS**. Native acceptance: **NOT RUN**. Nothing was deployed.

## Workstreams

| Workstream | Result |
| --- | --- |
| API URL configuration | Development localhost is allowed only when the build is not a release. A remote server must be HTTPS. The activated URL is not rewritten. |
| Offline POS startup | The status bar and the unlock keypad no longer say "check that the backend is running." A failed fetch uses the offline notice. A cashier with a saved PIN verifier can unlock while the server is unreachable, without an access token. SQLite still opens during Tauri setup. A register that was never activated is not granted a session. |
| Local SQLite operation | Existing catalogue, cashier, cart, and sale paths are unchanged. Expenses can be saved in `local_expenses` while the server is down. |
| Security | Saving a local expense still requires an unlocked register. PIN unlock does not create an access token. |

## Status the cashier sees

Offline:

`You're working offline. Local POS operations remain available. Pending changes will synchronize when a connection is restored.`

An individual online-only action, such as a petty-cash top-up, still explains that it needs the server.

## Tests

`cargo test --offline --lib connectivity` — 1 passed, exit 0.

`cargo test --offline --lib local_expenses` — 2 passed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` — exit 0.

Vitest `connectivity.test.ts`, `localExpense.test.ts`, `statusBar.test.ts` — 3 files, 18 tests, 0 failed.

`pytest tests/test_expenses.py::test_offline_client_key_posts_once` was not run. The default Python environment does not have `phonenumbers` installed, so the API suite could not start.

## Not run

The desktop app was not launched with the API stopped, then restarted, then reconnected against a disposable register. No Business Pro screen was compared.
