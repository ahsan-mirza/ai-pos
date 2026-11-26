# AxizPOS universal printer connectivity — acceptance

Date: 26-11-2026

Project status: **PASSED WITH LIMITATIONS**. The universal printer project is not PASSED. MTP-3 was not attached, and no other physical printer was printed. Nothing was deployed. No production invoice was printed.

The engine is the existing desktop printer module. Serial / COM is now a separate connection from Bluetooth Classic. An unknown Windows queue can be set to generic ESC/POS by the cashier. A native Windows driver, including Toshiba Native on `Toshiba: 0_USB`, still uses GDI when ESC/POS is requested.

## Workstreams

| Workstream | Status |
| --- | --- |
| 1. Unified Printer Manager | PASSED WITH LIMITATIONS. Adapter selection is in `printer_profile.rs`. Bytes still go out through `printer.rs`. |
| 2. Windows printer and driver support | PASSED WITH LIMITATIONS. Spooler and GDI tests passed. Physical output NOT RUN. |
| 3. Generic USB transport | PASSED WITH LIMITATIONS. USB stays on the Windows queue. The USB device is not claimed. Physical output NOT RUN. |
| 4. Generic ESC/POS | PASSED WITH LIMITATIONS. Explicit ESC/POS is covered by tests. It is refused for rendered, text-only, and office queues. Physical output NOT RUN. |
| 5. LAN printing | PASSED WITH LIMITATIONS. Typed host and port, default 9100. An open socket stays Candidate. Physical output NOT RUN. |
| 6. Wi-Fi printing | PASSED WITH LIMITATIONS. Same TCP adapter as LAN. Wi-Fi is a label, not a radio scan. Physical output NOT RUN. |
| 7. Bluetooth Classic | PASSED WITH LIMITATIONS. Paired `BthModem` COM ports can be selected. Physical output NOT RUN. |
| 8. BLE printing | BLOCKED. No documented GATT service is registered, so no characteristic is written. Physical output NOT RUN. |
| 9. Serial / COM | PASSED WITH LIMITATIONS. A non-Bluetooth COM port can be saved and would be opened only for a test or a receipt. Baud is not changed. Physical output NOT RUN. |
| 10. Vendor-specific extension | BLOCKED. `VendorSdkTransport` refuses the job. The protocol list is empty. |
| 11. Automatic discovery | PASSED WITH LIMITATIONS. One compatible Windows printer can be suggested. Several wait. A missing name is kept. An office queue is not substituted. |
| 12. Capability verification | PASSED WITH LIMITATIONS. Print, cutter, and drawer are separate, and paper stays `not-verified`. |
| 13. MTP-3 blank or faint output | BLOCKED for paper. The blank-raster rejection and the Toshiba GDI path remain. The text `AXIZPOS UNIVERSAL PRINTER TEST` was not printed. |
| 14. Live preview inside Register Settings only | PASSED WITH LIMITATIONS. Checkout confirmation tests still omit the settings preview. |
| 15. Print-job reliability | PASSED WITH LIMITATIONS. The job row stores id, invoice, printer, connection, protocol, transport, payload type, size, status, one attempt, and `physical-not-verified`. It is not replayed. |
| 16. Cash drawer independence | PASSED WITH LIMITATIONS. Serial, Bluetooth, BLE, preview, discovery, save, and the test receipt do not kick. Open or closed is not sensed. |
| 17. Security and permissions | PASSED WITH LIMITATIONS. Settings writes without register permission are refused. The network is not scanned. BLE and vendor adapters send nothing. |
| 18. Representative hardware acceptance | NOT RUN. |

## Hardware matrix

| Category | Connection | Protocol | Result |
| --- | --- | --- | --- |
| Generic ESC/POS thermal | USB | ESC/POS | NOT RUN |
| Toshiba MTP-3 | USB | ESC/POS | NOT RUN. The label profile is unverified. |
| Another manufacturer's thermal printer | Windows / USB | Manufacturer driver | NOT RUN. Toshiba Native remains a GDI candidate in software. |
| Generic Ethernet receipt printer | LAN | ESC/POS where the cashier selected it | NOT RUN |
| Wi-Fi receipt printer | Wi-Fi | Same TCP adapter | NOT RUN |
| Bluetooth Classic receipt printer | Bluetooth | SPP / serial where Windows exposes it | NOT RUN |
| BLE receipt printer | Bluetooth LE | Documented GATT profile | NOT RUN. No profile is registered. |
| Standard office printer | Windows | Windows driver rendering | NOT RUN. Office and virtual queues are unsupported for receipts. |
| Serial receipt printer | COM | ESC/POS | NOT RUN |

No model, driver version, firmware, executable SHA-256, or photograph was recorded, because no device was printed.

## Commands

From `apps/desktop/src-tauri`:

`cargo test --offline --lib printer -- --test-threads=8`

39 passed, 0 failed, exit 0.

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

`pnpm exec eslint` on the changed printer UI files. Exit 0.

`pnpm exec vitest run src/features/printing/printerConnections.test.ts src/features/printing/settingsPreview.test.tsx src/features/printing/printerSettingsModal.test.tsx src/features/checkout/receiptConfirmation.test.tsx src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts --reporter=dot`

6 files, 41 tests, 0 failed, exit 0.

No API suite was run. Invoice tax calculation was not changed. Unit tests do not open a printer, socket, or Bluetooth radio.
