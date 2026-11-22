# O4 checkout data dependency audit

Checkout already prices a sale on the register and stores that price on the queued event. O4 adds only the configuration that those calculations read and that the server was still comparing with a later rate. Datasets that already have their own cache, or that need a live provider or a stock allocation, stay out of the catalogue feed.

## Classification

| Dataset | Class | Where checkout reads it | O4 bootstrap |
| --- | --- | --- | --- |
| Products, including the price, unit options, and price-list JSON already on the product row | REQUIRED_OFFLINE | `products` via the O3 generation. `cart.ts` `lineCharge` uses the line's unit price | Already `products`. Not a second copy |
| Currency and VAT policy | REQUIRED_OFFLINE | `currency.ts` `businessTax` / `syncBusinessCurrency`. Filled from `settings.rs` `business_settings` | New dataset `checkout_settings` |
| Receipt header and footer | OPTIONAL_OFFLINE | `settings.rs` receipt cache, used when printing. Not an input to `lineCharge` | Included on the same frozen settings document so the printed slip matches that generation. Not required to price a sale |
| Units | REQUIRED_OFFLINE | Product `sellable_units` on the O3 product payload. `sale_service.py` `price_lines` rejects an unknown unit at sync | Not a separate dataset |
| Price lists and product prices | REQUIRED_OFFLINE | Columns on the product payload (`prices`, `price_lists`). The charged price is copied onto the sale line | Not a separate dataset |
| Manual discounts | OPTIONAL_OFFLINE | Entered on the line in `queue.ts` `manualDiscountFields` and stored on the event. Limits live in the existing settings cache (`pos_policy`), not in this feed | Not added. The amount on the queued line is the snapshot |
| Promotions | OPTIONAL_OFFLINE | `promotions.ts` `loadPromotions`: the last fetched list when offline | Not added. A promotion change reaches a disconnected till only after that existing refresh |
| Customers and groups | OPTIONAL_OFFLINE | `customers.rs` `search` / `refresh`. `wholesaleClient.ts` `searchCustomers` uses the local cache in Tauri. A sale does not require a customer | Not added. The existing cache is not the catalogue feed |
| Cash tender | REQUIRED_OFFLINE | `tenders.ts` cash branch. Underpayment stays blocked | No new data |
| Card, QR, and pay-later | REQUIRES_ONLINE | `tenders.ts` requires a provider intent in status `PAID` unless a manager has approved a manual card entry on an integrated terminal | No approvals are invented |
| Bank transfer and cheque | OPTIONAL_OFFLINE | `tenders.ts` accepts a non-empty reference. That reference is not a bank settlement | No new verification |
| Pharmacy medicine | BLOCKED_OFFLINE | `checkout.ts` `blockPharmacyOfflineSale` | Not downloaded. The block is unchanged |
| Serials and IMEIs | REQUIRES_ONLINE | `serials.rs` caches free serials for this register and marks one `taken` when it is already on a local queued sale. That cache is not a reservation against another till. `sale_service.py` still checks the serial when the event is applied | Not added |
| Staff PIN hashes | NOT_APPLICABLE | Unlock stays on `cached_users` | Not downloaded |
| `inventory_levels`, `stock_movements` | NOT_APPLICABLE | Stock is applied on the server when the sale syncs | Not downloaded. Snapshot quantity remains the branch cache from `products_out` |
| `sync_queue` | NOT_APPLICABLE | Local outbox. It is the sale record on the register | Not a bootstrap dataset and not replaced |
| Menus, laundry production, payment-gateway configuration | NOT_APPLICABLE | No offline checkout path required them | Not downloaded |

## Currency and tax

`settings.rs` `refresh` loads `GET /api/v1/settings` and `GET /api/v1/settings/receipt` into the single `business_settings` row (`currency`, `tax_json`, `profile_json`, `receipt_json`). `currency.ts` `applyTax` reads `enforced` or `vat_registered`, `prices_include_vat`, and `standard_rate_bps`.

That cache was outside the O3 feed, so a tax change was not ordered with the product snapshot. `bootstrap_service.py` now freezes one `checkout_settings` document with the catalogue session: currency, VAT registration, prices-include-VAT, standard rate, tax authority, TRN, legal names, and the receipt JSON. Payroll, messaging, and ledger settings are not copied.

`BusinessSettings` insert and update append a `catalog_changes` row with operation `settings` in the same flush as the counter update. Pages for `checkout_settings` read `bootstrap_setting_snapshots`, not the live row.

## Sale amounts

`queue.ts` `saleItems` writes `unit_price_cents`, `tax_cents`, `line_total_cents`, and `tax_rate_bps` from `lineCharge` and `rateFor` before the event is queued. `sale_service.py` `price_lines` uses `tax_rate_bps` when the line carries it, and checks the line arithmetic against that rate. A line with no rate still has to match the current policy.

## What stays online

Card, QR, and pay-later stay blocked until the existing provider reports `PAID`. Pharmacy medicine stays blocked offline. Serial availability against other tills is not decided from `register_serials`. Customer-specific tax treatment is snapshotted only when the register sends `tax_rate_bps`; otherwise the server still uses the current policy.
