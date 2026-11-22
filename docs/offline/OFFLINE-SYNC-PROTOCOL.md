# Sync protocol

Status: the existing queue stays. The new protocol is not implemented.

`sync_queue` in the register SQLite file is the offline queue. `POST /api/v1/sync/push` returns `applied` or `duplicate`. A rejected event fails the batch with HTTP 422. Entity types are store, product, serial number, sale, repair ticket, sale return, customer, open order, and laundry order.

Not present:

- Per-event statuses for conflict, validation rejection, unauthorized, retryable failure, and schema mismatch.
- A server change cursor.
- Atomic pull batches.
- The status-bar phrases `Online · Synced`, `Online · N pending`, `Offline · N pending`, `Connection restored · Synchronizing`, and `Online · N sync failed`.

The queue must be extended. A second queue must not be added. An empty queue does not mean the register is online. A reachable API does not mean the cashier is signed in. HTTP 401 is authentication and HTTP 403 is permission. Neither is retried.
