# O4 local-first checkout design

O4 extends the O3 session, snapshot, and pull. It does not add a second bootstrap service. The client still cannot name a table. The allowlist is `products` and `checkout_settings`.

## Dataset

| | `checkout_settings` |
| --- | --- |
| Identity | One document per tenant, record id `checkout` |
| Scope | The tenant of the authenticated terminal. The page is served only for that terminal's session |
| Schema | The same session `schema_version` as the product snapshot |
| Contents | `currency`, `vat_registered`, `prices_include_vat`, `standard_rate_bps`, `tax_authority`, `trn`, `legal_name`, `legal_name_ar`, `receipt` |
| Parents | None. Product prices stay on the product payload |
| Page order | One record at position 0. The page size limit still applies |
| Delete | Not used. A settings change is an upsert |
| Local table | Existing `business_settings` (`currency`, `tax_json`, `receipt_json`) |
| Checkout | `currency.ts` reads that row. A missing generation does not clear a previous row |

## One generation

`sync.rs` `bootstrap_catalogue` downloads the settings page before it activates products. `Db::activate_bootstrap` replaces `products` and writes `business_settings` in one SQLite transaction, and only when the staged product count matches. `sync_queue` is not in that transaction.

If the staged count is short, the function returns an error and does not write the new settings. The previous products, the previous `business_settings` row, and the queued sales stay.

A settings pull uses operation `settings`. `apply_product_pull` writes `business_settings` and advances `last_seq` in the same transaction as any product changes in that batch. A gap still returns an error and leaves `last_seq` where it was.

## What checkout uses

Product lookup uses the active `products` rows. Price and tax use `lineCharge` with the policy in memory, which `syncBusinessCurrency` loads from `business_settings`. The register does not have a second tax calculator.

Promotions, customers, and serials keep the caches they already had (`promotions.ts`, `customers.rs`, `serials.rs`). Those caches are not part of this generation. A sale that needs a provider payment, a pharmacy lot, or a serial reservation against another till is not treated as ready just because the product catalogue is present.

## Consistency

The settings document is copied after the feed counter is locked and before the session commits, in `start_session`. A later `BusinessSettings` update is a change-feed row, not a rewrite of that page. The register therefore does not pair a new tax rate with the previous snapshot's products unless it has applied the pull that carries both, in order.

Changes committed during the download have a sequence above the session watermark, so the following pull returns them.
