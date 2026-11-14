# Phase 5 production runbook — retire Lite, Standard, and Pro

This runbook retires three commercial package codes from sale:

- `LITE`
- `STANDARD`
- `PRO`

The packages that remain available for a new subscription are `FREE`, `GROWTH`, `PRO_AI`, and `ENTERPRISE`.

The migration is `control_0035` (`apps/api/alembic_control/versions/control_0035_retire_legacy_plans.py`). It sets `billing_plans.active = false` for those three codes. It does not delete plan rows, subscriptions, invoices, payments, or audit events, and it does not change prices or module lists.

Do not run this against production until the preflight below has been reviewed and a mapping or grandfathering decision has been recorded for every active legacy subscriber. No tenant mapping is approved. Do not rewrite a legacy subscription to Free, Growth, or Pro AI.

## 1. Backup

Take a full backup of the control database before any change. When the console registry shares the store database, that backup is the store database as well. Confirm the backup can be restored to a separate server before continuing.

Record:

- backup identity and time
- database name
- `control_alembic_version.version_num` (expected starting point: `control_0034`)

Do not read `alembic_version` as the console revision. That table is the store history.

## 2. Pre-migration package inventory

```sql
SELECT version_num FROM control_alembic_version;

SELECT code, name, active, monthly_fils
FROM billing_plans
ORDER BY code;

SELECT p.code, pr.country, pr.monthly_fils, pr.enabled
FROM billing_plan_prices pr
JOIN billing_plans p ON p.id = pr.plan_id
ORDER BY p.code, pr.country;
```

Expected commercial codes after this change stay `FREE`, `GROWTH`, `PRO_AI`, and `ENTERPRISE`, with `active = true`. `LITE`, `STANDARD`, and `PRO` stay in the table with `active = false`. Administrator prices on the four current packages must be unchanged.

## 3. Active legacy subscriber report

```sql
SELECT t.id AS tenant_id, p.code AS plan_code, s.status, c.code AS cycle_code,
       p.monthly_fils, s.current_period_end
FROM subscriptions s
JOIN billing_plans p ON p.id = s.plan_id
JOIN tenants t ON t.id = s.tenant_id
JOIN billing_cycles c ON c.id = s.cycle_id
WHERE p.code IN ('LITE', 'STANDARD', 'PRO')
ORDER BY p.code, s.status;
```

A row here is a store still subscribed to a retired package. Leave `subscriptions.plan_id` and `tenants.plan` as they are. The portal keeps that plan name and shows a retired-package notice. It does not offer the retired package for a new purchase.

## 4. Pending invoice and change-request report

```sql
SELECT id, tenant_id, plan_code, status, total_fils
FROM billing_invoices
WHERE plan_code IN ('LITE', 'STANDARD', 'PRO')
  AND status NOT IN ('paid', 'void', 'cancelled');

SELECT id, tenant_id, current_plan_code, requested_plan_code, status
FROM subscription_change_requests
WHERE status IN ('quoted', 'pending_payment', 'payment_submitted')
  AND (current_plan_code IN ('LITE', 'STANDARD', 'PRO')
       OR requested_plan_code IN ('LITE', 'STANDARD', 'PRO'));
```

Paid and completed rows are history. Do not edit them. An open invoice or an open plan-change request must be finished or cancelled by an operator before any later tenant move. This migration does not close them and does not create invoices.

## 5. Approval checkpoint

Stop here if any active legacy subscription, pending legacy invoice, or open legacy plan-change request exists and the mapping decision is not written down.

These mappings are not approved and must not be applied:

- `LITE` to `FREE`
- `STANDARD` to `GROWTH`
- `PRO` to `PRO_AI`

Approved actions for this release:

- Keep the plan row so the subscription foreign key stays valid.
- Keep the subscription on its current plan.
- Stop new quotes and new plan-change requests that target `LITE`, `STANDARD`, or `PRO`.

Deleting a plan row is not approved. `subscriptions.plan_id` and `billing_plan_prices.plan_id` reference `billing_plans.id` without a cascade that is safe to use. Invoices and change requests store the plan code as text and must stay readable.

## 6. Application deployment order

Deploy the application build that contains this phase before relying on the database stamp alone.

That build:

- rejects `LITE`, `STANDARD`, and `PRO` in quote creation and plan-change creation with `422 plan_not_selectable`
- refuses to mark those packages active again from Console
- lists only active packages on `GET /api/v1/billing/catalog`
- does not insert the three codes from `ensure_catalog`
- marks an existing active row inactive on catalog startup without rewriting its price or modules

Startup catalog initialization on the new build retires an active legacy row even if the migration has not run yet. The migration is still required so the database stamp matches the release and a process that does not call `ensure_catalog` cannot leave the codes for sale.

Do not start a second pricing or entitlement service.

## 7. Alembic command

From `apps/api`, against the control database URL the application resolves (the shared store database when the old console database is absent):

```text
python -m alembic -c alembic_control.ini upgrade head
```

The expected step is `control_0034 -> control_0035`. The console version table is `control_alembic_version`.

## 8. Post-migration verification

```sql
SELECT version_num FROM control_alembic_version;
-- control_0035

SELECT code, active FROM billing_plans
WHERE code IN ('LITE', 'STANDARD', 'PRO', 'FREE', 'GROWTH', 'PRO_AI', 'ENTERPRISE')
ORDER BY code;
-- LITE, STANDARD, PRO: active false
-- FREE, GROWTH, PRO_AI, ENTERPRISE: active true

SELECT count(*) FROM subscriptions s
JOIN billing_plans p ON p.id = s.plan_id
WHERE p.code IN ('LITE', 'STANDARD', 'PRO');
-- same count as the preflight subscriber report

SELECT count(*) FROM billing_invoices
WHERE plan_code IN ('LITE', 'STANDARD', 'PRO');
-- same count as before; statuses and totals unchanged
```

Then confirm with the application:

- `GET /api/v1/billing/catalog` returns only `FREE`, `GROWTH`, `PRO_AI`, and `ENTERPRISE`
- a quote or plan-change request with `plan_code` `LITE`, `STANDARD`, or `PRO` returns `422` and `plan_not_selectable`
- a store that is still on a legacy package still reads that package name
- Enterprise still returns custom pricing and is not quoted as a fixed price

## 9. Catalog initialization

Restart the API so `ensure_catalog` runs. Then repeat the plan query in section 8.

`LITE`, `STANDARD`, and `PRO` must still be one inactive row each when they already existed. They must not reappear as active, and a second restart must not insert another row. Prices and modules on `FREE`, `GROWTH`, `PRO_AI`, and `ENTERPRISE` must match the pre-migration inventory.

## 10. Rollback limitations

`downgrade` to `control_0034` was executed on SQLite and on a disposable PostgreSQL database. It only runs:

```sql
UPDATE billing_plans SET active = true WHERE code IN ('LITE', 'STANDARD', 'PRO');
```

That downgrade:

- does not recreate a plan row that is missing
- does not restore a previous price or module list
- does not put a subscription back onto a legacy plan, because the subscription was never moved
- turns all three codes active again, including a code an administrator had already switched off before this migration

Do not treat that downgrade as a full undo. Do not run it on production as the recovery path.

## 11. Backup recovery

If the release must be reversed:

1. Stop the application so it cannot write new quotes.
2. Restore the control database from the backup taken in section 1.
3. Deploy the previous application build.
4. Confirm `control_alembic_version` and the subscription and invoice counts match the preflight.

Do not repair a bad release by deleting plan rows or by editing invoice totals.

## Preventing new legacy subscriptions during rollout

A client that still sends `LITE`, `STANDARD`, or `PRO` is rejected by the API. Hiding the packages in the portal is not the control. After the application is deployed, catalog startup also forces those rows inactive, so a process that comes up before the migration command still will not sell them. The migration then records the same inactive state in `control_0035`.
