# Blank receipt printing — root cause and fix

Date: 25-11-2026

Status: **BLOCKED** for physical acceptance. The software path is in place and covered by unit tests. A complete tax invoice was not seen on paper, so the issue is not marked passed.

## Screenshot findings

The register showed this queue:

| Property | Observed value |
| --- | --- |
| Windows queue | Toshiba POS Printer (CR) |
| Driver | Toshiba Native Windows Driver |
| Port | Toshiba: 0_USB |
| AxizPOS classification | Candidate |
| Automatic discovery | Enabled |
| Warning at the time | This device is not verified as a supported receipt printer |
| Paper width | 80 mm |
| Drawer connector | Pin 5 |

After a sale, the printer fed and cut the paper and the paper was blank.

## What this PC has installed

`Get-Printer` on 25-11-2026 did not list `Toshiba POS Printer (CR)`. Present queues:

| Queue | Driver | Port | Status |
| --- | --- | --- | --- |
| OneNote (Desktop) | Send to Microsoft OneNote 16 Driver | nul: | Normal |
| OneNote (Desktop) - Protected | Microsoft Virtual Print Class Driver | OneNote virtual port | Normal |
| Microsoft Print to PDF | Microsoft Print To PDF | PORTPROMPT: | Normal |
| iR-ADV C3525 | Canon Office XPS Class Driver | WSD | Offline |
| Canon Generic PCL6 Driver | Canon Generic PCL6 Driver | 10.10.101.250 | Normal |
| AnyDesk Printer | AnyDesk v4 Printer Driver | AD_Port | Normal |

`Get-PnpDevice` did not show a Toshiba printer. The only name match was the ACPI thermal zone, which is not a printer. No USB identity, driver version, or spooler datatype could be read for the Toshiba queue because Windows does not have it. No bytes were sent to a printer.

## Why it was Candidate

Classification uses the driver name and the port. It does not use the queue name, and the `CR` suffix is not treated as proof of ESC/POS.

`Toshiba Native Windows Driver` does not match a known receipt profile (`toshiba tec`, Epson, Star, and the other listed profiles). It is not an office or virtual driver, so it is not Unsupported. The result is Candidate: installed, possibly a receipt printer, not yet verified. Drawer kick stays off. That part of the old classification was right.

The warning was wrong. Candidate, Unsupported, and virtual queues all used `This device is not verified as a supported receipt printer.` Candidate is not a confirmed incompatibility.

The Register Settings sentence for this driver is now:

`Toshiba POS Printer (CR) was discovered using the Toshiba Native Windows Driver. Receipt printing has not yet been verified. Run the printer test to confirm the supported print method.`

The queue name is still stored. Discovery does not replace it with PDF, OneNote, or another queue.

## Where the receipt was lost

The sale path was already: payment is stored, the cashier is asked, Yes prints the saved slip, No skips it. A print error does not reverse the payment. Reprint uses that same slip and does not start another sale. This pass did not change that order.

The slip is drawn in the webview to a 1-bit raster (`packages/receipt`) and sent to the desktop process. `escpos_raster` wraps that raster as ESC/POS `GS v 0`, then sends a feed (`ESC d 4`) and a cut (`GS V 66`). `WritePrinter` submitted those bytes with datatype `RAW`.

Two defects sit on that path:

1. An all-white raster is a valid byte length, so the feed and cut were still sent. The paper moves and nothing is printed.
2. Toshiba Native Windows Driver on port `Toshiba: 0_USB` is a Windows graphics driver behind Toshiba's port monitor. It is not a known raw ESC/POS profile. A RAW ESC/POS job can be accepted by the spooler. The driver then ejects the page without drawing the raster. Feed and cut with a blank sheet matches that.

The renderer was not rewritten. A blank raster is now rejected before any feed or cut, with: `The invoice was generated, but its printable content could not be rendered.`

## Transport

| Driver and port | Transport |
| --- | --- |
| Known receipt profile, and not a native Windows driver | Raw ESC/POS |
| Toshiba Native Windows Driver, or a port starting with `Toshiba:` | Windows GDI bitmap |
| Unverified candidate with no receipt profile | Windows GDI bitmap. Raw bytes are not sent. |
| PDF, OneNote, PCL, PostScript, and other office or virtual queues | No receipt transport |
| Driver default datatype EMF or XPS | Windows GDI, including when a receipt profile would otherwise use ESC/POS |

GDI expands the same 1-bit raster to a 24-bit image and draws it with `StretchDIBits` through `CreateDC` / `StartDoc`. Paper width follows the raster: 384 dots is 58 mm (58.0 mm page width) and 576 dots is 80 mm (80.0 mm). The driver DPI scales the image, and it is kept inside the printable width. A failed GDI submit is not retried as raw ESC/POS. That fallback is what produced the blank page.

Drawer kick is still ESC/POS `ESC p`, and only for a queue whose profile is compatible, open, and ready. The Toshiba candidate does not get a pulse during discovery, preview, or the test receipt. Open or closed stays `Not reported`.

Spooler acceptance is reported as: `The printer job was submitted, but physical output has not yet been verified.` A preview does not mark the job submitted. Physical text stays unverified until the paper is read. See `PRINTER-PERMISSION-AND-PHYSICAL-PRINT-VERIFICATION-ACCEPTANCE.md`.

## Diagnostics in Register Settings

The selected queue stays visible with classification, Windows status, driver, port, connection, capabilities, and transport. Actions:

1. Refresh Windows printers.
2. Validate connection.
3. Test receipt rendering. This draws a preview and does not submit a job.
4. Print test receipt. One job at a time. It does not create a sale, a payment, or a drawer pulse.
5. Test drawer kick. Disabled until drawer kick is verified on its own.

The test slip is titled `AXIZPOS PRINTER TEST` and includes the queue, driver, port, paper width, `Text rendering: PASSED`, `Invoice rendering: TEST`, and one sample line. Amounts on that slip are sample column data. Sale receipts still use the saved invoice and the existing tax and currency settings.

Stage `Physical text verified` stays `not_run` in software. Opening the queue does not mark it passed.

## Paper width, PDF, and reprint

The renderer width is `paper_dots` from Register Settings (384 or 576). The GDI page width uses that same raster. PDF download is still the API invoice for the saved sale. Thermal output uses the same `ReceiptDoc` the cashier already printed from. This pass did not add a second tax calculation in the printer service. Historical reprint still passes the stored slip, not a price lookup.

## Automated tests

The tests do not open a Toshiba queue and do not write to a printer.

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

`pnpm exec vitest run src/features/printing/printerSettingsModal.test.tsx src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts --reporter=dot`

3 files, 20 tests, 0 failed, exit 0. Duration 2.63s.

From `apps/desktop/src-tauri`:

`cargo test --offline --lib printer::tests`

16 passed, 0 failed, exit 0.

`cargo test --offline --lib printer`

32 passed, 0 failed, exit 0, 1.21s. That filter also runs `printer_discovery::tests` and `printer_gdi::tests`. No API pytest target applies to this printer path.

Covered in Rust, without Windows hardware:

- Toshiba Native Windows Driver on `Toshiba: 0_USB` is Candidate, USB, no drawer kick, transport `windows-gdi`.
- A RAW datatype does not switch that driver to ESC/POS.
- Epson TM on USB001 stays ESC/POS unless the driver datatype is EMF or XPS.
- PDF and PCL have no receipt transport.
- An unknown USB candidate is not sent raw ESC/POS.
- A blank raster is rejected.
- ESC/POS image bytes come before the cut.
- 58 mm destination width stays narrower than 80 mm.

Covered in the desktop tests:

- The Toshiba warning names the queue and the driver and does not call the printer unsupported.
- Print test receipt stays available. Test drawer kick stays off.
- Save keeps the candidate and says it is not operational.
- The diagnostic slip contains the required lines and a sample item.
- Physical text verification is `not_run` even after a submitted job.

## Native acceptance

| Step | Result |
| --- | --- |
| Toshiba queue present in Windows | NOT RUN. The queue is not installed. |
| AxizPOS classification | Implemented as Candidate. Not observed in the live dropdown. |
| Queue can be opened | NOT RUN |
| Diagnostic preview on this register | NOT RUN in the running app |
| One plain-text test page | NOT RUN. No job was submitted. |
| Visible text on paper | NOT RUN |
| One diagnostic invoice on paper | NOT RUN |
| Disposable sale, reprint, stock and payment reconciliation | NOT RUN |

POS build identity and executable hash were not taken. Nothing was deployed.

## Workstreams

| Workstream | Status |
| --- | --- |
| 1. Toshiba Windows printer discovery | Implemented in code. Live queue absent. |
| 2. Compatibility classification and message | Implemented. Stays Candidate. Not marked verified. |
| 3. Windows queue connectivity | BLOCKED. Queue not installed. |
| 4. Invoice data generation | Existing saved-slip path kept. Empty raster rejected. |
| 5. Printable payload generation | Ink is required before a job is sent. |
| 6. Printer transport | GDI selected for this driver. Not proven on the device. |
| 7. Visible text test receipt | NOT RUN |
| 8. Complete tax invoice on paper | NOT RUN |
| 9. 58 mm and 80 mm | Width mapping tested. Paper not printed. |
| 10. PDF comparison | Same slip model. Not compared on paper. |
| 11. Historical reprint | Still uses the saved slip. Not reprinted on paper. |
| 12. Payment and drawer integrity | Print failure still does not reverse payment. No pulse sent. |

## Remaining limitations

- Physical printing and drawer kick are unverified.
- The Toshiba driver version, default datatype, and USB identity were not readable.
- GDI page length depends on `DocumentProperties`. If the driver ignores a custom length, the text can print and the roll can still feed extra blank paper. That was not observed.
- A candidate is not marked compatible after a spooler accept. Only visible text would do that, and this pass does not set that flag automatically.
- No production register was changed.

## Connection profiles — 25-11-2026

The same renderer and GDI-versus-ESC/POS choice now sit behind connection profiles. USB still uses the Windows queue. Network and Wi-Fi share TCP. Bluetooth Classic is a paired COM port. BLE is refused until a documented GATT service exists. The Toshiba queue is still Candidate. Details are in `docs/hardware/UNIVERSAL-PRINTER-CONNECTIVITY-ACCEPTANCE.md`.
