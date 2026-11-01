# AxizReach security

`EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, and `EVOLUTION_WEBHOOK_SECRET` stay on the server. The portal never receives the API key. Connection responses omit `webhook_key`.

The webhook route is open to the internet so Evolution can call it, and it does not accept a tenant header. Authentication is the shared secret compared with `hmac.compare_digest`. The connection is loaded by its stored unguessable key. Duplicate `eventId` values are stored once and ignored.

Campaign routes still require `Permission.MESSAGING_MANAGE` and `require_reach()`. Turning the capability off stops new campaign sends inside `dispatch_due`. Historical campaigns and `reach_usage` rows are kept. Existing roles are not given a new permission.

Credit rows are tenant scoped. A request session cannot turn off that filter. Allocations are an audited console admin action.

STOP, unsubscribe, and cancel on the connected WhatsApp number clear that customer's WhatsApp and SMS marketing opt-in and skip queued campaign messages.

## Baileys account restriction

Evolution's WhatsApp integration uses Baileys, an unofficial WhatsApp Web client. WhatsApp can restrict or ban the linked number. Use a number the store is allowed to connect, keep the session on the central Evolution API, and do not treat a QR scan in development as production approval. WhatsApp Cloud API remains available for stores that should not use Baileys. Real QR testing is manual and needs that authorized number.
