# Universal printer connectivity — acceptance

Date: 25-11-2026

Software status: **PASSED WITH LIMITATIONS**. No transport is marked physically passed. Nothing was deployed.

On 25-11-2026 the installed queues were Generic / Text Only on COM4, Microsoft Print to PDF, and OneNote. None is MTP-3. The MTP-3 label was not applied. Generic / Text Only stays a Windows-rendered candidate, not raw ESC/POS. Physical output remains NOT RUN.

The cashier picks a connection in Register Settings → Printer & Drawer. The live receipt preview stays on that page. After payment, Yes prints the saved invoice and No skips it. A failed print does not reverse the payment.

## Transport results

| Transport | Software | Physical |
| --- | --- | --- |
| USB | PASSED WITH LIMITATIONS. USB queues stay on the Windows spooler. A non-USB port cannot be saved as USB. | NOT RUN. MTP-3 was not attached. |
| Windows spooler | PASSED WITH LIMITATIONS. Discovery, GDI versus ESC/POS, and the Toshiba candidate path are covered by tests. | NOT RUN. `Toshiba POS Printer (CR)` is not installed on this PC. |
| LAN | PASSED WITH LIMITATIONS. User-entered host and port, default 9100. An open socket stays Candidate. | NOT RUN. |
| Wi-Fi | PASSED WITH LIMITATIONS. Same TCP adapter as LAN. The link type is a label, not a radio scan. | NOT RUN. |
| Bluetooth Classic | PASSED WITH LIMITATIONS. Paired `BthModem` COM ports can be selected. The port is opened with an 8-second write timeout. A normal serial port is ignored. | NOT RUN. No paired receipt printer was printed. |
| Bluetooth BLE | BLOCKED. No documented GATT printing service is registered, so no characteristic is written. | NOT RUN. |
| Vendor adapter | BLOCKED. The vendor-protocol list is empty. | NOT RUN. |

## What was verified in tests

- One verified Windows printer can still be selected by the existing discovery policy. Several verified printers wait. A missing name is kept. An unrelated queue is not substituted.
- MTP-3 label: 80 mm, ESC/POS, 90 mm/s, cashbox DC 12V/1A. Connection is unknown. Drawer and verification stay false.
- Empty rasters are rejected. ESC/POS image bytes precede feed and cut. GDI is still selected for Toshiba Native.
- TCP `192.168.1.20` becomes port 9100. `host:9101` is kept. Opening a port is not verification.
- Bluetooth `COM5` is stored for this register. `COM0` is rejected. Drawer kick is refused for Classic and BLE.
- A second in-flight job is refused. A retry does not create a sale or kick the drawer. Job rows record `accepted-unverified` or `failed`, with `physical-not-verified`.
- The settings preview is still absent from the checkout confirmation.

## Commands

From `apps/desktop/src-tauri`:

`cargo test --offline --lib printer -- --test-threads=8`

38 passed, 0 failed, exit 0. Duration 2.08s.

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

`pnpm exec vitest run src/features/printing/printerConnections.test.ts src/features/printing/settingsPreview.test.tsx src/features/printing/printerSettingsModal.test.tsx src/features/checkout/receiptConfirmation.test.tsx src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts --reporter=dot`

6 files, 41 tests, 0 failed, exit 0. Duration 2.15s.

No API invoice suite was run. Invoice tax calculation was not changed. Unit tests do not open a printer, socket, or Bluetooth radio.

## Devices

| Device | Result |
| --- | --- |
| MTP-3, 80 mm, ESC/POS | NOT RUN. The label is a profile only. USB, Wi-Fi, and Bluetooth were not observed on the hardware. |
| Toshiba POS Printer (CR), Toshiba Native Windows Driver, `Toshiba: 0_USB` | NOT RUN. Still Candidate. GDI is selected. Raw ESC/POS is not sent. |
| Network ESC/POS printer | NOT RUN. |
| Bluetooth Classic printer | NOT RUN. |
| BLE receipt printer | NOT RUN. No GATT service is implemented. |

No photograph, executable hash, or paper comparison was produced.

## Limitations

- USB is not a raw USB protocol. Windows keeps the device.
- Wi-Fi is not discovered separately from a typed IP address. The network is not scanned.
- Bluetooth Classic depends on a Windows RFCOMM COM port. AxizPOS does not pair the radio.
- BLE printing is unavailable until a documented service and characteristic are added. A generic characteristic is not assumed.
- A successful spooler write or socket write is not paper proof.
- Drawer open or closed is not sensed. Bluetooth and BLE never kick. The MTP-3 cashbox rating is electrical information, not a verified kick.
- This build was not deployed.
