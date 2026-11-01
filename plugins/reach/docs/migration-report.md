# AxizReach migration report

Campaign logic, Evolution, recipients, templates, and the credit ledger now live in `plugins/reach`. The API process imports that package. Paths under `/api/v1/reach` and the portal route `/settings/reach` are unchanged.

Moved:

- Models, service, and schemas into `plugins/reach/reach`
- Router into `plugins/reach/reach/router.py`
- Tests into `plugins/reach/backend/tests`
- Portal screen into `plugins/reach/frontend/ReachPage.tsx`
- Forward revision `20261101_0095` into `plugins/reach/backend/migrations`

## References that stay outside the plugin

| Location | Why it stays |
|---|---|
| `apps/api/app/routers/v1/__init__.py` and `apps/api/app/routers/v1/reach.py` | Mounts `/api/v1/reach`. The core file only loads the plugin router. |
| `apps/api/app/models/__init__.py` and `apps/api/app/models/reach.py` | Registers plugin models on the shared metadata so tenant scoping and `create_all` still see them. |
| `apps/api/app/schemas/reach.py` | Re-exports plugin schemas for older imports. |
| `apps/api/app/services/reach_service.py` and `apps/api/app/services/reach_bridge.py` | Bridge used by transactional messaging. No channel row still means the channel is available. |
| `apps/api/app/services/messaging_service.py` | `dispatch_due`, consent, and the outbox. Campaign pause, Evolution submit, usage, and credit settle go through the bridge. |
| `apps/api/app/services/messaging_providers.py` | `evolution` is one allowed WhatsApp provider name. Cloud, SMS, SMTP, and log stay here. |
| `apps/api/app/models/customer.py` and `20261030_0090_reach_consent.py` | `marketing_whatsapp_opt_in`, `marketing_sms_opt_in`, `marketing_email_opt_in` belong to the customer master. |
| `apps/api/alembic/versions/20261030_0089_axiz_reach.py` and `20261030_0090_reach_consent.py` | Already applied. Moving them would break the tenant revision chain. `20261031_0091` still revises `0090`. |
| `apps/api/alembic/env.py` | Adds the plugin migration directory to `version_locations` on the same version table. |
| `apps/api/app/core/capabilities.py`, `apps/api/app/console/billing.py` | Capability `axiz_reach` and console add-on copy. |
| `apps/api/app/core/cache.py`, `apps/api/app/jobs/catalog.py` | Shared cache and `dispatch_messages`. No second queue. |
| `apps/api/app/tenancy/middleware.py` | `/api/v1/reach/webhooks/` is open so Evolution can call back without a tenant header. |
| `apps/api/app/routers/super_admin.py` | One audited admin endpoint that allocates credits. |
| `apps/web/src/App.tsx`, `navigation.ts`, `SettingsLayout.tsx` | Keeps `/settings/reach`, `Capability.AxizReach`, and the settings tab. The page module is loaded through the `@reach` alias. |
| `apps/web/src/features/messaging/MessagingPage.tsx` | Link to Reach and transactional provider setup. |

Not done in this change: dropping or recreating tables, editing revisions 0089 or 0090, copying the customer master, a new Redis deployment, a new permission, or a live WhatsApp send.
