# Independent cash drawer connection

Date: 26-11-2026

Status: **BLOCKED** for a physical kick. **PASSED WITH LIMITATIONS** for the software gate.

No photograph of a USB, serial, or network drawer controller was supplied. No verified controller command is installed. AxizPOS will not pretend an RJ11/RJ12 drawer is a USB device.

## What the software does

| Check | Result |
| --- | --- |
| Separate connection does not call the receipt printer | PASS, `drawer_manager` tests |
| USB with no verified controller sends no pulse | PASS |
| Serial COM shape is checked and then refused | PASS |
| Invalid network address is refused without a socket | PASS |
| Empty network address does not scan the network | PASS |
| Vendor path sends no pulse | PASS |
| Printer-driven profile on the separate path is refused | PASS |
| Second kick inside 3 seconds is refused | PASS |
| Cash policy allows a separate drawer when the printer transport is None | PASS, `printPolicy.test.ts` |
| Test drawer kick stays off for a separate connection | PASS, `cashDrawer.test.ts` |
| Status bar does not copy the printer light | PASS, `deviceStatus.test.ts` |

## Physical matrix

| Setup | Result |
| --- | --- |
| A. MTP-3 printer drawer port | Not kicked in this pass. The port is labelled DC12V/1A. A 12V profile can be selected only after the voltage is confirmed. Physical open was not observed |
| B. No printer, independent USB controller | BLOCKED. No supported controller was identified |
| C. Toshiba POS Printer (CR) plus a separate controller | BLOCKED for the controller. Printer and drawer settings are stored separately |
| D. Windows office printer plus a separate controller | BLOCKED for the controller. An office queue still does not become a kick circuit |
| E. RJ11 drawer and no controller | BLOCKED, and the screen says a compatible controller is required |

## Automated evidence

- `cargo test --offline --lib drawer_manager` — 5 passed, exit 0
- `cargo test --offline --lib cash_drawer::` — 3 passed, exit 0
- `cargo test --offline --lib printer::tests` — 18 passed, exit 0
- `pnpm exec vitest run` on the drawer, policy, status, settings, and receipt confirmation tests — 5 files, 38 passed, exit 0
- `pnpm exec tsc -p tsconfig.json --noEmit` in `apps/desktop` — exit 0

No API suite was required. The drawer decision is local to the register.
