# AxizPOS universal printer architecture

Date: 26-11-2026

Status: **PASSED WITH LIMITATIONS**. This is one printer engine. Checkout, tax, and payment code were not given a second print path. No transport was proven on paper in this pass. Nothing was deployed.

## Flow

`Saved invoice snapshot → shared receipt renderer → Printer Manager → capability check → printer profile → transport adapter → printer`

The React register does not open a device. It calls the existing Tauri printer commands. `apps/desktop/src-tauri/src/printer.rs` still sends the bytes. `printer_profile.rs` chooses the adapter. `printer_discovery.rs` classifies a Windows queue. `printer_gdi.rs` draws a Windows page.

## Adapters

| Adapter | What it does in this build |
| --- | --- |
| `WindowsSpoolerTransport` | Raw bytes through `OpenPrinterW` / `WritePrinter` for a known ESC/POS profile. |
| `WindowsDriverRenderTransport` | The same queue, rendered with GDI. Used for native Windows drivers, text-only drivers, EMF, and XPS. |
| `UsbRawTransport` | A USB queue stays on the Windows spooler. AxizPOS does not claim the USB device. |
| `NetworkTcpTransport` | User-entered host and port. Port 9100 is the default. Also the network-printer adapter. |
| `BluetoothClassicTransport` | A Windows Bluetooth modem exposed as a COM port after the user pairs in Windows. |
| `SerialComTransport` | A COM port that is not a Bluetooth modem. Baud, parity, data bits, and stop bits stay as Windows set them. |
| `BluetoothBleTransport` | Registered, and it refuses the job. No GATT printing service is documented here. |
| `VendorSdkTransport` | Registered, and it refuses the job. The vendor-protocol list is empty. |

An open TCP port, a visible queue, or a COM name is not a verified printer.

## Protocols

Supported languages are ESC/POS and Windows driver rendering.

ZPL, CPCL, and TSPL are not implemented. They are not sent as ESC/POS.

A known receipt driver uses ESC/POS unless the driver reports EMF or XPS. An unknown model stays on Windows rendering until the cashier explicitly chooses generic ESC/POS. That choice is refused for a native Windows driver, a Toshiba port monitor, a text-only driver, and an office or virtual queue. The MTP-3 label records 576 dots, ESC/POS, and 90 mm/s. It does not force those values onto every 80 mm printer, and it does not mark the device verified.

## Capabilities

Printing, cutting, and the cash drawer are separate. A missing cutter or an unverified drawer does not block a receipt. Software never stores `verified` from the client, and it never reports that paper came out because the spooler or socket accepted the job.

## Jobs

Each user-requested print stores a job id, invoice id, printer id, connection, protocol, transport, payload type, payload size, time, status, one attempt, the native error, and `physical-not-verified`. A second job cannot be sent while one is in flight. A retry does not create a sale, move stock, or kick the drawer. An accepted job is not sent again automatically, because the paper may already be out. The row remains after restart. It is not replayed.

## Settings

Configuration stays on POS Settings → System & Register → Printer & Drawer. The choices are Windows printer, USB, Network / Wi-Fi, Bluetooth, Serial / COM, and None. The live sample is only on that page. Checkout still asks Print or Skip after the payment is saved. A failed print does not reverse the payment.

Saving settings requires `pos:access`, `devices:manage`, or `settings:manage`. Viewing status does not. A direct `save_printer_settings` call from a session without those permissions is refused and audited. Sale printing stays available to the signed-in cashier so a saved invoice can still be printed.

## What this build does not do

- It does not scan the network at startup.
- It does not pair Bluetooth.
- It does not write a BLE characteristic.
- It does not load a manufacturer SDK.
- It does not change COM baud or send a drawer pulse during discovery, preview, save, or the test receipt.
- It does not show density or speed controls. No documented software command for those is registered.
- It does not treat the MTP-3 cashbox rating as proof that a drawer opened.
