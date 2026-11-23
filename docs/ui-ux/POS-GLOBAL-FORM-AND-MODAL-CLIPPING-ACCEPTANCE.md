# Form and modal clipping acceptance

Date: 23-11-2026

Overall: **PASSED WITH LIMITATIONS**

## Root cause

Selected portion chips used an outset `ring-2`. The dialog body is a vertical scroller, and `packages/design-tokens/src/scrollbars.css` sets `overflow-x: clip` on those scrollers. The clip removes the part of the ring that sits outside the button, so the selected Half/Full edge looks cropped. The audit is `docs/ui-ux/POS-GLOBAL-FORM-AND-MODAL-CLIPPING-AUDIT.md`.

## Correction

`packages/design-tokens/src/tokens.css` adds `--pos-control-touch` (`3.5rem`), `--pos-control-line` (`1.25`), and `--pos-focus-width` (`0.125rem`).

`.choice-control` keeps a selected or pressed stroke as an inset shadow, and draws focus with a negative outline offset. Both stay inside the border box, so the scroller cannot crop them. `.control-focus` uses the same inset outline.

Applied to:

- Portion chips in `QuantityModal.tsx`
- Serving options, modifier cards, and ingredient radios in `PriceOptionModal.tsx`
- Size and colour cells in `VariantPicker.tsx`
- Cashier cards in `PinUnlock.tsx`
- Quantity stepper in `QuantityField.tsx`

The catalogue search field in `SearchInput.tsx` now paints its focus ring on a wrapper that does not clip. The inner box still clips to the rounded border.

Portion selection, prices, and quantity rules are unchanged. The root font size is unchanged.

## Zoom and profiles

| Check | Result |
| --- | --- |
| 100–200% WebView zoom of this stroke | NOT RUN in this pass. The previous quantity-modal zoom run measured the dialog before this stroke change. |
| Grocery, electronics, fashion windows | NOT RUN again for this stroke. Those windows were closed after the quantity acceptance. |
| Cafe | NOT RUN |
| Laundry | NOT RUN. The live register was not opened. |
| Physical touchscreen | NOT RUN. This machine has a touch pad and pen devices, and no touch digitizer. |

The inset stroke does not depend on zoom or on a profile. It removes the outset ring that the clip was cutting. A fresh WebView pass at 100%, 125%, 150%, 175%, and 200% is still required before this fix is marked passed on its own.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/quantityModal.test.tsx src/features/checkout/priceOptionModal.test.tsx src/features/checkout/cart.test.ts --reporter=dot`

3 files, 31 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

The changed components live in the desktop app. Web TypeScript was not run; the shared change is CSS.

## Remaining gaps

- Native WebView screenshots of Half/Full after the inset stroke, at 100% through 200%.
- Cafe and Laundry forms were not opened.
- Grocery weighed scale, electronics serial completion, and laundry service entry were not reopened for this stroke.
- Physical touchscreen acceptance remains NOT RUN.
