# AxizReach migration inventory

Audit of the repository before the move. There was no Evolution API client, prepaid credit ledger, or separate Reach worker. AxizReach was a campaign add-on on the shared messaging outbox.

| Existing file | Existing location | Purpose | Classification | Target location | Action |
|---|---|---|---|---|---|
| reach.py models | apps/api/app/models/reach.py | messaging_channels, reach_campaigns, reach_usage | Plugin-owned | plugins/reach/reach/models.py | Move, leave a re-export so ORM registration stays |
| reach_service.py | apps/api/app/services/reach_service.py | Campaigns, channels, usage | Plugin-owned | plugins/reach/reach/service.py | Move |
| reach.py schemas | apps/api/app/schemas/reach.py | API contracts | Plugin-owned | plugins/reach/reach/schemas.py | Move |
| reach.py router | apps/api/app/routers/v1/reach.py | /api/v1/reach | Plugin-owned | plugins/reach/reach/router.py | Move, core file only mounts the plugin |
| test_reach.py | apps/api/tests/test_reach.py | Campaign and consent tests | Plugin-owned | plugins/reach/backend/tests | Move |
| ReachPage.tsx | apps/web/src/features/reach/ReachPage.tsx | Settings campaign screen | Plugin-owned | plugins/reach/frontend | Move |
| 20261030_0089 | apps/api/alembic/versions | Creates Reach tables | Shared integration | Stays | Applied history. Do not move |
| 20261030_0090 | apps/api/alembic/versions | Marketing consent columns on customers | Core-owned | Stays | Customer master columns |
| messaging.py | apps/api/app/models/messaging.py | Templates and outbound outbox | Core-owned | Stays | Receipts and campaigns share it |
| messaging_service.py | apps/api/app/services/messaging_service.py | Consent, enqueue, dispatch_due | Core-owned | Stays | Calls a Reach bridge |
| messaging_providers.py | apps/api/app/services/messaging_providers.py | log, WhatsApp Cloud, SMS, SMTP | Core-owned | Stays | Evolution is added as a provider name only |
| customer.py | apps/api/app/models/customer.py | Customer master and opt-in | Core-owned | Stays | Reuse |
| capabilities / billing copy | packages/shared-types, apps/api/app/core/capabilities.py, console billing | axiz_reach add-on | Core-owned | Stays | Activation |
| navigation.ts, App.tsx | apps/web | Route and settings tab | Shared integration | Stays | Portal registration |
| jobs/catalog.py dispatch_messages | apps/api/app/jobs | Sends the outbox | Core-owned | Stays | No second queue |
| Redis cache | apps/api/app/core/cache.py | Shared cache | Core-owned | Stays | Not a Reach queue |
| MessagingPage.tsx | apps/web/src/features/messaging | Transactional provider setup | Core-owned | Stays | Not campaign logic |
| site WhatsApp button | apps/site | Marketing site chat link | Core-owned | Stays | Unrelated |
| super-admin WhatsAppPage | apps/super-admin | Console contact number | Core-owned | Stays | Unrelated |

New plugin-owned tables (forward revision only): reach_connections, reach_recipients, reach_templates, reach_credit_accounts, reach_credit_transactions, reach_webhook_events.
