# Universal printer connectivity — audit

Date: 25-11-2026

This audit describes the printer path before the connection profiles were added, and the architecture those profiles use. It does not claim that every thermal printer works.

## What already existed

There is one receipt path:

`Saved invoice → renderReceipt (shared template) → print_raster → Windows spooler or TCP`

Settings live in the register SQLite table `printer_settings`, one row per register. There is no second printer database.

| Piece | Behavior before this change |
| --- | --- |
| Windows discovery | `EnumPrintersW` lists local and connection queues. Classification uses driver and port, not the queue name. |
| Open and write | `OpenPrinterW` / `WritePrinter` for raw ESC/POS. Toshiba Native and a `Toshiba:` port use GDI (`StretchDIBits`) instead. |
| Network | Transport `tcp`. Address is an IPv4 host or hostname, with an optional port. The default port is 9100. A connect was treated as ready. |
| USB | Only as a Windows port (`USB001`, `Toshiba: 0_USB`). No direct USB claim. |
| Bluetooth | Not implemented. |
| BLE | Not implemented. |
| Vendor languages | No adapter. Unknown real printers use GDI. Office and virtual queues are unsupported. |
| Preview | Register Settings only. Checkout asks Yes or No and does not open the preview. |
| Drawer | ESC/POS pulse for a verified Windows profile, or for TCP. 8-second submit timeout. 3-second gap. Open/closed stays Not reported. |
| Jobs | One in-flight print (`PRINTING`). No job row. A spooler accept was already not treated as paper proof. |

## Gaps

- One Windows queue and one TCP address could not describe USB, Wi-Fi, and Bluetooth as separate choices.
- An open TCP port was reported as ready.
- A raw USB or raw Bluetooth write would have taken the device away from Windows, or bypassed pairing.
- BLE has no standard ESC/POS GATT service in this codebase.
- No model-name allowlist should decide the language. The MTP-3 label is evidence for a test profile only.

## Architecture after this change

`Receipt renderer → print_raster → printer profile → transport adapter → device`

| Adapter | When it is used | What it does |
| --- | --- | --- |
| WindowsSpoolerTransport | Windows printer | Existing spooler. ESC/POS or GDI from the driver and port. |
| UsbRawTransport | USB | Same spooler. The USB device stays owned by Windows. The name is the extension point. It does not open the USB interface directly. |
| NetworkTcpTransport | Network and Wi-Fi | One TCP socket. The user types the address. Port 9100 is the default. No network scan. |
| BluetoothClassicTransport | Paired RFCOMM COM port | Windows `CreateFile` on `COMn` after Windows has created a Bluetooth serial port. Pairing stays in Windows. |
| BluetoothBleTransport | BLE | Refuses the job. The documented GATT registry is empty. |
| VendorPrinterTransport | Documented vendor language | The registry is empty. Unknown languages are not sent ESC/POS by this adapter. |

A client cannot store verification as `verified`. An open port, a paired radio, and the MTP-3 label stay `candidate`.

Checkout, the live preview, and the cash-payment kick policy for Windows and TCP are unchanged. Bluetooth and BLE do not kick the drawer.
