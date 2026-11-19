# Stage 1.3 — Register form parity

Date: 19 November 2026. Business Pro remains the reference. The installed register was not used.

## What changed

The inventory API already accepts up to 1000 purchase-order lines and 1000 transfer lines. The register forms sent one line, and receiving posted only the first outstanding line.

The register now builds one payload for every line:

- `apps/desktop/src/features/inventory/documentLines.ts` checks unique products, whole quantities, unit cost, different source and destination stores, outstanding receipt quantity, and pharmacy lot and expiry on a lot-controlled line.
- Purchase orders take a supplier, a note, and any number of product lines, then save through the existing `POST /api/v1/inventory/purchase-orders`. Product create is unchanged.
- Receiving posts every entered outstanding line through the existing receive endpoint. A quantity above the remainder is rejected before the request.
- Transfers take a source, a destination, and any number of lines through `POST /api/v1/inventory/transfers`. Ship and receive still use the existing endpoints. Opening a transfer loads its lines.
- Category, brand, and model create and rename are shown only when the signed-in user is not bound to a store. The API already returns 403 for a store-bound user. Units stay available to an inventory manager because that route does not use the catalog-admin rule.

`documentLines.test.ts` covers two purchase lines, a repeated product, a transfer between the same store, a two-line receipt, and an over-receipt. Desktop typecheck passed.

## API check on the disposable grocery tenant

A Floor Manager on `inv-accept` created a two-line draft for the existing oats product and `INV-TIN`, then cancelled it. Status went from 201 to cancelled. On-hand quantities and movement counts for both products stayed the same. A live transfer was not posted, because a requested transfer reserves stock at the source.

`tests/test_inventory.py` already covers a two-line purchase order, partial receipt, over-receipt refusal, and a transfer that moves stock and IMEIs. Those tests were not re-run in this pass. The register change does not alter the API.

## Screens that already exist and are not yet at Business Pro parity

The register already has stock, products, categories, brands, models, units, pricing, price lists, price changes, batches, replenishment, stock counts, purchase orders, transfers, serial search, and the pharmacy lot actions. Several of those screens are still shorter than Business Pro: category and brand editing is a name field, price lists and price changes are read-oriented, stock counts add one draft line at a time, and purchase discounts, VAT lines, approval, and print are not separate register controls because those fields are not on `PurchaseOrderCreate`.

## Not run

The acceptance executable was rebuilt from this source with `pnpm exec tauri build --config src-tauri/tauri.inventory-acceptance.conf.json --no-bundle` and `CARGO_TARGET_DIR` set to `acceptance/inventory/target`. Frontend build finished, then the release profile finished in 38.62 seconds. The executable is `acceptance/inventory/target/release/ai-pos-desktop.exe`, 20,881,408 bytes, written 19 November 2026 17:21:46 UTC. No installer was produced. The new window was not opened. The installed AI POS process remained the only live desktop, and global clicks could hit it.

No viewport was opened. No new screenshot was captured.

## Status

Inventory forms parity: **IN PROGRESS**.

Multi-line purchasing and transfers: **PASSED WITH LIMITATIONS**. The payload and the disposable two-line purchase order are verified. The Windows form and a stock-moving transfer were not run.
