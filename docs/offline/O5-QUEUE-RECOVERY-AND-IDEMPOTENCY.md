# O5 queue recovery and idempotency

`sync_queue` is still the only outbound sale and return queue. No second outbox or ledger was added. No column was added. `status = 'conflict'` is a new value in the existing `status` text column. Existing `pending`, `synced`, and `rejected` rows are left as they are.

## Retry

`flush` calls `next_pending_batch`. Only `pending` rows are returned.

- Unavailable: `record_failure` increments `attempts`, writes `last_error`, leaves `pending`, and stops this flush. The next flush sends the same key and payload.
- `conflict` and `rejected`: not returned. They survive process restart because they are ordinary SQLite rows.
- Clock-ahead `restamp_batch` and shift-currency `relabel_shift_currency` remain the existing one-shot corrections. They are not used for sale totals.

No new exponential backoff was added. The existing engine already stops the current flush on the first unavailable batch and polls again later.

## Lost response

If the server commits and the response is lost, the local row stays `pending`. The next flush posts the same key. `_apply_event` finds the stored hash, returns `duplicate`, and does not call `_dispatch`. The register then marks the batch `synced`.

If the unique key races, `push_batch` rolls back and `_duplicates_after_rollback` returns `duplicate` when every hash matches. A different hash returns `idempotency_conflict` and the register quarantines the batch.

## Restart

`a_conflict_stays_out_of_the_pending_queue_and_keeps_its_payload` reopens the SQLite file. The conflict row is still present, still excluded from `next_pending_batch`, and `total_cents` is unchanged.

`a_queued_sale_keeps_its_price_after_restart_and_a_later_catalogue_price` still shows a pending sale snapshot surviving a later catalogue price.

## Dependencies

A return is a separate queue event that names the original sale in its payload. The server rejects a return whose sale or quantity is invalid and rolls that batch back. The local return row stays `rejected` or `pending`. It is not marked `synced` because an earlier event in another batch succeeded. There is no new dependency table.

## Visibility

`sync_center::conflict_count` counts distinct `conflict` batches. The status bar shows `Queue · 1 conflict` when that count is above zero, including when pending and failed are zero. That chip is not a resolve action.
