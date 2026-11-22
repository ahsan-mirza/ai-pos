# Bootstrap protocol

Authenticated register calls, under the existing terminal token. The server uses the device row for tenant, branch, and terminal. A client-supplied branch id is not accepted as proof.

## Endpoints

- `POST /api/v1/terminals/bootstrap/sessions` locks the catalogue feed counter, copies the current product rows for that device's branch, and stores them on `bootstrap_snapshot_items`.
- `GET /api/v1/terminals/bootstrap/sessions/{session_id}/pages?dataset=products&after_position=-1&limit=50` reads that copy. `limit` is 1 to 100. Ordering is the snapshot position.
- `GET /api/v1/terminals/bootstrap/pull?cursor=...&limit=50` returns changes with `seq` greater than the cursor.

The only dataset name accepted is `products`. Any other name is HTTP 403 `dataset_forbidden`. The response does not echo the rejected name.

## Snapshot

The copy and the watermark are taken in one transaction after `catalog_feed_counters.value` is locked. Pages do not read the live `products` table. A rename after the session starts stays off the pages and appears on the pull.

The session expires 30 minutes after `created_at`. A later page is HTTP 409 `snapshot_expired`. The register starts a new session. An expired page does not change the local catalogue.

`since_seq` is the counter value at copy time. The opaque cursor on each page is bound to that session, the device, the branch, and the tenant.

## What is not in this download

Tax, receipt text, and currency stay on `settings.rs`. Staff PIN hashes stay on the online unlock path. Customers, menus, and serials stay on their own caches. `sync_queue` is not read or written here.
