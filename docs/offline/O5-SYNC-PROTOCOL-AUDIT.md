# O5 sync protocol audit

Traced from the current sale and return push path. No protected database was opened.

## Queue record

`sync_queue` is created in `apps/desktop/src-tauri/src/db.rs` (`CREATE TABLE IF NOT EXISTS sync_queue`).

| Field | Role |
| --- | --- |
| `id` | Local event id |
| `batch_id` | One checkout or return batch |
| `idempotency_key` | Unique. Retries reuse this key |
| `entity_type` | `sale`, `sale_return`, and other synced entities |
| `operation` | `upsert` |
| `payload` | Original JSON. This is the financial snapshot for a sale or return |
| `occurred_at` | Event time |
| `status` | `pending`, `synced`, `rejected`, and now `conflict` |
| `attempts` | Incremented by `record_failure` on a transport or server-unavailable error |
| `last_error` | Safe message from the last refusal or transport failure |
| `created_at` | Local insert time |

`Db::enqueue` writes the batch in one SQLite transaction. `returns::enqueue` writes `sync_queue` and `local_returns` in that same transaction. A failed return writes neither.

`Db::next_pending_batch` selects `status = 'pending'` only, oldest batch first. `conflict` and `rejected` are not selected.

## Push

Register: `sync::flush` in `apps/desktop/src-tauri/src/sync.rs` posts `POST /api/v1/sync/push`.

Router: `push_sync` in `apps/api/app/routers/v1/sync.py`. It requires `require_device` and calls `push_batch`.

Request body: `SyncPushRequest` (`device_id`, `events`). Each event is `SyncEventIn`: `idempotency_key`, `entity_type`, `operation`, `payload`, `occurred_at`.

Server identity for an applied event is `SyncEvent` (`apps/api/app/models/sync_event.py`): tenant-unique `idempotency_key`, `payload_hash` from `canonical_hash`, `entity_type`, `entity_id`, `device_id`, `occurred_at`, `applied_at`. The full payload is not stored again on `SyncEvent`. The domain row (sale or return) holds the applied snapshot.

## Batch atomicity

`push_batch` applies every event, then commits once. `SyncRejected` rolls the whole batch back and returns HTTP 422 `sync_rejected`. `ApiError` rolls the batch back. A unique-key `IntegrityError` rolls the batch back.

One HTTP 200 therefore means every event in that request was `applied` or `duplicate`. A 409 or 422 means nothing new from that request was committed. Events committed by an earlier request stay committed.

The register must not treat HTTP 200 as proof without reading `results`. It counts `applied` and `duplicate`, then marks the local batch `synced`.

## Outcomes that already existed

`SyncPushResult.status` is `applied` or `duplicate`.

- Same key and same `canonical_hash`: `duplicate`. `_apply_event` returns before `_dispatch`, so stock and the sale are not applied again.
- Same key and a different hash: HTTP 409 `idempotency_conflict`. The original row is not overwritten.
- Validation and domain failures (`SyncRejected`, including stock and return-quantity failures): HTTP 422 `sync_rejected`, whole batch rolled back.
- Authentication: `require_device` rejects the request before `push_batch`. The register treats non-409/413/422 failures as unavailable, leaves the batch `pending`, increments `attempts`, and stops the flush.
- Network error and 5xx: same pending path. The register does not invent a new idempotency key.

## What O5 changed in this path

- After an `IntegrityError` rollback, if every key in the batch already exists with the same hash, the response is HTTP 200 with `duplicate` results. A hash mismatch on that path is still 409 `idempotency_conflict`. A missing key stays the generic 409 `conflict`.
- The register reads `error.code`. `409` plus `idempotency_conflict` marks the batch `conflict`. Other 409, 413, and 422 responses still mark `rejected`. Unavailable responses stay `pending`.

## Not claimed

A lost response after commit is safe only when the same key and payload are retried. That retry is the outcome lookup. There is no second lookup endpoint.

No per-event commit was added. A conflict inside a batch still rolls back the events that had not yet been committed by an earlier request.

`restamp_batch` and `relabel_shift_currency` remain the only payload rewrites, and they are the existing clock and shift-currency cases. O5 does not rewrite sale or return money.
