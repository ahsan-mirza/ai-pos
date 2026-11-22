# O8 PostgreSQL RLS acceptance

Status: **NOT RUN**.

No disposable PostgreSQL instance was started. The application role `ai_pos_app` was not connected. Tenant and branch policies were not executed.

In-memory SQLite tests do not prove row-level security. A superuser or `BYPASSRLS` session was not used, because no RLS session was opened.

The developer database, the inventory acceptance database, the laundry acceptance databases, and any production database were not opened.

Alembic `20261122_0128` and `20261122_0129` were not applied to those databases. API tests create tables with `create_all` on `sqlite://`.
