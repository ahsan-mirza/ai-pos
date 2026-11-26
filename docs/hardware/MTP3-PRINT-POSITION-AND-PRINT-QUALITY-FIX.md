# MTP-3 print position and print quality

Date: 26-11-2026

Status: **NOT PASSED**. Software rendering and the Windows job shape were changed and tested. The MTP-3 was not on this PC, so paper, power, and the print head were not checked. Nothing was deployed.

## What the slip showed

The report for `20261126_220937.jpg` was: most of the paper blank, `SAMPLE RECEIPT — NOT A SALE` readable near the bottom, other characters extremely faint, and the body not at the top. That file was not in the workspace, so this note uses that description and the sample receipt the test button sends.

The sample line is the header and, when the store has no footer of its own, the footer as well. A footer-only mark at the bottom of a long blank sheet is a positioning and page-break failure. It is not evidence that the renderer drew only that line. The preview that produced 9,472 ink bytes at 576 dots already had a non-blank image.

## Software cause

The installed queue is Toshiba Native Windows Driver on `Toshiba: 0_USB`, datatype RAW. That driver still gets a GDI page. Raw ESC/POS is not sent to it, because a RAW job on this driver is accepted by the spooler and then discarded.

Three GDI choices dropped or shrank the body:

1. A short `VERTRES` split the raster into several `StartPage` calls. On a roll, each call is another form. The last fragment is the footer, after blank paper.
2. A top-down bitmap (`biHeight` negative) was tried first. A driver can return success and still keep only the last rows.
3. `DocumentProperties` could put back a long default page after the receipt length was set, and a printable width reported in the wrong DPI could scale a 72 mm image down until only the largest line stayed readable.

The page is now one form, the same height as the raster, drawn bottom-up from the top-left. The receipt length and 203 dpi are written again after the driver merge. A reported width that is much narrower than the raster is not used to shrink it. A 512-dot image stays 512 dots; 576 is not forced onto every 80 mm job.

No thermal-density command was added. The MTP-3 manuals that were found do not give a safe darkness value for this queue, and a darker setting would not put the missing lines back.

## ESC/POS payload

For a queue that does take raw ESC/POS, the raster is still `ESC @`, then `GS v 0` bands of at most 128 rows, then `ESC d 4` and `GS V 66`. There is no feed before the image. A text diagnostic is `ESC @`, left align, `ESC 3 30`, the ASCII lines, then the same feed and cut. It contains no `ESC p` and no vendor command.

`WritePrinter` must accept the full byte count. A short write is reported with the Windows error code and is classed as a spooler failure. Opening the queue is not treated as a successful print.

## Hardware, separate from the code

`Get-Printer` on this PC listed Generic / Text Only on `COM4:`, OneNote, and Microsoft Print to PDF. `Toshiba POS Printer (CR)` was not installed. No bytes were sent. The self-test was not run.

Two manuals published as MTP-3 disagree, so neither sequence is treated as verified for this unit:

- GOOJPRT-style sheet (80 mm paper, about 72 mm print width, 203 dpi, ESC/POS, 12 V): power off, paper loaded, hold FEED, press POWER, release when printing starts.
- The other sheet (indicator lights or an OLED menu): hold POWER and FEED together, or open the menu and choose printing self test.

If that self-test is faint or has missing columns, the paper direction, paper grade, head contact, and the 12 V / 1 A supply come before any further software change. The label's 90 mm/s was not written into the driver.

## Tests

| Command | Result |
| --- | --- |
| `cargo test --offline --lib printer::tests` | 21 passed, 0 failed, exit 0 |
| `cargo test --offline --lib -- destination_keeps black_bits escpos_graphics paper_width` | 4 passed, 0 failed, exit 0 |
| `cargo check --release --offline` | exit 0, no warnings |
| `pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` | exit 0 |
| `pnpm exec vitest run` on the three printing tests | 3 files, 19 passed, exit 0 |

No API test builds this thermal payload. The returns receipt suite was not run.

Covered without hardware: header, item, and footer bytes stay in that order; the raster is not truncated; there is no leading feed; the text diagnostic keeps every line and does not kick the drawer; a 512-dot row is not rewritten to 576; a short spooler write, a timeout, a disconnect, a blank raster, and a malformed image are different failure classes. Physical quality stays `not_run`.

## Still required on the MTP-3

1. Run the self-test that matches this unit's own manual.
2. Print the text diagnostic and the sample raster.
3. Compare one disposable invoice with Receipt Preview.
4. Photograph those three slips.

Do not mark this passed from the unit tests alone.
