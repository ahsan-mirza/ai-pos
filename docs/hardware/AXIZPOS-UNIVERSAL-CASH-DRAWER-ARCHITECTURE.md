# AxizPOS universal cash drawer architecture

Date: 26-11-2026

Status: **PASSED WITH LIMITATIONS**

The cash drawer is no longer assumed to hang off the receipt printer. A register can use a printer drawer port, a separate controller, both devices, or neither. This build kicks only a verified printer drawer port. Separate controllers are configurable and are not pulsed.

No production deploy was made.

## Path

`Cash drawer service → Drawer manager → Connection adapter → Verified controller → Physical drawer`

The manager lives in `apps/desktop/src-tauri/src/drawer_manager.rs`. React asks the existing `open_cash_drawer` command. It does not talk to a port.

| Connection | Adapter | What is sent |
| --- | --- | --- |
| Through receipt printer | Printer kick port | The existing ESC/POS pulse, after the profile voltage matches the confirmed drawer-port voltage and the queue has a verified kick profile |
| Separate device | USB, serial, network, or vendor | Nothing. No verified command is registered |
| None | None | Nothing. Printer settings are left alone |

`PrinterKickPortAdapter` is the existing `plan_drawer_kick` path. It still refuses a text-only driver, a raw COM port, an unknown printer profile, a voltage mismatch, a missing queue, and a second kick inside 3 seconds. TCP writes keep the existing 8-second write timeout.

`UsbCashDrawerControllerAdapter`, `SerialCashDrawerAdapter`, `NetworkCashDrawerControllerAdapter`, and `VendorCashDrawerAdapter` share `plan_separate`. Each one checks its address shape and then looks for a verified protocol. The verified list is empty. A standard RJ11/RJ12 drawer is reported as needing a controller. No USB bytes, COM open, or network packet is sent during discovery, Save, preview, or a test click.

A printer-driven profile, including HP VB400-BL1616 and the 12V and 24V ESC/POS ports, cannot be kicked on the separate path.

## Register settings

`Printer & Drawer` stores, in the local SQLite `printer_settings` row:

- `drawer_connection`: `printer`, `separate`, or `none`. An empty value still means printer, so older registers keep their kick.
- `drawer_controller_kind`, `drawer_controller_address`, `drawer_controller_protocol` for a separate device.

Save does not pulse. Test drawer kick stays disabled unless the printer path is verified. A separate controller can be saved while its command remains blocked.

Receipt printing does not read the drawer connection. Drawer status does not copy the printer light when the connection is separate or none.

## Payment

Cash still kicks once, after the sale is recorded or queued, when the cash-drawer policy is on. Card, failed, and cancelled sales do not. A replay does not kick again. Test receipt and print retry do not kick.

A separate connection is eligible even when the receipt printer is None. The native command then refuses the pulse and records the reason. The sale stays recorded. Connection `none` does not call the kick.

Open/closed stays **Not reported**. No profile has a sensor.

## Permissions and offline

Register management permission still guards settings changes and the manual test. The configuration is local. A kick does not wait for the cloud API.

## What was not built

No Toshiba-only or HP-only driver was added. No vendor SDK was linked. No pulse timing was invented for an unknown interface.
