# POS pixel-to-rem migration report

Date: 22-11-2026

Scope: application-owned desktop POS UI in `apps/desktop/src`, plus the shared tokens in `packages/design-tokens/src/tokens.css`. Business Pro, the marketing site, and super-admin were not part of this pass. Generated files, `node_modules`, and vendored packages were not edited.

## What was checked

A search of `apps/desktop/src` (`*.ts`, `*.tsx`, `*.css`) for CSS lengths written as `Npx` found one hit: a comment in `RegisterLayout.tsx` that explains why `80rem` matches a 1280px layout at the browser’s default 16px root. No application stylesheet, Tailwind arbitrary utility, or media query in that tree still declares a layout length in `px`.

The tree contains 258 of those source files. Media queries in `apps/desktop/src/index.css` and the docked-cart query use rem (`48rem`, `64rem`, `80rem`, and the existing container queries).

Root font-size is unchanged. There is no `html { font-size: … }` rule and no `62.5%` root.

## Shared tokens

See `docs/ui-ux/POS-REM-DESIGN-SYSTEM.md`. Tokens were added to the existing `packages/design-tokens/src/tokens.css` `:root` block. They were not copied into a second theme file.

Shell pieces that now size icons with rem classes instead of a pixel `size` prop:

- Outer sidebar (`SidebarNav.tsx`)
- Top navbar (`HeaderBar.tsx`)
- Settings navigation (`settingsUi.tsx`)
- Shared search fields (`posControls.tsx`, `SearchInput.tsx`)
- Product card and variant card icons (`ProductCard.tsx`, `VariantPicker.tsx`)

`PosButton` / `PosIconButton` heights stay on the Tailwind rem scale (`h-9`, `h-12`, `h-14`) and the `2rem` icon-button token.

`--pos-control-touch` (`3.5rem`), `--pos-control-line`, and `--pos-focus-width` (`0.125rem`) size the shared `.choice-control` selected stroke. The stroke is an inset shadow so a clipping scrollport cannot crop it.

## Exceptions that stay in pixel or device units

| Location | Why it stays |
|---|---|
| `POS_DOCKED_MIN_PX = 1280` | Documents the CSS-pixel width that `80rem` equals at a 16px root. Layout uses `matchMedia("(min-width: 80rem)")`. `window.innerWidth` and `matchMedia` report CSS pixels; the query string is rem. |
| Lucide `size={n}` on about 241 remaining icons | Lucide’s `size` prop writes the SVG `width` and `height` attributes. It is the library’s pixel attribute, not a CSS layout length. Shell, settings, search, and product-card icons use rem classes instead. |
| SVG `viewBox` and the field-icon data URIs in `index.css` | Drawing coordinates. The CSS `background-size` and padding for those icons are rem (`1.25rem`, `2.5rem`). |
| `CreditBadge` `style={{ width: \`${used}%\` }}` | A percentage of the track, not a pixel length. |
| Tauri window and printer APIs | Native APIs that take physical or logical pixels. Not converted. |
| Canvas, barcode, and device pixel ratio | Device or buffer coordinates. Not converted. |
| Tailwind `px-3`, `px-4`, and similar | Padding utilities. In Tailwind’s default theme these are rem (`px-4` is `1rem`). They are not pixel lengths. |

## Tests

Commands and results are in `docs/ui-ux/POS-COMPACT-PRODUCT-CARD-ACCEPTANCE.md`.
