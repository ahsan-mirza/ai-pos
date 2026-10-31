# Architecture

The plugin is a separate Python package at `plugins/einvoicing`. The API process adds that directory to `sys.path` and imports `einvoicing`. A second process can run `uvicorn einvoicing.main:app` on port 8090. A third process runs `python -m einvoicing.worker`.

Both processes use `DATABASE_URL`, the same PostgreSQL database as the API. They do not open a second database.

## What the plugin owns

Immutable invoice snapshots, credit-note snapshots, provider accounts, submission attempts, the outbox, webhook events, and plugin audit rows. See `DATABASE_SCHEMA.md`.

## What the plugin reads and does not rewrite

`sales`, `sale_items`, `returns`, `customers`, `stores`, `business_settings`. Amounts stay in integer cents. `money()` only formats those cents.

## How a sale becomes an e-invoice

1. POS checkout finishes with the existing receipt path.
2. Sync calls `sale_service.record_sale`.
3. `einvoicing_bridge.note_sale` writes `einvoicing_outbox` only when the add-on is on and the buyer TRN is non-empty. The write is a savepoint. A missing table logs a warning and leaves the sale committed.
4. `process_outbox` loads the posted sale, classifies it, stores the snapshot, and submits through the selected adapter.
5. Today the only adapter is `MockAsp` (`code = "mock"`).

A return follows the same outbox with `kind = "return"` after a credit-note number is assigned. A credit note is created only when that sale already has an e-invoice.

## Status

Internal statuses and allowed moves are `TRANSITIONS` in `einvoicing/engine.py`. Provider status is a separate column (`MOCK_ACCEPTED`, `MOCK_REJECTED`, and the other mock outcomes). The portal cannot set a status. Retry is allowed from `REJECTED`, `RETRY_PENDING`, and `PROCESSING_ERROR`. After five attempts the outbox row becomes `DEAD`.
