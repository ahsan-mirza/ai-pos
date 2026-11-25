# Settings parity audit

Status of the whole settings program: **IN PROGRESS**

Date: 23-11-2026

This inventory is from the current POS settings rail, Business Pro navigation, Super Admin settings, and the `business_settings` row. A matching label is not treated as synchronization.

The canonical tenant row is `business_settings` (`apps/api/app/models/business_settings.py`). Its revision is `cache_generation`, exposed as `entitlement_revision`. There is no second settings database.

## Mandatory matrix

| Setting section | POS | Business Pro | Super Admin policy | Owner/scope | Sync direction | Test status |
|---|---|---|---|---|---|---|
| Overview | Reads the cached business snapshot and this terminal's activation. | General settings plus stores, registers, and subscription screens. | Tenant drawer shows entitlement fetch time. | Mixed. Identity is tenant. Activation is register. | POS reads the API snapshot. No dedicated overview write. | Audited. Not cross-tested. |
| Business | A business-wide user with `settings:manage` can save legal name, Arabic legal name, country, and location. Store code and business type stay read-only. | The same identity fields on Business identity, plus the existing business-type screen. | Does not own the tenant legal name. | Tenant. One `business_settings` row. | Both write `PUT /api/v1/settings/identity`. A stale revision is rejected. | Automated API proof. Live two-register walk not run. |
| Finance | Currency can be saved by a business-wide user with `settings:manage`. | Business currency and extra currencies. | No tenant currency override. | Tenant. `business_settings.currency`. | Both can write through `PUT /api/v1/settings/currency` when permitted. POS native cache refreshes on the next settings fetch. | Audited. Not cross-tested. |
| Tax & invoices | Read-only VAT, TRN, inclusive flag. | Branch tax, VAT, receipt layout. | No tenant tax rate editor. | Tenant tax on `business_settings`. Receipt branding on `receipt` JSON. Branch contact on the store. | Business Pro writes. POS prints from the cached receipt profile. Historical invoices are not rewritten. | Audited. Not cross-tested. |
| Sales rules | Read-only return window from `pos_policy`. | Till rules and returns policy. | None. | Tenant. `business_settings.pos_policy`. | Business Pro writes `settings.pos_policy`. POS uses the cached policy at checkout. | Audited. Not cross-tested. |
| Products | Read-only catalogue note. | Product screens, not a second settings table. | None. | Tenant catalogue plus branch stock. | Existing catalogue sync. Not a new settings channel. | Audited. Not cross-tested. |
| Customers | Read-only loyalty flag. | Customer records and credit live on customer APIs. | None. | Tenant customers. Loyalty JSON is tenant settings. | Customer sync is separate from this settings page. | Audited. Not cross-tested. |
| Staff & access | This register can edit staff when the existing staff permission allows it. | Roles page. | Seat and entitlement counts. | Branch staff, tenant roles. | Existing O7 staff provisioning. Not reworked. | Audited. Not cross-tested. |
| Modules | Lists enabled module labels. Cannot purchase add-ons. | Module settings and add-on access. | Platform grants `managed_capabilities` and plan modules. A tenant cannot clear a forced module. | Platform entitlement plus tenant selection on `business_settings`. | Settings fetch carries `entitlement_revision`. A newer cached revision is kept if a poll is older. | Audited. Not cross-tested. |
| Workflows | Read-only, except laundry pages that stay read-only. | No single workflows settings page in the settings nav. | None found as a tenant workflow editor. | Tenant, where a workflow record exists. | Not a shared settings write. | Audited. Not cross-tested. |
| Integrations | Read-only. Secrets are not shown. | Delivery channels exist. Credentials stay server-side. | Platform mail and WhatsApp settings are platform-only. | Platform for console mail. Tenant messaging JSON holds provider names, not secrets. | Status is not pushed to POS as secrets. | Audited. Not cross-tested. |
| Alerts | Read-only, except the laundry notifications topic. | No matching alerts editor in the settings nav. | None. | Tenant `message_events` where used. User notification preferences are not this page. | Not synchronized as a live policy. | Audited. Not cross-tested. |
| Audit trail | Read-only. Shows the business-settings `updated_at` in the business timezone and `updated_by_name` when the snapshot contains them. | Full audit log at `/settings/audit-logs`. | Operator audit is a separate control-plane log. | Tenant `audit_logs` plus the settings row timestamp. | POS does not append a second trail. An identity save writes `settings.identity` with source `pos` or `business_pro`. | Timestamp mapping tested in Rust and desktop tests. Full event list on POS not built. |
| Register | This terminal's branch, code, and activation. | Registers page. | Entitlement sync state per register. | Register. | Assignment stays on the existing activation flow. | Audited. Not cross-tested. |
| Printer & drawer | Local Windows queue, paper, copies, drawer kick. Receipt confirmation asks after each payment. | Receipt layout is branding, not a Windows queue. | None. | Terminal. | Do not copy a queue name to another machine. | Prior printer work. This pass did not retest hardware. |
| Connectivity | Connection text from the open page. | No tenant API-endpoint editor. | None for tenant endpoints. | Register reachability. | Not a shared writable setting. | Audited. Not cross-tested. |
| Security | Shows the signed-in user. Does not change PIN policy. | Roles and permissions. | Platform operator users. | Tenant roles. Session lock is local. | Permission changes follow staff sync, not this page. | Audited. Not cross-tested. |
| Appearance | Accent, theme, and density on this register. | Business accent `primary_color` and appearance settings. | None. | Register theme is local. Business accent is tenant. | A local theme is not forced onto other terminals. | Audited. Not cross-tested. |
| Shortcuts | Touch keyboard note. No shortcut editor. | None. | None. | Register. | Nothing to sync. | Audited. Not applicable as a shared setting. |
| Sync & data | Queue text from the open page. No reset control. | No queue wipe control in settings. | None. | Register queue. | Existing sale sync. | Audited. Not cross-tested. |
| Updates | Shows the local POS version. | Downloads page for the installer. | Platform release, not a tenant toggle on this page. | Register build. | Version is local. | Audited. Not cross-tested. |
| Diagnostics | Says whether business settings loaded. No secrets. | None. | None. | Register. | Not synced. | Audited. Not cross-tested. |

## What is actually shared

Shared tenant fields on `business_settings` include currency, timezone, country, location, legal names, VAT fields, loyalty, accounting, receipt branding, till policy, module selection, and the business accent.

POS in the desktop shell loads them through `settings::refresh` into the local `business_settings` cache. The browser preview calls `GET /api/v1/settings` directly.

Business Pro edits the same row through the settings API. Super Admin can force modules through `managed_capabilities`. Those forced values are not a tenant override.

## What must stay local

Windows printer queue, drawer connection, paper width, copies, scanner or scale ports, touch keyboard, local theme choice, diagnostics, and this register's sync queue stay on the terminal. Business Pro receipt layout is branding and branch contact, not a device queue.

## Audit trail gap that this pass changes

The desktop settings screen was building its settings object with `updated_at: ""` even when `GET /api/v1/settings` had returned a timestamp. The native snapshot now keeps `updated_at`, `updated_by_name`, `country`, `location`, `timezone`, and `entitlement_revision` inside the cached tax JSON. The audit page prints that timestamp in the business timezone, `Asia/Dubai` when the row does not name one. An empty or invalid value still says no timestamp was returned. A cached revision that is newer than the response is kept.

The page does not yet list each `settings.*` audit event. That list already exists in Business Pro.
