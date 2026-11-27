# MTP-3 blank receipt — root cause and fix

Date: 27-11-2026

Status: **NOT PASSED**. The passthrough job printed a blank page. The receipt path is Windows graphics again, one short band per page. Paper has not been checked since that change. Nothing was deployed.

## Follow-up, 27-11-2026 — blank page after passthrough

The till is `Toshiba POS Printer (CR)`, driver `Toshiba Native Windows Driver`, port `Toshiba: 0_USB`, transport `windows-gdi`. The preview has ink (12,454 ink bytes, 576 dots wide). Rendering a test does not send a job. Printing did.

The previous GDI job left `SAMPLE RECEIPT — NOT A SALE` on the paper. That line is the last graphic. Sending the same receipt as `PASSTHROUGH` (escape 19) inside an empty driver page removed that ink. The driver accepted the escape and put nothing on the paper. Raw ESC/POS is not the transport this driver prints.

The receipt path no longer sends that escape. It draws the shared raster as GDI graphics. Each band is at most 32 rows, under 64 KB, and it is the only blit on a page sized to that band, starting at the top. The 40 mm page floor is not used for a band. A sample still does not kick the drawer. Checkout has no MTP-3-only branch.

The installer with this path is `dist\POS-Setup-0.1.5.exe`, SHA-256 `47D5F8B3B59157B12BD6FF198FBDE6BBE69D244928D45CC57F02CA17764591A6`. `dist\ai-pos-desktop.exe` is SHA-256 `3DB9BC28C3C3F529F00AF933B49E32A25D62500EC7AF99307D9CD017EEBC842D` and contains `one blit per page`. It has not been printed on the Toshiba queue from this PC. `cargo test --offline --lib printer` passed 51 tests.

## Why the previous implementation failed

The 26-11-2026 change drew the receipt as one bottom-up `StretchDIBits` on one page. The 27-11-2026 change split that same bitmap into strips of at most 24 source rows, still with `StretchDIBits`, still on one page. Both changes stay on the Windows GDI bitmap path.

The executable that printed with the strip change, and that does not contain the passthrough path, was:

- `dist\ai-pos-desktop.exe` SHA-256 `FF59AFF1160D269A3DB20D1059FE7D48472B0E08B824B753F4871D4A54C76900` (22,573,568 bytes). It contains `strips of at most` and does not contain `Windows PASSTHROUGH`.
- Installer SHA-256 `647F29C491B1054B2D96D7D0006DA2133DA83BEDE61AC2F9B2FF89A01314DC61`.

No `ai-pos-desktop` process was running on this PC, so that hash is the built file, not a hash taken from a live till process.

`20261127_210623.jpg` is still a long white slip. `SAMPLE RECEIPT — NOT A SALE` is readable near the bottom and the body is missing. That sentence is the last line of the sample (the header, and the footer when the store has no footer of its own). A driver that keeps only the last `StretchDIBits` call produces that slip even after the bitmap is cut into 24-row strips: every strip is submitted, and only the footer strip remains. Splitting the image did not change the transport.

`Toshiba Native Windows Driver` is classified as Windows GDI even when the saved protocol says ESC/POS and the queue datatype is RAW. A RAW `WritePrinter` job on that driver is accepted by the spooler and then discarded. The configured transport was not the transport that painted the slip. The slip matches the GDI bitmap path that the hashed executable actually contains.

The shared receipt renderer already draws the store name, items, VAT, and totals. The Settings preview of the same document shows those lines. They were in the raster. They were not the rows that remained on the paper.

Darkness and voltage were not changed.

## Actual root cause

The Windows receipt path painted the shared raster with `StretchDIBits`. On the photographed slip only the last graphic remained. The missing body is rows the driver did not keep, not an empty payload and not a blank raster. An all-white raster is rejected before a feed or a cut, and the footer line is visible, so the job was not empty.

## A/B/C diagnostic matrix

The required queue is `Toshiba POS Printer (CR)`. `Get-Printer` on this PC on 27-11-2026 listed only:

| Queue | Driver | Port | Datatype |
| --- | --- | --- | --- |
| Generic / Text Only | Generic / Text Only | COM4: | RAW |
| Microsoft Print to PDF | Microsoft Print To PDF | PORTPROMPT: | RAW |
| OneNote (Desktop) - Protected | Microsoft Virtual Print Class Driver | OneNote virtual port | RAW |

No Toshiba queue is installed. No thermal printer is connected. No bytes were sent to a printer. No photograph of test A, B, or C was taken.

| Test | Payload | Physical result |
| --- | --- | --- |
| A. Windows driver text: business name, several lines, numbers, AED 10.00 | Not sent. The queue does not exist. | Not run |
| B. Minimal RAW ESC/POS text: `ESC @`, ASCII lines, ending marker `END-TEXT`, no raster, no `ESC p` | Built in `escpos_text_receipt` and checked by unit test. Not sent. | Not run |
| C. RAW `GS v 0` raster of a known bitmap | Built in `escpos_raster`, framed by `passthrough_frames`, checked by unit test. Not sent. | Not run |
| Complete sample receipt | Not sent | Not run |
| Disposable tax invoice | Not sent | Not run |

The diagnosis rules cannot be closed. A was not observed, so paper, power, the print head, and the driver are not cleared. The software path that matches the photograph is the GDI bitmap. The corrected Windows path no longer depends on `StretchDIBits` for a receipt that has text.

## Corrected transport and payload

Windows GDI queues, including Toshiba Native Windows Driver, now send one job:

1. Build the shared `escpos_raster` payload. `ESC @` is first. `GS v 0` bands are at most 128 rows. There is no `ESC d` or `ESC J` before the image. The feed is `ESC d 4` and the cut is `GS V 66` after the image. A sample document does not include `ESC p`.
2. Open the driver DC and ask `QUERYESCSUPPORT` for escape 19 (`PASSTHROUGH`).
3. On one `StartDoc` and one `StartPage`, send that payload with `ExtEscape`. Each frame is a little-endian WORD length plus at most 16 KB of the same bytes, in order. `ESC @` is not repeated between frames. The driver page is short so it does not add the long blank feed the tall DIB page produced.
4. If the driver reports the escape unsupported, or the first escape accepts nothing, send one GDI `TextOut` of `receiptPlainText` and do not send the bitmap as well. A kitchen ticket with no plain text is the only case that still uses the strip bitmap, and only after the escape is refused.
5. Raw ESC/POS queues still use `WritePrinter` with datatype RAW. A short write is a spooler failure. The accepted count is the `WritePrinter` count, and it is left empty when `WritePrinter` was not used.

There is one transport per profile. Checkout has no MTP-3-only branch. 58 mm stays 384 dots and 80 mm stays 576 dots. Those widths were not measured on this printer.

Each job record stores the executable SHA-256, queue, driver, port, transport, payload type, image width and height, black-pixel count, bytes per row, raster bytes, text bytes, the ESC/POS command summary, the expected size, the `WritePrinter` accepted count when that call ran, the Windows error, the spooler job id, and the result. A malformed or all-white raster is rejected before submission. The ink span must show marks before the cut; the header and item rows are in that raster, not only in the preview.

## Test commands and results

| Command | Result |
| --- | --- |
| `cargo test --offline --lib printer` from `apps/desktop/src-tauri` | 50 passed, 0 failed |
| `pnpm exec vitest run` on the four printing tests from `apps/desktop` | 4 files, 21 passed |
| `pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` | exit 0 |

Covered without hardware: passthrough frames restore the original bytes in order and stay within 16 KB; a text diagnostic contains `AED 10.00` and `END-TEXT`, has no raster command, and has no drawer pulse; a raster payload keeps `GS v 0` before the cut; header, item, and footer marks stay in order with no leading feed; a blank raster is rejected; 58 mm stays narrower than 80 mm; a sample does not kick the drawer; a second send is refused while one is in progress.

## Photographs

No successful output was photographed. The only physical sample is the failing slip `20261127_210623.jpg`. Tests A, B, C, the sample receipt, and a tax invoice were not printed.

## Executable

| File | SHA-256 | What it contains |
| --- | --- | --- |
| Previous `ai-pos-desktop.exe` | `FF59AFF1160D269A3DB20D1059FE7D48472B0E08B824B753F4871D4A54C76900` | Strip GDI only. This is the build that matches the blank slip. |
| Previous `POS-Setup-0.1.5.exe` | `647F29C491B1054B2D96D7D0006DA2133DA83BEDE61AC2F9B2FF89A01314DC61` | Installer of that strip build. |
| Current `dist\ai-pos-desktop.exe` | `A491CC0B36AFF48AEFCC74540705BE25462C63758FD4BC8F8B22D71CE10B49DB` | Contains `Windows PASSTHROUGH` and the strip fallback. 22,580,224 bytes. Not yet run against the printer. |
| Current `dist\POS-Setup-0.1.5.exe` | `2026CDEB50B09753AF5CFCF2BE18F0D40984BB6BC1847AFF37CBB39F48742EEF` | Unsigned installer of the passthrough build. 7,043,307 bytes. Not installed on the till from this PC. |

## Remaining limitations

- Paper output is not accepted. Do not treat the unit tests as a pass.
- `Toshiba POS Printer (CR)` was not present, so the driver's `PASSTHROUGH` support was not queried and Tests A, B, and C were not printed.
- 576 dots was not measured on the MTP-3 head.
- A driver that accepts the escape and still drops the bytes will not be visible until the next print on that queue. The text fallback runs only when the escape is refused.
- Darkness and voltage were left unchanged.
- Nothing was deployed.
