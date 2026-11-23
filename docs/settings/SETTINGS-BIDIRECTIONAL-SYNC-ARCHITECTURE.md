# Settings synchronization architecture

Status: **IN PROGRESS**

Date: 23-11-2026

## Canonical store

Tenant settings live on one `business_settings` row per tenant. POS and Business Pro do not have separate copies of that row in the database.

The revision is `cache_generation`. The settings snapshot exposes it as `entitlement_revision`. A desktop poll that is older than the cached revision for the same tenant is ignored. That is the existing stale-read guard. It is not a full conflict workflow for two editors.

Accepted setting changes in `settings_service` write `audit_logs` with actions such as `settings.currency`, `settings.tax`, `settings.pos_policy`, `settings.receipt`, `settings.modules`, `settings.appearance`, and `settings.timezone`. The audit row stores the actor, old values, and new values. Secrets are not part of those payloads.

## How a change moves today

Business Pro saves through the settings API. The API commits the row and the audit event, then bumps `cache_generation`.

A POS register learns about that row the next time `settings::refresh` succeeds. Checkout, tax, and module gates read the cache. There is no settings WebSocket. An open settings screen does not apply a remote edit until it loads again.

POS currency save calls `PUT /api/v1/settings/currency` when the user is allowed to manage business-wide settings. Other business sections on POS are read-only on purpose. They are marked managed in Business Pro.

Super Admin module forces are stored on `managed_capabilities`. The effective module set is resolved on the server. A tenant save cannot clear a forced module.

## What this pass does not add

No second settings table. No new outbox. No last-write-wins editor for tax or security. No claim that every section already round-trips while both applications stay open.

A client must not treat its own save as a new remote edit. Currency save already replaces the screen from the response body. Other sections do not save from POS.

## Local device settings

Printer, drawer, and other hardware values stay in the register's printer settings. They are not columns on `business_settings` and must not be copied to another terminal as if the Windows queue existed there.
