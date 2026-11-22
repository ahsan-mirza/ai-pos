# O4 financial snapshot and persistence

The queued sale is the financial record on the register. Replay uses the amounts on that event.

## What is stored on the sale

`queue.ts` `buildChargeEvents` builds one `sync_queue` event of type `sale`. Each line from `saleItems` carries:

- product id, quantity, and unit
- `unit_price_cents` and `list_price_cents`
- `tax_rate_bps`, `tax_cents`, and `line_total_cents`
- promotion id and `discount_cents` when a promotion reduced the line
- manual discount cents, reason, and override when the cashier entered one
- serial value, when the line already has one
- currency, totals, tenders, cashier, branch, and `sold_at` on the sale payload
- the event `idempotency_key`

`tax_rate_bps` is `rateFor` of the policy used for `lineCharge`. It is the rate at charge time, not a rate to be looked up again later.

A return event stores `original_sale_id` and `total_refund_cents`. `returns.rs` `enqueue` writes that event and the `local_returns` mirror in one SQLite transaction. The refund amount is the amount on the event. O4 does not add a new return policy.

## What a later change must not do

`price_lines` in `sale_service.py` computes the expected VAT from `item.tax_rate_bps` when that field is present. It does not replace that rate with the current `TaxPolicy` rate. The line is still rejected when `tax_cents` or `line_total_cents` does not match that snapshotted rate, the unit price, the quantity, and the discounts.

A line that omits `tax_rate_bps` still has to match the current policy. That is the previous behaviour for events queued before this field existed.

The local tests reopen the database after a product price change and after a settings change. The queued `unit_price_cents`, `tax_cents`, `total_cents`, and currency stay as they were inserted. The catalogue price and `business_settings` currency do change.

## Atomic queue write

`Db::enqueue` inserts the batch inside `Db::transaction`. A second enqueue of the same idempotency key fails, and `pending_count` stays 1. A return whose cashier or store does not match the unlocked session is rejected before the transaction, and `pending_count` stays 0.

The server still records an applied event by idempotency key. `sync_service.py` returns `duplicate` for a key that was already applied. O4 does not change that path.

## What was not added

No second outbox. No new sales table. The sale payload in `sync_queue` is the snapshot. `local_returns` is the existing mirror of a queued return, written in the same transaction as its queue row.
