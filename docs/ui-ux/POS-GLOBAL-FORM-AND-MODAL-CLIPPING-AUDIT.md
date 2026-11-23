# Form and modal clipping audit

Date: 23-11-2026

## Defect

The Restaurant/Cafe portion chip (for example Half — AED 6.00, selected) draws its selected edge with Tailwind `ring-2`. That ring is an outset box-shadow. The chip sits in a dialog body with `overflow-y-auto`.

`packages/design-tokens/src/scrollbars.css` then sets `overflow-x: clip` on every vertical scroller that is not also a horizontal scroller. Clip is intentional: it stops the wheel from sticking to a control. It also crops anything painted outside a child’s border box, including an outset ring and an outline with a positive offset.

The selected chip therefore loses the outer part of its orange edge. The border looks cut on the sides that sit against the scroller. The price text and the checkmark stay inside the button. The crop is the stroke, not the label.

This is the same mechanism on the quantity stepper’s old `outline-offset`, the cashier picker (`ring-2 ring-primary`), and the catalogue search field, which put `focus-within:ring-4` on the same element that has `overflow-hidden`. That utility is rewritten to `overflow: clip`, which crops the field’s own focus ring.

## Shared cause

| Piece | Role |
| --- | --- |
| `scrollbars.css` `.overflow-y-auto` | Sets `overflow-x: clip` so the wheel reaches the real scroller |
| `scrollbars.css` `.overflow-hidden.overflow-hidden` | Rewrites `overflow: hidden` to `overflow: clip` |
| Outset `ring-*` and positive `outline-offset` | Paint outside the border box, where clip removes them |

Box sizing is already `border-box` through Tailwind. The controls are not exceeding a declared height. The selected stroke is what crosses the clip edge.

## Inventory

Shared and inspected:

| Surface | File | Clip risk |
| --- | --- | --- |
| Portion chips | `QuantityModal.tsx` | Outset ring inside the dialog scroller. This is the reported selector. |
| Serving options, modifiers, ingredient radios | `PriceOptionModal.tsx` | Same dialog scroller. Selected state was a 1px border, flush with the clip edge once the card is full width. |
| Quantity stepper | `QuantityField.tsx` | Positive outline offset inside the same scroller. |
| Size and colour cells | `VariantPicker.tsx` | Outset focus ring inside the picker. |
| Cashier picker | `PinUnlock.tsx` | Outset ring on the pressed card. |
| Catalogue search | `SearchInput.tsx` | Focus ring on the clipped box. |
| Modal card | `apps/desktop/src/index.css` `.modal-card` | `max-h` plus scroll. Header and footer stay outside the scrolling body in `QuantityModal` and `PriceOptionModal`. |
| Product, payment, and cart controls | `ProductCard.tsx`, `TenderPanel.tsx`, `CartItemCard.tsx` | Many already use `ring-inset`. Left as they are. |

Profile forms (grocery product entry, electronics serials, fashion variants, laundry services, settings, checkout) use these shared controls or `modal-input`. They were not each opened in a window in this pass. Laundry and Cafe were not launched.

## What was not a cause

The document root font size is unchanged. Browser zoom still scales rem. The portion prices are not cut off by a too-small line-height. The quantity validation rules are unchanged.
