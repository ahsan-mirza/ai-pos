# AxizPOS printer protocol and compatibility registry

Date: 26-11-2026

A new printer is added by a protocol adapter, a profile, capability mapping, and tests. Checkout, tax, invoice identity, the cart, and cash payment do not change. A documented standard stays on the generic adapter. A manufacturer adapter is only for a documented difference.

## Languages

| Language | Status | Where it is used |
| --- | --- | --- |
| ESC/POS | Implemented for text raster (`GS v 0`), feed, cut, and the drawer pulse `ESC p` | Known receipt drivers, a typed network address, Bluetooth Classic, Serial / COM, and an unknown model only after the cashier selects it |
| Windows driver rendering | Implemented | Native Windows drivers, text-only drivers, EMF, XPS, and unknown queues that were not switched to ESC/POS |
| ZPL | Not implemented | Not sent |
| CPCL | Not implemented | Not sent |
| TSPL | Not implemented | Not sent |
| Vendor SDK command set | Not implemented | `documented_vendor_protocols()` is empty |

ESC/POS is not assumed to include every command. Cutter and drawer stay `not-verified` until a device proves them. QR and barcode commands are not claimed for every ESC/POS printer. The shared receipt renderer still draws the slip, including a QR when the slip itself contains one, and the thermal path sends that drawing as a raster.

## Generic profiles

| Profile | How it is chosen | Verified |
| --- | --- | --- |
| `generic-escpos` | Cashier selects ESC/POS on a candidate that is not a rendered, text-only, or office driver. Also the language for network, Bluetooth Classic, and Serial / COM. | No |
| `windows-driver` | Default for an unknown Windows queue, and the only path for a native Windows or text-only driver | No |
| MTP-3 label | Model text contains `MTP-3` or `MTP3` | No. 80 mm, 576 dots, ESC/POS, 90 mm/s, cashbox DC 12V / 1A. Connection and drawer stay unknown. |

Known receipt driver names (Epson, Star, Bixolon, and the other names in `printer_discovery.rs`) still select ESC/POS automatically. That list is a hint for drivers that already speak ESC/POS. It is not a list of every supported printer, and it does not mark paper output verified. An unknown model does not need to be added to that list to use generic ESC/POS.

## Adding a printer

1. Prefer `generic-escpos` or `windows-driver` when the device follows one of those.
2. Add a vendor protocol only with a documented command set. Put the id in `documented_vendor_protocols()`.
3. For BLE, add the real service UUID, write characteristic, packet size, and acknowledgement to the GATT list. Do not invent a UUID.
4. Add an adapter test that does not open hardware.
5. Print on that model and record the evidence before calling it verified.

## Manual setup

When Windows does not report a useful model, the cashier can:

- pick the Windows queue and, for an eligible candidate, choose Windows driver or ESC/POS
- type a host, with an optional port
- pick a paired Bluetooth COM port
- pick or type a non-Bluetooth COM port

Save does not print and does not kick the drawer. Verification stays Candidate until paper is read. This build has no screen for density, speed, or code page, because those commands are not registered.
