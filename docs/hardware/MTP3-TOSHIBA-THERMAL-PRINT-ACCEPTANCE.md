# MTP-3 and Toshiba thermal print — acceptance

Date: 26-11-2026

Status: **NOT PASSED**. Paper was not printed in the 26-11-2026 position pass. The cause and the software change are in `MTP3-PRINT-POSITION-AND-PRINT-QUALITY-FIX.md`. The earlier blank-page analysis is in `BLANK-RECEIPT-PRINTING-ROOT-CAUSE-AND-FIX.md`. This file does not mark MTP-3 compatible with every printer.

## Label

| Item | Value |
| --- | --- |
| Model | MTP-3 |
| Width | 80 mm, 576 dots |
| Speed on the label | 90 mm/s |
| Language on the label | ESC/POS |
| Power | DC 12V / 1A |
| Cashbox output | DC 12V / 1A |

The label does not say USB, Wi-Fi, or Bluetooth. The software profile keeps connection, drawer, and verification false.

## Windows queue seen earlier

| Item | Value |
| --- | --- |
| Queue | Toshiba POS Printer (CR) |
| Driver | Toshiba Native Windows Driver |
| Port | Toshiba: 0_USB |

That driver stays a Candidate. Raw ESC/POS is not sent to it, including when generic ESC/POS is requested. The receipt is rendered with GDI. This queue was not installed on the development PC during this pass.

## This pass

| Check | Result |
| --- | --- |
| Printer discovered | NOT RUN. The queue is not installed. |
| Queue opened | NOT RUN |
| Profile identified | UNVERIFIED. The label profile is not a verified device. |
| Diagnostic text `AXIZPOS UNIVERSAL PRINTER TEST` | NOT RUN |
| Columns, numbers, and a sample amount | NOT RUN |
| Complete invoice | NOT RUN |
| Physical text | NOT RUN |
| Drawer pulse | NOT RUN. No pulse is sent for this candidate. |

No photograph, firmware, driver version, or executable hash was taken.

## Position pass, 26-11-2026

The reported slip had the sample line near the bottom, a blank sheet above it, and faint characters. The renderer already had ink. The GDI path was splitting that image across forms and could shrink it when the driver reported a width in the wrong DPI. It now sends one page, bottom-up, at the top of a page the same height as the raster. No darkness command was added. The Toshiba driver still does not receive raw ESC/POS.

| Check | Result |
| --- | --- |
| Hardware self-test | NOT RUN. This PC has no Toshiba queue. |
| Text diagnostic | NOT RUN on paper. The payload is covered by `printer::tests`. |
| Raster sample | NOT RUN on paper. |
| Disposable invoice against the preview | NOT RUN |
| Drawer | NOT RUN. The sample still does not kick. |
