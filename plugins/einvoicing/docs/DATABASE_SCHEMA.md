# Database schema

Plugin tables live in the existing tenant database. Revision `einvoicing_0001` is under `plugins/einvoicing/migrations` and records itself in `alembic_version_einvoicing`. It has not been applied.

`tenant_id` is a UUID and is not a foreign key. Control-plane `tenants` may live in another database. Foreign keys that do exist:

| Column | References |
|---|---|
| `einvoicing_invoices.store_id` | `stores.id` |
| `einvoicing_invoices.source_sale_id` | `sales.id` |
| `einvoicing_invoices.customer_id` | `customers.id` |
| `einvoicing_invoice_lines.invoice_id` | `einvoicing_invoices.id` |
| `einvoicing_submissions.invoice_id` | `einvoicing_invoices.id` |
| `einvoicing_submission_attempts.submission_id` | `einvoicing_submissions.id` |
| `einvoicing_credit_notes.invoice_id` | `einvoicing_invoices.id` |
| `einvoicing_credit_notes.source_return_id` | `returns.id` |
| `einvoicing_credit_notes.store_id` | `stores.id` |

Unique keys stop a second invoice for the same sale, a second credit note for the same return, a second outbox row for the same source, a second submission for the same idempotency key, and a second webhook for the same provider event.

The ORM used by tests does not declare those foreign keys, because SQLite tests do not load the core metadata. PostgreSQL enforcement is the migration.

On PostgreSQL the migration enables and forces RLS policy `tenant_isolation`, matching the API: the row's `tenant_id` must equal `app.tenant_id`, unless `app.bypass_rls` is `on`.

Secrets are `credential_ciphertext` and `webhook_secret_ciphertext`. They are Fernet tokens from `EINVOICING_CREDENTIAL_KEY` and are not selected by `invoice_public` or `public_settings`.
