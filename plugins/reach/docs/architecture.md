# AxizReach architecture

AxizReach runs inside the API process. It uses the same database session and tenant context as the rest of the portal. It does not start a second server, a second queue, or an Evolution container.

```text
Portal /settings/reach
  -> Vite alias @reach
  -> plugins/reach/frontend
  -> /api/v1/reach
  -> apps/api/app/routers/v1/reach.py (mount only)
  -> plugins/reach/reach
```

Campaign sends stay on `outbound_messages`. `dispatch_messages` still calls `messaging_service.dispatch_due`. That function asks the Reach bridge whether a campaign row is paused, then sends. Provider `evolution` goes to the plugin client. `log`, WhatsApp Cloud, HTTP SMS, and SMTP stay in core.

Prepaid credits apply only when the WhatsApp channel provider is `evolution`. A store with no credit account keeps the previous behavior for log, Cloud, SMS, and email. One credit is reserved when an Evolution campaign is queued and consumed only after Evolution returns a message id. A definite failure before that releases the reservation. The idempotency key is the outbound message id.

`reach_usage.cost_cents` is unchanged history. It is not converted into credits.

Customer rows, `marketing_*_opt_in`, templates, and the outbox stay in core. The bridge is `apps/api/app/services/reach_bridge.py`. If the plugin cannot be imported, transactional messaging still treats a missing channel row as available.
