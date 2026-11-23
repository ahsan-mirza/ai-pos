# Settings conflict and offline policy

Status: **IN PROGRESS**

Date: 23-11-2026

## Scopes

| Scope | Examples | Who edits |
|---|---|---|
| Platform | Forced modules, plan modules, console mail | Super Admin |
| Tenant | Currency, VAT, till policy, receipt branding, legal name | Business Pro, and POS only where a section is already editable |
| Branch | Store address and phone on receipts, staff at a branch | Existing store and staff APIs |
| Register | Activation, sync queue, local theme | That register |
| Terminal device | Windows printer queue, drawer kick wiring | That machine |
| User | Catalogue view preference | That user, with its own revision |

A register must not overwrite a tenant value with a device value. A branch address must not replace the tenant legal name.

## Offline classes

| Class | Current behavior |
|---|---|
| Local device | Printer and drawer save on the machine. They do not enter the tenant settings row. |
| Local preference | Theme and catalogue view can change on the device. Catalogue view already has its own revision. |
| Online tenant policy | Tax, finance, modules, and security policy are not edited from an offline register. POS shows the last accepted snapshot. |
| Shared and already editable | Currency save needs the API. It is not queued as an offline settings change. |

An offline register keeps the last fetched currency, tax, profile, and receipt JSON. It does not invent a newer `updated_at`.

## Conflicts

Two editors of the same tenant setting are not given a merge screen in this pass. The desktop settings fetch keeps a newer cached `entitlement_revision` when an older poll arrives for the same tenant. That prevents an old response from rolling the module set backward. It does not show both values and ask the cashier to pick one.

Financial, tax, and security settings must not switch to last-write-wins. That work is still open.

## Pending sync

There is no "Pending Sync" badge on shared settings, because POS does not queue shared tax or finance edits while offline. Local printer changes are saved immediately on the device and are not a tenant sync item.
