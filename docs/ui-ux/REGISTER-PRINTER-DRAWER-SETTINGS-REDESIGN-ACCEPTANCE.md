# Register printer and cash drawer settings redesign

Date: 27-11-2026

Verdict: PASSED WITH LIMITATIONS.

Nothing was deployed. The shared Register Settings modal was changed. Browser zoom at 125%, 150%, and 200% was not exercised.

## Layout

The dialog title is **Receipt Printer & Cash Drawer**. On a wide screen the printer connection and receipt controls sit on the left and a receipt preview sits on the right. The cash drawer group remains below those controls. Cancel and Save stay at the bottom of the dialog. The body scrolls inside a max height of `min(92dvh, 52rem)` so the footer is not pushed off a short window. Narrow widths stack the preview under the form.

## Behaviour kept

Windows, USB, network, Bluetooth, serial, and none still use the existing connection tabs and save path. Paper width is still 58 mm (384 dots) and 80 mm (576 dots). Copies, discovery, validation, test rendering, and test print are unchanged. Test print does not kick the drawer. A cashier without register permission can still view status and cannot save or test the drawer.

The preview uses the same sample receipt template as the settings preview. It refreshes when the paper width changes. Zoom expands the thumbnail. It does not create a sale, print, or kick.

## Drawer section

The drawer connection, cash and card triggers, profile, voltage, and pin stay in one group. A 24V profile with a confirmed 12V port shows a mismatch and Test Drawer Kick stays disabled. The button asks for one explicit pulse, names the printer and voltage, and then calls the same kick used after a cash sale. The result still says open/closed is Not reported.

## Tests

Desktop Vitest `printerSettingsModal.test.tsx` and the related printer tests: 24 passed in the same run as the drawer consistency checks. `pnpm exec tsc -p tsconfig.json --noEmit` exit code 0.

## Not run

- A live click through every connection mode on a built till.
- Visual check at 125%, 150%, and 200% zoom.
- Restart persistence on the MTP-3 register. Save still writes the existing local printer settings row.
