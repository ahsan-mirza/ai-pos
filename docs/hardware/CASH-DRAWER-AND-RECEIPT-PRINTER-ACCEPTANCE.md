# Cash drawer and receipt printer

Date: 23-11-2026

## Register settings save

Save no longer treats an unverified Windows queue as a failed write. The settings row is stored first. A probe runs only for a ready, compatible, openable queue, and only to confirm the connected message. OneNote `(Desktop) - Protected` is kept as a virtual preference. It is not a connected receipt printer and it cannot kick the drawer.

The isolated walk and the hash are in `docs/hardware/REGISTER-SETTINGS-SAVE-ACCEPTANCE.md`. Status for that pass: **PASSED WITH LIMITATIONS**. No drawer pulse was sent. `printer_status` on that register had no kick timestamp.

## Earlier pass — Windows printer dropdown

Date: 22-11-2026

| Check | Result |
| --- | --- |
| Manual queue name replaced by a dropdown | PASS in the desktop source |
| Search, refresh, and persisted selection | PASS in frontend tests |
| Spooler mapping, status, and open validation | PASS in Rust tests, Windows APIs mocked |
| Native dropdown on a new acceptance window | NOT PASSED |
| Physical drawer kick | NOT TESTED |

Register Settings no longer has a text field for the Windows queue. Windows printer mode shows `Select Windows printer`, a searchable list, and a Refresh button beside it. The menu uses the existing select and is portaled, so the modal does not clip it.

The new acceptance executable started and stopped on Activate this register. Register Settings was not opened. This pass does not claim the dropdown showed the printers installed on this PC. No drawer kick was sent. The already-open release register was not used.

## Dropdown behavior

Each installed queue shows its exact Windows name, the driver, the manufacturer when `GetPrinterDriverW` returns one, the port and connection, and one status word:

| Status word | Meaning |
| --- | --- |
| Ready | Online and classified as a compatible receipt printer |
| Candidate | Online, but the driver is not a verified receipt profile. It can be chosen. Drawer kick stays off. |
| Unsupported | An office driver that is not virtual. It can be chosen and is not described as a receipt printer. |
| Virtual printer | PDF, OneNote, AnyDesk, or another virtual port. It cannot enable Test print or Test drawer kick. |
| Offline | Installed, and Windows reports offline or work-offline |
| Unavailable | Error, paper out, pending deletion, or `OpenPrinterW` failed |
| Not installed | The saved name is no longer in the Windows list |

Refresh shows `Discovering Windows printers...`, then `Found N Windows printers` with the real count. Duplicate names are collapsed. The previous selection is kept when that queue is still installed. If it is gone, the saved name stays selected and the modal says: `The previously configured printer is not installed. Select an available printer to reconnect.` Another queue is not substituted.

No queues: `No Windows printers were found. Connect or install a printer and refresh the list.`

An offline queue: `This printer is installed but currently offline.`

A candidate, unsupported, or virtual queue: `This device is not verified as a supported receipt printer.`

Save persists the exact queue name, driver, port, manufacturer, and the object GUID when `GetPrinterW` level 7 returns one. The modal refuses a name that is neither an installed queue nor the name already stored for this register. `Receipt printer connected successfully.` is shown only after the native open of a compatible queue succeeds.

Network (LAN) still uses the IP field. None still has no printer selector. In None, the cash-drawer checkbox and the drawer connector are disabled. Paper width, print-after-sale, copies, Test print, Cancel, and Save remain.

## Discovery source

One enumeration, `enumerate_windows_printers` in `apps/desktop/src-tauri/src/printer.rs`.

The dropdown calls `EnumPrintersW` (local and connections, level 2). For each distinct queue it calls `OpenPrinterW`, `GetPrinterDriverW` level 6, and `GetPrinterW` level 7, then closes the handle. Nothing is written to the printer.

Probe, background discovery, and receipt printing use the same enumeration without opening every queue. The selected queue is opened with the existing `OpenPrinterW` probe. Compatibility still comes from the driver and port in `printer_discovery::classify`. The queue name and the Windows default printer do not make a device a receipt printer.

The cash drawer follows the saved receipt printer. There is no second Windows printer picker for the drawer. Selecting, refreshing, or saving does not send a kick. Test drawer kick stays off unless the queue is open, ready, classified as a compatible receipt printer, and the kick interval allows it. Open or closed stays `Not reported`.

## Tests for this pass

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0. The acceptance frontend build ran the same check before Vite.

`pnpm exec vitest run src/features/printing/printerSettingsModal.test.tsx src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts --reporter=dot`

3 files, 18 tests, 0 failed, exit 0. Duration 1.32s.

Those tests cover a discovered list, search by queue name, selecting the exact name, refresh without a duplicate or a silent replacement, a missing saved printer, an empty list, the loading sentence, offline and virtual status, saving an installed name, reopening with that name, Test print disabled when the queue is unavailable, Test drawer kick disabled for an offline or virtual printer, and Network (LAN) and None left unchanged.

From `apps/desktop/src-tauri`:

`cargo test --offline --lib printer::tests`

13 passed, 0 failed, exit 0, 0.49s.

The mapping test builds spooler rows in memory and does not call Windows. It checks Ready, Offline, work-offline, a failed open, a candidate, a virtual PDF, an empty name, duplicate names, and a refused drawer kick. The other tests cover a missing queue, no silent replacement, one pulse, the repeat gap, and saving the queue name, driver, port, and identity. Two Windows tests still call `EnumPrintersW` only. They do not open a queue and do not write to a printer.

## Native acceptance for this pass

| Item | Value |
| --- | --- |
| Executable | `D:\Work\ai-pos\acceptance\printer-dropdown\target\debug\ai-pos-desktop.exe` |
| Product | AxizPOS Printer Acceptance |
| Identifier | `com.axizpos.printer.acceptance` |
| Config | `apps/desktop/src-tauri/tauri.printer-acceptance.conf.json` |
| Build | `pnpm exec tauri build --debug --no-bundle --no-sign`, exit 0 |

The window title was `AxizPOS Printer Acceptance`. It opened on Activate this register. A store code, activation key, and demo connection file were not entered. Register Settings was not reached, so search, refresh, save, and the cash-drawer association were not clicked. No screenshot of the dropdown was taken. The window was closed. No kick was sent.

## Earlier software pass

| Check | Result |
| --- | --- |
| Automatic printer discovery | PASS |
| Automatic printer connection | PASS as policy. This PC had no compatible receipt printer, so none was auto-selected. |
| Drawer association | PASS in software |
| POS Settings visibility | PASS on the offline acceptance window below |
| Physical drawer kick | BLOCKED |
| Physical drawer-open sensor | NOT SUPPORTED |

| Item | Value |
| --- | --- |
| Executable | `D:\Work\ai-pos\acceptance\offline\target\release\ai-pos-desktop.exe` |
| Product | AxizPOS Offline Acceptance |
| Identifier | `com.axizpos.offline.acceptance` |
| Data directory | `C:\Users\ahsan\AppData\Roaming\com.axizpos.offline.acceptance` |
| Size | 21,962,752 bytes |
| SHA-256 | `09684BAC46E29F895130FA34CF4E7FD852F07ABD4BE6F70D2E38169CE0B88B1A` |
| Built | 22-11-2026 19:43 |

That window wrote `acceptance-diagnostics.json` with guard `passed` and used only that data directory. The Laundry register and `com.aipos.desktop` were not opened. It was closed after the settings check. That executable does not contain this dropdown.

Windows queues present during that pass:

| Queue | Driver | Port | Classification |
| --- | --- | --- | --- |
| OneNote (Desktop) | Send to Microsoft OneNote 16 Driver | nul: | Unsupported, virtual |
| OneNote (Desktop) - Protected | Microsoft Virtual Print Class Driver | OneNote virtual port | Unsupported, virtual |
| Microsoft Print to PDF | Microsoft Print To PDF | PORTPROMPT: | Unsupported, virtual |
| iR-ADV C3525 | Canon Office XPS Class Driver | WSD | Unsupported, network, offline |
| Canon Generic PCL6 Driver | Canon Generic PCL6 Driver | 10.10.101.250 | Unsupported, network |
| AnyDesk Printer | AnyDesk v4 Printer Driver | AD_Port | Unsupported, virtual |

None of these is a known receipt-printer profile. None was selected. `Toshiba thermal` remains a saved name from an older register database, not a hardcoded printer, and it was not installed.

## Selection policy

One register database holds one hardware configuration. The receipt printer and the cash drawer share it.

- One available compatible printer, and no saved printer that is still installed: select it, persist the queue, driver, and port, and associate the drawer. Discovery does not pulse the drawer.
- More than one available compatible printer: keep the saved name and ask for a choice.
- No available compatible printer: keep the saved name, including a missing `Toshiba thermal`, and do not adopt an office or virtual queue.
- The saved queue is installed again: keep it.
- The saved queue is gone and exactly one available queue has the same saved driver and port: restore that queue. Two queues with the same driver and port are not chosen automatically.
- A manually chosen installed printer is not replaced while it remains installed.
- A TCP address is left as a manual network printer.

`FindFirstPrinterChangeNotification` watches the local print server. On a change, discovery runs again and the register emits `printer-hardware-change`. The watch holds the server handle, not a handle per queue. A missing queue is not opened in a loop.

## Drawer association

The path is AxizPOS, the selected Windows receipt printer, that printer's drawer-kick port, then the cash drawer. There is no separate printer name for the drawer and no direct USB drawer mode.

Drawer kick is allowed only when the selected queue is open, ready, and its profile supports the kick. The command remains ESC/POS `ESC p`, pin 2 or pin 5, default 50 ms on and 500 ms off. The spooler write times out after 8 seconds. A second kick within 3 seconds is refused. A receipt printed inside that window still prints and does not add a second pulse.

A successful spooler write is recorded as "Drawer command submitted." Open/closed state stays "Not reported." Cash payments still kick only after the sale is recorded or queued, the tender includes cash, and `drawer_kick` is on. Card, failed, cancelled, and replayed sales do not request a kick.

## Settings and status bar

Settings → Printer & drawer is one section, "Receipt Printer & Cash Drawer." It shows the selected queue, driver, port, connection, and last communication. The drawer card shows that same printer, drawer-kick support, the last attempt, the last error, and open/closed state. Opening the page does not pulse the drawer.

The status bar shows Printer and Drawer separately. Green means the queue is ready, or that drawer-kick control is available. Amber on the drawer means a kick command was submitted and the physical state is still unknown. Green does not mean the drawer opened.

## Persistence

`printer_settings` stores the queue name, driver, port, model or manufacturer, previous queue name, whether the cashier chose it, automatic discovery, and `saved_identity` when Windows returned an object GUID. Printer handles are not stored. A missing saved name is kept until the cashier chooses an installed queue or discovery finds exactly one compatible printer.

## Earlier test run

`cargo test --offline --lib printer` previously reported 22 passed, 0 failed, including classification and the live enumeration. `pnpm exec vitest run src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts src/features/settings/settingsRoutes.test.ts` previously reported 3 files, 10 tests, 0 failed. Those counts are from the pass before the dropdown. The counts in "Tests for this pass" are the ones run after the dropdown.

## Limitations

- The printer-acceptance window was not activated, so the dropdown was not confirmed against the live spooler.
- No installed queue on this PC is a known receipt-printer profile, so a live auto-connect of a receipt printer was not available.
- The drawer cable and kick port were not verified. No pulse was sent.
- The register cannot read whether the drawer is open or closed.
- This build was not installed over a production or Laundry register.
