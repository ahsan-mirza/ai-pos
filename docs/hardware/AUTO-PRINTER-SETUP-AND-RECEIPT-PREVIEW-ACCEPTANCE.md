# Automatic printer setup and receipt preview

Date: 25-11-2026

26-11-2026: Printer & Drawer now includes Serial / COM beside Windows, USB, Network / Wi-Fi, Bluetooth, and None. The live sample is still only on this page. Choosing generic ESC/POS does not print during discovery. See `AXIZPOS-UNIVERSAL-PRINTER-CONNECTIVITY-ACCEPTANCE.md`.

Software status: **PASSED WITH LIMITATIONS**. Physical printer acceptance: **NOT RUN**.

Register changes require `devices:manage` or `settings:manage`. A cashier can still view status. The live preview remains on this page and still sends nothing to the printer. The 25-11-2026 permission and physical-print note is `PRINTER-PERMISSION-AND-PHYSICAL-PRINT-VERIFICATION-ACCEPTANCE.md`.

The live sample slip is on POS Settings → System & Register → Printer & Drawer. Checkout, payment confirmation, and Bill History do not mount it.

## Automatic discovery

Opening Printer & Drawer probes the saved queue and lists Windows printers. A hardware change refreshes the same list. Discovery does not print and does not kick the drawer.

| Situation | Result |
| --- | --- |
| One ready, compatible printer and no cashier choice | The existing discovery policy selects that queue. The page says it was automatically selected. |
| More than one verified printer | The page asks the cashier to choose. |
| Candidate, including Toshiba Native Windows Driver | The queue stays selected. Receipt printing is not marked operational. Drawer kick stays off. |
| Unsupported or virtual | Receipt printing is not activated. |
| Missing queue | The previous name is kept and the missing warning is shown. |

Queue name, driver, port, and Windows identity are still stored on the register. The print transport is derived from that driver and port when a job is sent. A renamed queue with the same driver and port can be restored. An unrelated queue is not substituted.

## Setup steps

The Printer & Drawer page shows five steps:

1. Printer detected — queue, driver, and port.
2. Compatibility — receipt transport and drawer kick are separate. Open/closed stays `Not reported`.
3. Receipt preview — sample invoice at 58 mm or 80 mm. Changing the width redraws the slip. Nothing is printed.
4. Test receipt — one sample slip, no sale, no drawer kick.
5. Setup result — an open queue is not the same as verified paper output.

## Live preview

`ReceiptPreviewPanel` is rendered only from `ReceiptHardwareCard`. It calls the same `renderReceipt` used for sales, at 384 dots for 58 mm or 576 dots for 80 mm. The image is shown at that paper width. The two widths are separate renders, not one bitmap scaled.

The sample number is `SAMPLE-1001`. It uses the register's business name, address, tax number, logo, header, and footer when those are configured, plus sample lines (portion and modifier text), tax, subtotal, discount, total, cash, and an on-account balance. Building the sample does not create a sale, a payment, or a stock movement.

Paper width on this page updates the preview immediately. When the cashier may change the register, the new width is saved. A candidate printer can be saved without being marked operational.

## Checkout and reprint

After a successful payment the cashier is still asked. Yes sends the saved slip to the configured printer and shows printing progress. The settings preview does not open. No skips printing. The choice is not remembered.

If printing fails, the payment stands and the cashier sees:

`Payment successful, but the receipt printer is unavailable. You can print this bill later from Bill History.`

Retry and PDF download stay on that panel when a PDF is available.

Bill History print sends the stored invoice. It does not open the settings preview, recalculate prices, or create another sale.

## Toshiba and the blank receipt

`Toshiba POS Printer (CR)` with Toshiba Native Windows Driver on `Toshiba: 0_USB` remains a Candidate. Jobs for that driver use Windows GDI, not raw ESC/POS. An empty raster is rejected before feed and cut. It is not marked verified. The queue was not installed on this PC, so no page was printed and no drawer pulse was sent. Details are in `docs/hardware/BLANK-RECEIPT-PRINTING-ROOT-CAUSE-AND-FIX.md`.

## Tests

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

`pnpm exec vitest run src/features/printing/settingsPreview.test.tsx src/features/printing/printerSettingsModal.test.tsx src/features/checkout/receiptConfirmation.test.tsx src/components/shell/deviceStatus.test.ts --reporter=dot`

4 files, 37 tests, 0 failed, exit 0. Duration 1.66s.

Rust printer tests from the blank-receipt pass still apply. No API invoice suite was required for this UI path. No production deploy was made.

## Limitations

- Physical output was not compared with the preview.
- Drawer open or closed is still not sensed.
- Portal logo and header text refresh the preview when the register reloads business settings. They are not edited on this page.
- A spooler accept is still not treated as proof the paper shows the slip.

## Connection choices — 25-11-2026

Printer & Drawer can select Windows, USB, Network / Wi-Fi, Bluetooth, or None. The preview is still only on that page. USB uses the Windows queue. An open network port stays a candidate. Bluetooth does not kick the drawer. See `docs/hardware/UNIVERSAL-PRINTER-CONNECTIVITY-ACCEPTANCE.md`.
