# AxizPOS AI platform

Phase 1 is the conversational assistant. Later phases are not built yet.

## What runs today

```text
Portal
  |
FastAPI  (auth, tenant session, permissions, subscription)
  |
Assistant
  |-- builtin rules, same tools, used when Ollama is off or down
  |-- LangChain ChatOllama  ->  Ollama  ->  configured model
  |
Allowlisted report tools
  |
PostgreSQL session already filtered by tenant
  and, on PostgreSQL, by app.tenant_id row-level security
```

The model receives tool definitions and tool results. It does not receive a database connection, a tenant id it can change, or another store's rows.

Trusted context is the signed-in user on the request session: store from the host or `X-Tenant-Domain`, branch from the user's assignment, permissions from the role. Tool arguments named `tenant_id`, `branch_id`, or `store_id` are dropped. A branch the user cannot see is rejected.

Redis keys for reports and conversations start with `ai:{tenant}`.

## What is intentionally unchanged

Business types, starter packages, capability keys, and subscription checks are the existing ones. AI access for a billed store still follows the subscription state already enforced on `POST /api/v1/assistant/ask`. No new commercial AI package was added.

Reports, stock, replenishment, credit risk, and kitchen briefs already calculate figures in Python and SQL. The assistant only reads those services.

Background work uses the existing APScheduler job list. No AI job was added in this phase.

Qdrant, MinIO document search, LangGraph workflows, and forecasting models are not wired in. PostgreSQL remains the source for numbers.

## Next phases

1. LangGraph only for multi-step work. One-tool questions stay a single tool call.
2. Cached insight records produced by the existing report services, explained by the model, refreshed by the existing scheduler.
3. Forecasting in Python, stored per tenant, explained by the model. The model does not compute the forecast.
4. Industry modules selected from the current business type, without new entitlements unless the console adds them.
5. Qdrant only if a real document search needs it, with a tenant filter on every query.
