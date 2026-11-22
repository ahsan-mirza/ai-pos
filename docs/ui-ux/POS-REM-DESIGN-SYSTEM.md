# POS rem design system

Date: 22-11-2026

The desktop POS sizes its own interface in `rem`. `1rem` follows the browser root font-size. The app does not set `html { font-size }` and does not use a `62.5%` root trick. Browser zoom and a larger default font-size scale the same tokens.

Tokens live in `packages/design-tokens/src/tokens.css` and are imported by the desktop app. There is one set. Colors stay the existing AxizPOS primary, canvas, and charcoal values.

## Spacing, type, and controls

| Token | Value |
|---|---|
| `--pos-space-1` … `--pos-space-12` | `0.25rem` through `3rem` |
| `--pos-radius-sm` … `--pos-radius-xl` | `0.375rem`, `0.5rem`, `0.75rem`, `1rem` |
| `--pos-radius-pill` | `999rem` |
| `--pos-text-xs` … `--pos-text-2xl` | `0.6875rem` through `1.5rem` |
| `--pos-control-sm` / `md` / `lg` | `2rem` / `2.5rem` / `3rem` |
| `--pos-icon-sm` / `md` / `lg` | `0.875rem` / `1rem` / `1.25rem` |
| `--pos-product-image-height` | `7rem` |
| `--pos-product-footer-height` | `2.375rem` |

Tailwind’s default spacing, type, and radius scales are already rem (`h-10` is `2.5rem`, `px-4` is `1rem`). Arbitrary sizes in the POS use rem or these variables, for example `h-[var(--pos-product-image-height)]`.

Shared controls:

- `PosButton` and `PosIconButton` in `apps/desktop/src/components/shell/posControls.tsx`. The product-card details control uses the icon button at `--pos-control-sm` (`2rem`) and a circular radius.
- `PosSearchInput` keeps the leading search icon and the existing 150ms debounce.
- The docked-cart breakpoint is `min-width: 80rem` (`POS_DOCKED_QUERY`). That matches a 1280px-wide layout when the root font-size is the browser default of 16px.

## Product card

`CatalogTile` in `apps/desktop/src/features/checkout/ProductCard.tsx` is the sale-grid card for grocery, electronics, fashion, and restaurant menu items.

1. Image well, `7rem` tall. The details icon sits at the top end of the image (`0.5rem` inset) and does not add a row.
2. Category, then a two-line name.
3. One row: quantity badge, then currency and price. The row may wrap only when the column is narrower than the pair.
4. Branch-stock footer, `2.375rem`, on stock cards. Menu cards omit it.

Photos use `object-fit: contain`. A missing photo stays inside the `7rem` well. The catalogue grid is `repeat(auto-fill, minmax(min(100%, 13.125rem), 1fr))` with a `0.875rem` gap. Rows size to their content (`content-start`) so a card does not stretch to the pane.

## Profiles

Grocery, electronics, fashion, restaurant, and laundry share this token file, the shell, the buttons, and the search field. Laundry order intake does not render `CatalogTile`. Restaurant menu cards do not show a branch-stock footer.
