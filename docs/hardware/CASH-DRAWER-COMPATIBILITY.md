# Cash drawer compatibility

Date: 26-11-2026

AxizPOS opens a cash drawer only through a saved profile whose voltage and interface match the connected hardware. The register UI does not address a drawer model directly. Each register stores its own profile in the local database, so two registers can use different drawers.

A successful command means the bytes were handed to the printer or port. It does not mean the drawer moved. Open/closed stays **Not reported** unless a real sensor is read. No profile in this list has a sensor.

The HP Standard Duty Cash Drawer, model **VB400-BL1616**, assembly **661672-001**, spare **661843-001**, is a **24V** printer-driven drawer. Its drawer connector is RJ45. An Epson receipt printer needs an RJ12-to-RJ45 cable. The 24V pulse is produced by the printer drawer-kick circuit, not by this PC. Connecting that drawer to a 12V port is refused. Generic / Text Only and a raw COM port are refused, because they do not supply that circuit.

Physical opening of a VB400-BL1616 was **not** confirmed on this machine. The row below is **Supported by driver** from the HP cash-drawer user guide (printer-driven, 24V only). It is not marked Tested.

The register now stores a drawer connection separately from the receipt printer: through the receipt printer, a separate controller, or none. A separate USB, serial, network, or vendor controller is not kicked in this build, because no verified command is installed. An RJ11/RJ12 drawer is not treated as a PC USB device. The MTP-3 drawer output is labelled DC12V/1A, so it is not a match for the 24V HP drawer. See `AXIZPOS-UNIVERSAL-CASH-DRAWER-ARCHITECTURE.md`.

## Matrix

| Device or connection | Status | What AxizPOS will send |
| --- | --- | --- |
| HP VB400-BL1616 on a 24V ESC/POS receipt-printer DK port (RJ45, or RJ12-to-RJ45) | Supported by driver | ESC/POS pulse, connector pin 2, only after the cashier confirms 24V |
| HP VB400-BL1616 on a 12V port, a text-only driver, or a COM port | Not supported | No pulse |
| Other 24V RJ11/RJ12 printer-driven drawers on a confirmed 24V ESC/POS DK port | Supported by driver | ESC/POS pulse, pin 2 or pin 5 as saved |
| Other 12V RJ11/RJ12 printer-driven drawers on a confirmed 12V ESC/POS DK port | Supported by driver | ESC/POS pulse. A 24V setting is refused |
| 12V drawer on a 24V port, or 24V drawer on a 12V port | Not supported | No pulse |
| Direct USB drawer | Not supported | No pulse. No verified USB driver or vendor SDK is installed |
| Serial / COM drawer | Not supported | No pulse. No verified serial command is configured |
| OPOS cash drawer | Not supported | No pulse. No OPOS service is installed |
| USB or serial trigger adapter | Requires adapter | No pulse until a verified adapter command exists |
| Proprietary drawers not listed here | Not supported | No pulse |

## Register behavior

- A cash tender opens the drawer after the sale is recorded or queued, when "Open the cash drawer for cash payments" is on and the profile matches.
- Card and other tenders do not open it unless "Open the cash drawer for card and other payments" is explicitly on.
- Manual Test drawer uses the signed-in cashier session. A second kick inside three seconds is refused, and checkout will not send a second kick for the same payment.
- Test print does not kick. Test drawer does not print a receipt.
- The kick uses the local Windows spooler or the configured network printer. It does not wait for the server, so an offline register can still open a drawer that is attached to this PC.
- A missing printer, an offline queue, a virtual printer, and a driver without a drawer-kick profile each return their own message and send nothing.

## What was exercised

Rust tests cover the HP 24V pulse, the 12V/24V refusal, a text-only COM refusal, and empty USB, serial, OPOS, and adapter profiles. Frontend tests cover the same voltage gate and the cash versus non-cash checkout rule. No drawer was attached to the machine that ran these tests.
