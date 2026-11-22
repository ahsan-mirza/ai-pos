# Incremental pull

## Ordering

`catalog_feed_counters` has one row per tenant. A product flush increments `value` by the number of product changes in that flush and inserts `catalog_changes` rows with those sequence numbers, in the same transaction.

The next writer updates the same row, so it waits until the first transaction commits or rolls back. A rolled-back write releases the numbers with the row. A later commit cannot publish a higher sequence while a lower one is still open. The cursor is not `MAX(seq)` and it is not a timestamp.

Two threads allocating sequences on a file SQLite database produced 1..24 with no duplicates and no gaps (`test_feed_sequences_stay_unique_under_two_writers`).

## Cursor

The cursor is an HMAC of a canonical JSON body, using the API `jwt_secret`. The body contains schema version, tenant, branch, terminal, bootstrap session, and sequence. The register does not choose the sequence. There is no endpoint that accepts a caller-supplied sequence.

Pull rejects:

- a bad MAC as 401 `invalid_cursor`
- another tenant, branch, or terminal as 403 `cursor_scope`
- a cursor for an older session of the same register as 409 `cursor_generation`
- a sequence older than `retain_after`, or a gap in the retained rows, as 409 `rebootstrap_required`

`note_retention` deletes change rows at or below a sequence and raises `retain_after`. The pull does not skip those rows silently.

## Events

Each event has `seq`, dataset `products`, `record_id`, `operation` (`upsert` or `delete`), and a payload or null. An upsert of a later edit has `stock_authoritative: false`. The register applies the name, price, and active flag and keeps the branch quantity from the snapshot. A delete sets `is_active` to 0 and leaves the row, so a past sale can still show the name. The queue is not deleted.

The same sequence can be delivered again. A sequence at or below `last_seq` is ignored. A sequence that skips a number aborts the batch and does not move `last_seq`.
