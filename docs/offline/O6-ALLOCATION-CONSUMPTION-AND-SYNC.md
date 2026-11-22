# O6 allocation consumption and sync

The sync endpoint is still `POST /api/v1/sync/push`. `push_batch` still commits the request once, or rolls it back.

HTTP 200 still means every event in that request is `applied` or `duplicate`. HTTP 409 and 422 still commit nothing new from that request. Same key and same payload is `duplicate` and does not consume allocation or post stock again. Same key and a different payload is `idempotency_conflict`. The register still quarantines that as `conflict` and does not retry it.

## Sale payload

`SalePayload.allocations` is optional. Online sales omit it and can use only unreserved `available` stock. An allocated sale includes one entry per allocation:

- `allocation_id`
- `sequence` (the next integer after `last_sequence`)
- `product_id`
- `quantity`

The idempotency key is not taken from the client payload. The sync event key is stored on `terminal_allocation_consumptions`.

## Atomicity

Server: allocation update, consumption row, and `SALE_OUT` commit together. A later event that fails rolls the whole request back, including any allocation draw from an earlier event in that request.

Register: `Db::consume_allocation` updates the local balance and inserts the `sync_queue` row in one SQLite transaction. If the quantity does not fit, neither write remains.

A replay uses the original key. The server returns `duplicate` before `_dispatch`, so the allocation is not drawn again.

## Sequence

The next sale must use `last_sequence + 1`. A repeated or skipped sequence is `sync_rejected` and commits nothing.
