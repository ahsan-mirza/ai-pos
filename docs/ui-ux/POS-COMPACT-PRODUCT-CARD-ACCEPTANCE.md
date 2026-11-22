# Compact product card acceptance

Date: 22-11-2026

Shared component: `CatalogTile` and `ProductCard` in `apps/desktop/src/features/checkout/ProductCard.tsx`. Variant cards use the same tile. The catalogue grid is `catalogueLayoutClass` in `cataloguePresentation.ts`.

## Layout

1. The details control is a `PosIconButton` over the top end of the image. It is not a separate row. Accessible name: `Details for {product}`.
2. Category, then the name (`line-clamp-2`, tooltip and `aria-label` hold the full name).
3. One row: quantity badge, then currency and price (`gap-2`, which is `0.5rem`). The badge uses `whitespace-nowrap`. The row may wrap only when the column cannot hold both.
4. The badge’s visible text is the quantity the card already showed (`59 Pieces`, a weight, “Out of stock”, or “Not tracked”). When this register has an allocation remainder, the badge `title` and `aria-label` still include that sentence (`This register: 40 available`). The remainder is not replaced by branch on-hand, and branch stock stays on the footer button.
5. Menu cards (restaurant and cafe) omit the branch-stock footer. They can show a modifiers badge in the same price row.
6. Photos use `object-fit: contain` inside a `7rem` well (`--pos-product-image-height`). The footer is `2.375rem` (`--pos-product-footer-height`).

At a 16px root font-size those tokens are 112px and 38px. A typical grocery card is about 15.3rem to 16.5rem tall (image `7rem`, details about `6rem`, footer `2.375rem`), inside the `15.3125rem`–`19.375rem` band. The previous card was about 760px tall with an image near 415px.

## Profiles

| Profile | Card |
|---|---|
| Grocery, electronics, fashion | Stock badge, price, branch-stock footer |
| Restaurant and cafe | Menu price and modifiers when present; no stock footer |
| Laundry | Order intake does not use this card |

Allocation math, `allocationLabel`, and `withTerminalAllocation` are unchanged.

## Grid

`repeat(auto-fill, minmax(min(100%, 13.125rem), 1fr))`, gap `0.875rem`, `content-start`. Measured with the running preview stylesheet:

| Catalogue width | Columns | Card |
|---|---|---|
| 75rem (1200px) | 5 | about 14.3rem wide |
| 60rem (960px) | 4 | |
| 47.5rem (760px) | 3 | |
| 40rem (640px) | 2 | |
| 31rem (496px) | 2 | |
| 22.5rem (360px) | 1 | no horizontal overflow |

Image height stayed `7rem` at each width. Zoom 100%, 125%, 150%, and 200% did not add horizontal overflow on that grid.

The open register during this check was the laundry till, so grocery and restaurant catalogues were not clicked in a live session. The measurements use the shared card classes and tokens those profiles render.

## Frontend tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/catalogCard.test.ts src/features/checkout/cataloguePreference.test.ts src/features/checkout/catalogueView.test.tsx src/components/RegisterLayout.test.ts src/components/shell/posControls.test.ts --reporter=dot`

`pnpm exec tsc -p tsconfig.json --noEmit`

Result: 6 files, 25 tests, exit 0. Typecheck exit 0.

Pricing, tax, stock calculations, and the sale queue were not modified.

Profile rendering, the restaurant stock-footer omission, register allocation text, and the laundry exclusion are in `docs/ui-ux/POS-MULTI-PROFILE-CATALOG-TILE-ACCEPTANCE.md`.
