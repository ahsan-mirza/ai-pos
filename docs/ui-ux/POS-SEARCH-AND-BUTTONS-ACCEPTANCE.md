# POS search and button standardization

Date: 22-11-2026

The register uses one search field and one button shape across Grocery, Electronics, Fashion, Restaurant, and Laundry. Those profiles share the desktop POS shell. This change does not alter Business Pro pages.

## Search

Shared pieces:

- `PosSearchInput` and `PosSearchToolbar` in `apps/desktop/src/components/shell/posControls.tsx` and `apps/desktop/src/features/inventory/ui.tsx`
- `useDebouncedSearch` and `beginRequest` in `posControls.tsx`
- Checkout product search already used `useProductSearch` and `SEARCH_DEBOUNCE_MS`

Debounce is the existing shared value, **150ms** (`SEARCH_DEBOUNCE_MS`). The input updates immediately. The query that reaches a list request updates after the user pauses. Enter commits the current text at once. Escape clears the shared search field and commits the empty query. A newer inventory request ignores an older response through `beginRequest`.

Search buttons removed:

- Products list. The field searches on its own. Add product stays.
- IMEI / serial lookup. A query of at least 4 characters searches after the debounce. Shorter text does not call the API.

Refresh stays an icon button on stock and pricing, with tooltip `Refresh` and accessible name `Refresh results`.

Screens on the shared search field:

- Stock, products, pricing, and serial lookup
- Settings search (local filter, inverse field, search icon)
- Laundry customer finder (local filter, search icon)
- Checkout product search, customer search, and restaurant guest search already debounced; their icons are 18px and they use the same delay

Exact tag lookup (`Find garment`) still submits. Barcode and SKU resolution on the checkout field still runs immediately on Enter or a scan.

## Buttons

`PosButton` and `PosIconButton` are the shared controls.

| Variant | Treatment |
|---|---|
| Primary | Orange fill, white label, `rounded-xl` |
| Secondary | White fill, zinc ring, same radius and height |
| Outline | Transparent fill, zinc ring |
| Ghost | No fill, same type and focus ring |
| Destructive | Red fill, same radius |
| Icon | Square, centered icon, accessible name |

Sizes: small `h-9`, medium `h-12`, large `h-14`. Medium is the standard POS action. Inventory `PrimaryButton` / `QuietButton` and laundry `PrimaryButton` / `SecondaryButton` render these variants, so those profiles match.

Also moved onto the shared buttons: settings confirm, currency save, staff save, laundry settings shortcut, restaurant table and order-type actions, reorder actions, and sync retry / discard.

## Left on their existing sale surface

Checkout pay, quotes, held carts, and the round catalogue add control stay as they are so the sale layout does not move. Badge pills and the appearance preview chips are not action buttons.

## Checks

Inventory toolbar tests, POS control tests, and a TypeScript check were run from `apps/desktop`. The products and stock toolbars were checked in the running register preview.
