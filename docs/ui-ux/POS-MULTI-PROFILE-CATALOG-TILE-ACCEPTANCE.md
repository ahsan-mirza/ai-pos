# Multi-profile catalogue tile acceptance

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

The shared sale-grid card is `CatalogTile` in `apps/desktop/src/features/checkout/ProductCard.tsx`. Grocery, electronics, fashion, and restaurant/cafe render it through `ProductCard`. Fashion size groups render it through `ModelCard`. Laundry order intake does not import either component.

This pass did not change stock math, `allocationLabel`, `withTerminalAllocation`, prices, or the sale queue. The open register was the laundry till and was not used.

## How it was tested

Each profile fixture renders the real `ProductCard` after `bindCapabilityTenant` and `applyProfile` set that business profile. Allocation figures come from `withTerminalAllocation` on the product, which is the same function the register uses offline. Fashion groups use `modelGroup` and `ModelCard`. Laundry exclusion is a read of every `apps/desktop/src/features/laundry` source file.

No disposable Grocery, Electronics, Fashion, or Restaurant window was opened. No screenshot was taken. Browser zoom at 100%, 125%, 150%, and 200% on the live catalogue was **NOT RUN**.

## Card contract

| Check | Result |
| --- | --- |
| Image well | Class uses `--pos-product-image-height` (`7rem` in `packages/design-tokens/src/tokens.css`) |
| Image fit | `object-contain` on the photo |
| Details control | `absolute end-2 top-2` inside the image well. Accessible name `Details for {name}`. It is not a row above the category |
| Badge then price | Quantity or `+ Modifiers` appears before the currency amount |
| Stock footer | `--pos-product-footer-height` (`2.375rem`) on grocery, electronics, and fashion. Restaurant and cafe omit it |
| Long name | `line-clamp-2`, full name on `aria-label` |
| Long price | USD 12,345.67 stays in `whitespace-nowrap` inside `overflow-hidden` |
| Grid | `repeat(auto-fill, minmax(min(100%, 13.125rem), 1fr))`, gap `0.875rem`, `content-start`, card `h-auto` |
| Pixel lengths | None in `ProductCard.tsx`, `ProductPhoto.tsx`, `cataloguePresentation.ts`, or `VariantPicker.tsx` |

The card does not set a fixed total height. Documented compact proportion stays the image well, the text block, and the optional footer.

## Allocation

A grocery product with branch stock 59 and this register's remainder 40 exposes `This register: 40 available` on the badge `title` and `aria-label`. A different product's remainder of 7 is not shown. The visible badge stays `59 Pieces`.

Zero remainder says `This register: allocation exhausted` and the visible badge is `Out of stock` when branch stock is also zero. A product with no allocation field does not mention a register remainder.

The fashion size card uses the same `allocationLabel` sentences. Before this pass, `ModelCard` only said `In stock` or `Out of stock`, so a grouped fashion tile dropped the register sentence. The visible label is unchanged. The accessible name now appends each variant's existing allocation sentence.

## Profiles

| Profile | What the rendered card showed |
| --- | --- |
| Grocery | Photo, `59 Pieces`, allocation sentence, branch-stock footer. A second fixture has no `<img>` and stays in the same image well |
| Electronics | Category, serialized marker, `6 Pieces`, allocation sentence, branch-stock footer. SKU stays on the product record; the compact card does not add a SKU row |
| Fashion | Stock card shows `4 Pieces` and `This register: 40 available`. The size group card shows `Choose size & colour` and the same allocation sentence |
| Restaurant | `O810 Grill`, `+ Modifiers`, price, image well. No branch-stock footer, no `Pieces`, no register sentence |
| Cafe | `House coffee`, no photo, no modifiers badge, no `Out of stock`, no branch-stock footer |
| Laundry | Source under `features/laundry` contains `New Order` and does not contain `CatalogTile` or `ProductCard` |

## Defect fixed

`ModelCard` omitted the register allocation from the badge accessible name. It now calls `allocationLabel` for each variant and puts those sentences on `title` and `aria-label`.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/catalogCard.test.ts src/features/checkout/cataloguePreference.test.ts src/features/checkout/catalogueView.test.tsx src/components/RegisterLayout.test.ts src/components/shell/posControls.test.ts src/features/settings/settingsRoutes.test.ts src/features/checkout/catalogProfileAcceptance.test.tsx --reporter=dot`

7 files, 33 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

## Not tested

- Browser zoom at 100%, 125%, 150%, and 200% on the desktop catalogue window.
- A live Grocery, Electronics, Fashion, or Restaurant register. The open till is Laundry, and it was not switched or used for a sale.
- Screenshots.
