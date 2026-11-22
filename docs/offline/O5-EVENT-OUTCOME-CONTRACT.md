# O5 event outcome contract

`SyncPushResult` is unchanged: `idempotency_key` and `status` of `applied` or `duplicate`. Existing clients that compare that JSON still match.

Other outcomes are HTTP errors, not extra `status` values on a 200 body. A 200 body contains only `applied` and `duplicate`.

| Semantic outcome | Wire result | Local `sync_queue.status` | Next automatic flush |
| --- | --- | --- | --- |
| Applied | 200, `status: applied` | `synced` | Not sent again |
| Duplicate | 200, `status: duplicate` | `synced` | Not sent again |
| Retryable or unknown commit | Network error, 401, or 5xx. Batch stays unacknowledged | `pending`. `attempts` increases. `last_error` is set | Same key and payload are sent again |
| Business or validation rejection | 422 `sync_rejected`, 413 `batch_too_large`, or 409 `conflict` | `rejected`. `last_error` holds the message | Not selected |
| Same key, different payload | 409 `idempotency_conflict` | `conflict`. `last_error` holds the message | Not selected |

`queue_status_for` in `apps/desktop/src-tauri/src/sync.rs` is the register mapping. HTTP 200 is handled before that function. A network failure is not treated as proof the server skipped the commit. The following retry uses the original key. If the server committed, `_apply_event` returns `duplicate` and does not dispatch again.

## Partial batch

Atomicity is per request, not per event. A later event that raises `SyncRejected` or `ApiError` rolls back every event in that request. The register marks that batch `rejected` or `conflict` and does not mark it `synced`.

Events from a previous successful request stay applied. The register does not mint new idempotency keys for them.

## Fields that are not added

No stack trace, token, or raw payload is copied into the error message beyond the server's existing safe `error.message`. `last_error` stores that message. The original `payload` column remains the only copy of the event body.
