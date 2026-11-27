# Manual and sale drawer kick consistency

Date: 27-11-2026

Verdict: PASSED WITH LIMITATIONS.

Nothing was deployed. The MTP-3 and its drawer were not on this PC, so no pulse was sent and physical open or closed was not observed.

## Root cause

Cash sales and Test Drawer Kick both call `plan_drawer_kick`, then send the same `ESC p` pulse. The test stopped earlier. A Windows queue was treated as able to kick only when the driver name matched a manufacturer list such as Epson or Xprinter. MTP-3 / POS-80 is not on that list, so the test returned `This printer has no known drawer-kick profile` before the saved profile and voltage were compared.

The reported setup was **ESC/POS printer drawer port (24V)** with the confirmed port at **12V**. The MTP-3 cashbox label is **DC12V/1A**. That pair is a mismatch. The old message hid it.

A cash-sale kick that failed this check was swallowed by the checkout caller. A drawer that opened while a receipt printed was not proof that this pulse was sent. Many printers also move the DK port when they cut the receipt. This change does not treat that as a verified kick.

## Shared planner

`plan_drawer_kick` is the only planner for a cash-sale kick and for Test Drawer Kick. Both use the saved register settings: printer queue, transport, protocol, drawer profile, voltage, and connector.

A manufacturer name is no longer required when all of these are true:

- Drawer connection is through the receipt printer.
- The profile is a documented ESC/POS DK profile (`escpos-dk-12v`, `escpos-dk-24v`, or the 24V HP drawer profile).
- The confirmed drawer-port voltage equals that profile.
- The queue is open, not virtual, not text-only, and not a Windows-only driver.
- Printing language is ESC/POS, or the driver is already a known ESC/POS receipt driver.

A 24V profile with a 12V confirmation is refused on both paths: `12V and 24V are not interchangeable`. The voltage is not changed automatically, and no pulse is sent to discover it. Text-only, COM, PDF, and Toshiba Native Windows drivers still receive no raw pulse. Serial and Bluetooth stay unverified. The 3-second gap still blocks a second pulse. A sample or test receipt does not kick. Card, failed, and cancelled payments kick only when “open for card and other payments” is on.

For this MTP-3, the matching software choice is **ESC/POS printer drawer port (12V)**, confirmed voltage **12V**, and printing language **ESC/POS**. That is the printer port rating. It does not prove the attached drawer is a 12V drawer. If the drawer is 24V, do not connect it to this port.

## Tests

Rust, from `apps/desktop/src-tauri`:

`cargo test --lib printer:: -- --test-threads=8`

Result: 22 passed. Exit code 0. Includes the generic ESC/POS 12V pulse, the 24V-profile/12V-port refusal, and the no-pulse result when ESC/POS was not selected.

Desktop Vitest: cash drawer, printer settings modal, printer connections, device status, and print policy — 24 passed. `tsc -p tsconfig.json --noEmit` exit code 0.

## Not run

- Physical Test Drawer Kick on the MTP-3.
- A cash sale on that drawer after the 12V profile is selected.
- Confirmation that the drawer solenoid is 12V.
