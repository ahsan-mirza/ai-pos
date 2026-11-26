# Sync Center pending upload: root cause and fix

Date: 26-11-2026

Status: **PASSED WITH LIMITATIONS**. Nothing was deployed. The photographed BADR-AL-MADINAH register queue was not on this computer, so those exact rows were not uploaded.

## Original failure

Sync Now left sales `BADR-AL-MADINAH-R01-000026`, `000027`, and `000028`, plus cash movements, on the Waiting tab. The register showed:

`Not synced: The server hit an unexpected error. Retry, and contact support if it keeps happening.`

That sentence is the API's unhandled-error text (`internal_error`, HTTP 500). The desktop prefixes it with `Not synced:` and leaves the batch `pending`. It does not mean the rows were discarded or marked sent.

## Root cause

Two things stacked.

1. A restaurant or cafe menu item may have no SKU. Recording the sale copied `product.sku` with a slice. A missing SKU raised `TypeError` inside the sale handler, which the sync endpoint did not catch, so the whole batch became HTTP 500. The sale line now stores a blank SKU when the item has none (`apps/api/app/services/sale_service.py`). A no-SKU menu sale is covered by `tests/test_optional_menu_sku.py::test_selling_a_menu_item_without_a_sku_syncs`.

2. The flush stopped at the first HTTP 500. Cash movements and later sales are separate batches with their own idempotency keys, but they never left the register while an earlier sale batch was crashing. A no-sale drawer open is a real `cash_movement` with kind `NO_SALE` and amount 0. It is not deleted and it is not sent through the sale endpoint.

On this machine the local `bayrut` tenant has `Daal Channa` with a null SKU and an active Full Plate portion. `record_sale` for that shape completed inside a transaction that was rolled back. It did not raise. The BADR-AL-MADINAH invoices are not in the local Postgres databases, and no local `sync_queue` contains those invoice numbers. The register that took the screenshot is using its own database and its configured API host.

## What changed

- `POST /api/v1/sync/push` catches an unexpected exception, rolls the batch back, logs the attempt id with the entity type and idempotency key, and returns HTTP 500 `internal_error` without the exception text. The message includes `Reference: <attempt>` when the register sends `X-Sync-Attempt`.
- The same key and payload stay pending. A retry does not mint a new key. HTTP 200 is still the only path that marks a batch sent. HTTP 422 and 409 still reject or conflict the batch. HTTP 401, 403, and 503 stop the flush. A single HTTP 500 does not: the failed batch stays pending and the next pending batch is uploaded in the same Sync Now.
- Sync Center shows the attempt count, the last attempt time (`sync_queue.last_attempt_at`), and the safe error on the row.
- Upload and download stay on separate paths. A failed upload does not move the catalogue cursor.

## What was not verified

- The native BADR-AL-MADINAH register was not opened, rebuilt, or synced. Its pending ids, payload hashes, and configured host were not readable from this PC.
- Business Pro was not checked for invoices `000026`–`000028`, because those sales are not in the local databases.
- A lost acknowledgement after a successful commit was not replayed against a live register. The existing idempotency rule still treats the same payload as a duplicate.
- Production was not deployed.

## Tests

API, from the repo root:

`node scripts/python.mjs -m pytest tests/test_sync.py::test_an_unexpected_sync_crash_rolls_back_and_names_the_attempt tests/test_optional_menu_sku.py::test_selling_a_menu_item_without_a_sku_syncs tests/test_shifts.py -q --tb=line`

3 passed, exit 0.

Desktop, from `apps/desktop/src-tauri`:

`cargo test --lib sync::tests -- --test-threads=1`

3 passed, 124 filtered out, exit 0. This includes `a_server_error_names_the_attempt_and_does_not_stop_later_batches`.

`node scripts/python.mjs -m ruff check app/services/sync_service.py app/routers/v1/sync.py app/main.py tests/test_sync.py` passed after the long line was wrapped.

The native installer was not rebuilt. The BADR-AL-MADINAH register was not synced.
