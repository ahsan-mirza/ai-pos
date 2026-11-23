# POS settings information architecture

The gear in the outer POS sidebar opens `#/settings`. That page is the overview. Each section is `#/settings/{id}`. The outer sidebar, language switch, theme switch, icon-only Open drawer button, and bottom status bar stay outside this workspace.

## Two groups

Business settings describe how the business operates. System and register settings describe this terminal.

| Section | Group | Scope | Edited on the register |
|---|---|---|---|
| Business profile | Business | Business-wide | No. Shows legal name, country, location, store code, and business type. |
| Finance and currency | Business | Business-wide | Yes, for a business-wide administrator, through `PUT /api/v1/settings/currency`. |
| Tax and invoicing | Business | Branch | No. Shows VAT registration and whether prices include VAT. |
| Sales and POS rules | Business | Business-wide | No. Shows the return window from `pos_policy`. |
| Products and inventory | Business | Business-wide | No. The note follows the active profile. |
| Customers and loyalty | Business | Business-wide | No. Loyalty is mentioned only when that module is on. |
| Staff and permissions | Business | Branch | Yes, when the signed-in user can manage staff. Hidden otherwise. |
| Modules and add-ons | Business | Business-wide | No. Lists enabled modules. |
| Workflows and operations | Business | Business-wide | No. |
| Laundry services, workflows, stations, machines, quality, tags | Business | Business or branch | No. Laundry profile only. Reads `/api/v1/laundry/settings` and `/api/v1/laundry/production/workflows` where those calls already exist. |
| Integrations | Business | Business-wide | No. Secrets are not shown. |
| Notifications | Business | Business-wide | No. |
| Audit trail | Business | Business-wide | No. Shows `updated_at` and `updated_by_name` from the business-settings row. A missing timestamp stays the empty state. The event list stays on the Business Pro audit page. |
| Register and terminal | System | Register | No edit. Shows branch, register code, and activation. |
| Hardware and peripherals | System | Register | Printer and scale settings already saved on this register. |
| Connectivity and offline | System | Register | Read-only status from the open page. |
| Security and session | System | Register | Lock stays in the outer sidebar. No token is issued here. |
| Appearance and language | System | Register | Accent, theme, and density save on this register. Language stays in the top navbar. |
| Keyboard and shortcuts | System | Register | The touch keyboard stays on the bottom bar. Shortcuts are not editable. |
| Sync and local data | System | Register | Read-only. No reset or force-sync. |
| Updates and downloads | System | Register | Shows the app version. Does not download an installer. |
| Diagnostics and logs | System | Register | Says whether business settings loaded. No secrets. |

A Business Pro page is labelled "Managed in Business Pro". A register page is labelled "Register-specific". Currency is labelled "Business-wide".

## Old routes

| Old hash | Now |
|---|---|
| `#/settings` | Overview |
| `#/settings/currency`, `#/settings/currencies` | Finance and currency |
| `#/settings/branch-tax`, `#/settings/vat` | Tax and invoicing |
| `#/settings/receipts` | Hardware and peripherals |
| `#/settings/till-rules` | Sales and POS rules |
| `#/settings/appearance` | Appearance and language |
| `#/settings/business-profile`, `#/settings/stores` | Business profile |
| `#/settings/module-settings`, `#/settings/module-setup`, `#/settings/addons`, `#/settings/addon-access` | Modules and add-ons |
| `#/settings/roles` | Staff and permissions |
| `#/settings/registers` | Register and terminal |
| `#/settings/downloads` | Updates and downloads |
| `#/settings/audit` | Audit trail |
| `#/settings/laundry-floor` | Laundry workflows |
| `#/laundry/settings` | Short pointer on the floor. The categories live under `#/settings/laundry-*`. |

## Profile differences

Grocery, electronics, fashion, and restaurant use the same list without the laundry pages. Laundry adds services, workflows, stations, machines, quality, and tags. Those pages are omitted for the other profiles. Retail checkout settings are not added to the laundry list beyond the shared business pages.

## What is not persisted from this screen

Logo, hours, tax edits, till-rule edits, catalogue edits, loyalty rules, add-on purchases, integrations, notification policy, the full audit trail, shortcut editing, and installer downloads have no POS write API in this workspace. They are explained as read-only. A save is not simulated.
