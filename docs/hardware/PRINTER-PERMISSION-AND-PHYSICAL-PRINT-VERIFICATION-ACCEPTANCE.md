# Printer permission and physical print verification

Date: 25-11-2026

Nothing was deployed. No sale, payment, inventory movement, or drawer pulse was created.

| Workstream | Result |
| --- | --- |
| Register management permission | PASSED WITH LIMITATIONS |
| Printer profile and transport | PASSED WITH LIMITATIONS |
| Print job submission | NOT RUN |
| Physical receipt text | NOT RUN |

The printer issue is not PASSED. Physical text was not confirmed on paper.

## Permission

Viewing printer status stays open to a signed-in cashier. Changing the saved printer, paper width, transport, drawer settings, or sending a test receipt requires an existing permission: `devices:manage` or `settings:manage`. `devices:manage` is the register-management permission already used for registers. `settings:manage` is the business-settings permission. No new permission id was added. Cashiers are not granted either permission by this change.

A refused save does not write `printer_settings`. The denial is appended to the register audit ledger as `register.printer_settings` with outcome `denied`.

`devices:manage` is already part of the seeded Super Admin permission set. Sign-in does not rewrite roles. A request session cannot run that sync, and doing so returned HTTP 500 on unlock. Opening Printer & Drawer while online re-reads `/api/v1/auth/me` and replaces the unlocked permission list. An offline unlock keeps the last saved list.

The read-only sentence is: `You can view printer status. Register management permission is required to change printer settings.`

This was not confirmed by unlocking the live Bayrut Super Admin and saving a printer. The software path is covered by the desktop permission checks and the Rust denial test.

## Printer found on this PC

`Get-Printer` / `Win32_Printer` on 25-11-2026:

| Queue | Driver | Port | Driver DPI | Work offline |
| --- | --- | --- | --- | --- |
| Generic / Text Only | Generic / Text Only | COM4: | 600 × 600 | false |
| Microsoft Print to PDF | Microsoft Print To PDF | PORTPROMPT: | 600 × 600 | false |
| OneNote (Desktop) - Protected | Microsoft Virtual Print Class Driver | OneNote virtual port | 600 × 600 | false |

No queue name, driver, or port identifies MTP-3. The MTP-3 label (80 mm, 90 mm/s, ESC/POS, DC 12V/1A) is not applied. PDF and OneNote stay unsupported. Generic / Text Only stays a candidate: it is not a known ESC/POS profile, so the transport is Windows-rendered graphics, not raw ESC/POS. The drawer is not marked operational from the 12V/1A label.

Profile identified stays Unverified until a physical test confirms the method. A preview and a spooler accept do not change that.

## 576-dot width

The shared receipt renderer uses 576 printable dots for 80 mm and 384 for 58 mm. That is the ESC/POS printable width at about 203 dpi, not the 600 dpi reported by the Windows drivers above. The preview and a later print job both pass the same `paper_dots` value into that renderer. This PC's installed drivers do not report a 576-dot thermal head.

## Receipt payload

The diagnostic slip is still the shared renderer. It is titled `AXIZPOS PRINTER TEST`, names the printer, paper width, and `Text rendering: TEST`, and includes one sample line with quantity, unit price, tax, and total. `Protocol: ESC/POS` is printed only when the selected queue is a compatible ESC/POS profile. The slip is not a sale. Preview still reports ink bytes and width and does not submit a job. Print job submitted stays Not run until a job is sent. Physical text verified stays Not run after a spooler accept.

Print test receipt asks for confirmation first. The confirmation says the test does not create a sale or open the cash drawer. One confirmed test would save the authorized selection and submit one job with the drawer kick off. That button was not used.

## Messages

| Situation | Sentence |
| --- | --- |
| Permission missing | You can view printer status. Register management permission is required to change printer settings. |
| Profile unverified | Printer detected, but its receipt-printing profile has not been verified. Complete the printer test before using it for customer receipts. |
| Test submitted | Test receipt submitted. Please confirm that readable text printed correctly. |
| Queue cannot open | Windows found the printer, but AxizPOS could not open its queue. |
| Job refused | Receipt content was generated, but the printer did not accept the print job. |
| Spooler accepted | The printer job was submitted, but physical output has not yet been verified. |

A Toshiba Native driver still uses its own candidate sentence. An unsupported queue still uses the unsupported-method sentence.

## Checkout

Payment is still saved before the print question. Yes prints the saved invoice. No skips it. The settings preview is not opened. A print failure does not reverse the payment. The test path does not kick the drawer.

## Tests

No unit test opens a Windows printer port.

| Command | Result |
| --- | --- |
| `pnpm exec tsc --noEmit --pretty false` in `apps/desktop` | Exit 0 |
| `pnpm exec vitest run src/features/printing/printerSettingsModal.test.tsx src/features/printing/printerConnections.test.ts src/components/shell/deviceStatus.test.ts src/components/RegisterErrorBoundary.test.tsx` | 4 files, 23 tests, 0 failed, exit 0 |
| `cargo test --offline --lib printer` in `apps/desktop/src-tauri` | 39 passed, 0 failed, 63 filtered out, exit 0 |

API pytest was not run. The earlier API environment failed to import `phonenumbers`.

## Remaining

Physical text verification is NOT RUN. Print job submission on the connected hardware is NOT RUN. Restart persistence of a newly saved queue was not exercised on a disposable register. The live Super Admin session was not used to save a printer.
