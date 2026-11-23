# Register settings save

Date: 23-11-2026

Status: **PASSED WITH LIMITATIONS**

Save was failing after the settings had already been written. A virtual Windows queue can now be stored as a diagnostic preference, and the other register preferences persist with it. On the isolated window, OneNote `(Desktop) - Protected`, 58 mm paper, and 2 copies survived reopening the modal and a restart. Network (LAN) and None were not clicked on that window. No receipt was printed and no drawer kick was sent.

## Root cause

`PrinterSettingsModal.save` wrote the row, then called `probePrinter()` for every Windows selection. Anything other than `Receipt printer connected successfully.` was treated as a failed save: the error stayed on the form, `onSaved` did not run, and the button became clickable again. OneNote is virtual, so the probe returns `This device is not verified as a supported receipt printer.` Save could not finish for that queue. The probe also refreshed discovery, which could rewrite the row the user had just saved.

The click handler, the Tauri argument names, and the SQLite table were already aligned. Both sides use `paper_dots`, `drawer_kick`, `auto_discover`, and the other snake_case fields on `printer_settings`.

## Save path

1. The modal validates the mode, the address or queue name, and copies (1, 2, or 3). An invalid value keeps the modal open and does not write.
2. `save_printer_settings` checks `devices:manage` or `settings:manage`, then `printer::save` updates the single register row.
3. A successful write records `REGISTER_SETTINGS` / `register.printer_settings` with the previous and new values. A rejected save returns before that audit row.
4. The modal builds the message from the saved row. It probes only a Windows queue that is ready, compatible, and openable, and only to upgrade the message to the connected sentence. A probe failure does not undo the save and does not kick the drawer.
5. The page notice is set and the modal closes only after that write returns. Reopening loads the same row.

A virtual or unsupported queue is stored as the selected preference and is not reported as a connected receipt printer. Test print and Test drawer kick stay disabled. `plan_drawer_kick` refuses a virtual or unsupported queue, including OneNote. None mode clears the operational address into `previous_address` so the old queue is not used. Network (LAN) keeps the host and port and does not go through a Windows queue. An explicit missing queue is no longer replaced by automatic discovery.

The success text for a virtual queue is: `Register settings saved. The selected Windows queue is a virtual printer and cannot be used for receipt printing or drawer control.`

## Native evidence

Same executable, identifier, and data directory as `docs/orders/ORDER-TAG-AUTO-GENERATION-ACCEPTANCE.md`.

| Item | Value |
| --- | --- |
| Executable | `D:\Work\ai-pos\acceptance\ordertags\target\debug\ai-pos-desktop.exe` |
| Identifier | `com.axizpos.ordertags.acceptance` |
| SHA-256 | `4E1603CC4F790D6EFB9405B5512FBD69843502309EC7D23F6146FD2962675091` |
| Size | 31,714,304 bytes |

After Save, and again after the process was restarted, the register row was:

| Field | Value |
| --- | --- |
| transport | `windows` |
| address | `OneNote (Desktop) - Protected` |
| paper_dots | 384 (58 mm) |
| copies | 2 |
| auto_discover | 1 |
| user_selected | 1 |
| drawer_kick | 1 (the existing default; the kick was not sent) |
| saved_driver | Microsoft Virtual Print Class Driver |

The audit event was `register.printer_settings` / `REGISTER_SETTINGS`, outcome `saved`, from Tag Owner on register `TG1`. `printer_status` had no kick timestamp.

The reopened modal, including after restart, showed Windows printer, the OneNote queue, the badge `Virtual printer`, and `This device is not verified as a supported receipt printer.` The pressed paper control was `58 mm` and the copies control was `2`. Screenshot: `docs/orders/evidence/settings-after-restart.png`.

The card sale used Card and then `No, Skip` on the receipt prompt. That path does not ask for a drawer kick.

## Tests

Rust `printer::tests`: 13 passed. That run includes copies outside 1–3 being rejected, a TCP address round-trip, `999.1.1.1` leaving the previous address in place, None clearing the operational address, and the OneNote name saved with 58 mm paper.

`printer_discovery`: the single compatible printer is still selected when the user has not chosen one. An explicit missing name is not replaced. OneNote, PDF, and other virtual queues are not auto-selected as the receipt printer.

Desktop vitest, 4 files, 23 tests, 0 failed. The modal test covers the virtual-queue save message, a disabled Save while a save is in progress, and Save hidden from a user without permission.

## Limitations

- Network (LAN) and None were not clicked on this window. Those branches passed in the Rust save test.
- This PC has no compatible receipt printer. Physical printing and a drawer pulse were not attempted. The saved OneNote queue is not an operational receipt printer.
- The exact success sentence was not photographed. The reopened modal and the SQLite row are the persistence evidence.
- A cashier session was not opened on this window. The Save button is disabled without `devices:manage` or `settings:manage`, and the Rust command checks the same permission before it writes.
- `drawer_kick` stayed at its default of on. The virtual queue cannot carry a kick, and no kick row was written.
