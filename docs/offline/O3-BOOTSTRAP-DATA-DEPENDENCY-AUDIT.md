# O3 bootstrap data dependency audit

Traced from the register and API. A dataset is listed only when checkout or unlock actually reads it. The protocol that follows is limited to the product catalogue.

| Dataset | Source | Local table | Scope | Needed before | Change signal | Sensitivity | Offline use |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Products | `GET /api/v1/products` keyset `after`, `catalog_service.list_products`. Revision is `GET /api/v1/products/revision` (`max(updated_at)`, count). | `products` via `Db::replace_products` from `sync::fetch_products` | Tenant catalogue. Stock quantity on the row is a cache, not a terminal allocation. | None | `products.updated_at`. Hard delete is not visible from the timestamp alone. | Names, SKUs, prices. No customer PII. | Checkout search and price. |
| Tax, profile, receipt | Settings refresh in `settings.rs` into `business_settings.tax_json`, `profile_json`, `receipt_json`. | `business_settings` | Tenant | Products can load without it. Checkout must not be ready on products alone. | Settings write. | Business configuration. | Totals and receipt text. |
| Currencies | `GET /api/v1/currencies` in `settings.rs`. | `foreign_currencies` | Tenant | Optional for cash in a foreign currency. | Rate row. | Rates. | Offline foreign cash. |
| Staff PIN cache | Online unlock writes `cached_users`. `auth.rs` verifies Argon2. | `cached_users` | The users who have unlocked on this register. | Not created by bootstrap. | Next online unlock. A disconnected till does not learn a remote disable until then. | PIN hash only. No plaintext PIN. | Offline PIN unlock, five-attempt lockout, `pos:access`. |
| Sales and returns | Local checkout. | `sync_queue` | This terminal | Must survive bootstrap. | Push replay. | Money and tax snapshots. | Existing queue. |
| Customers, menu, serials | Separate caches (`customers`, `menu_cache`, `register_serials`) filled by their own refresh commands. | Those tables | Branch where the command is scoped | Not required for a basic product checkout. | Their own refresh. | Customer rows are PII. Bootstrap does not copy them in O3. | Those screens when already cached. |

O3 bootstraps the product catalogue only. Tax and staff stay on the paths above. Bootstrap does not download plaintext PINs and does not copy `inventory_levels` or `stock_movements`.

Product writes are captured from the SQLAlchemy session, not from one router. `before_flush` in `bootstrap_service.py` records an insert, update, or delete for every `Product` the session is flushing. That covers the product API, inventory product saves, pharmacy product saves, pricing saves, and sync upserts that use the same model. A stock movement changes `InventoryLevel` and `StockMovement` and does not by itself rewrite the catalogue feed. The snapshot freezes the branch quantity that `products_out` already returns. Later attribute changes set `stock_authoritative` false so the register keeps the quantity it already stored.

A disconnected register still does not learn a staff disable, a permission change, or a subscription change until it syncs. The PIN cache is not part of this download.

`OFFLINE_READY` still requires a verified entitlement, a readable database, cached products, cached staff, and a capability snapshot. A product page alone is not enough.
