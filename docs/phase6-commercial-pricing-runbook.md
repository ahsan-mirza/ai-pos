# Phase 6 production runbook — approved UAE commercial prices

Revision: `2026-11-14-uae-1`

The canonical list is `apps/api/app/console/commercial_manifest.py`. The quote engine reads `billing_plans`, `billing_plan_prices`, `billing_addons`, `billing_cycles`, and `billing_fees`. It does not read this file at quote time.

Prices are AED fils and are VAT-exclusive. The quote engine adds no VAT line.

This operation updates future catalog prices only. It does not change subscriptions, invoices, payments, purchased add-ons, or the active Standard tenant.

Do not run it on production until this price list has been approved. Phase 5's package retirement (`control_0035`) stays a separate migration.

## 1. Backup

Take a restorable backup of the control database before either migration. When the console registry shares the store database, that backup includes both histories. Record `control_alembic_version.version_num` and the catalog queries below.

## 2. Current catalog inventory

```sql
SELECT code, active, monthly_fils FROM billing_plans ORDER BY code;
SELECT code, months, discount_bps, active FROM billing_cycles ORDER BY sort_order;
SELECT code, amount_fils, active FROM billing_fees;
SELECT code, monthly_fils, one_time_fils, active FROM billing_addons ORDER BY code;
SELECT revision FROM commercial_catalog_releases;
SELECT p.code, s.status, count(*)
FROM subscriptions s
JOIN billing_plans p ON p.id = s.plan_id
GROUP BY p.code, s.status;
SELECT plan_code, status, count(*) FROM billing_invoices GROUP BY plan_code, status;
```

Compare the result with the approved list. A console price that differs from the manifest is an override. The first application of `2026-11-14-uae-1` sets package prices, cycle discounts, and the onboarding fee to the manifest. After that revision row exists, a later console edit of those rows is kept. An add-on whose monthly and one-time amounts are both zero is filled from the manifest. A non-zero add-on price is left as the console set it.

## 3. Approved prices

Currency: AED. Unit for add-ons: one tenant per month. Enterprise has no public price.

| Code | Monthly fils | AED / month |
|---|---:|---:|
| FREE | 0 | 0.00 |
| GROWTH | 12900 | 129.00 |
| PRO_AI | 29900 | 299.00 |
| ENTERPRISE | custom | contact sales |

Cycles, in basis points: Monthly 0, Quarterly 500 (5%), Half-yearly 1200 (12%), Annual cycle row 2500 (25%, used for a historical plan). A new Free, Growth, or Pro AI annual invoice uses the published 20% rate (2000 basis points).

Onboarding assistance: 25000 fils (AED 250.00), once, not discounted, and not included unless the customer opts in. It is not offered on Free.

Add-ons, monthly fils:

| Fils | AED | Codes |
|---:|---:|---|
| 1500 | 15 | split_bills, tips_service_charge |
| 1900 | 19 | quotes_layaway, multi_currency, variants_matrix, fefo, cheques, tax_free, alterations |
| 2900 | 29 | wholesale_pricing, serial_tracking, consignment, repairs, card_terminals, bnpl, gift_cards, fashion_rental, sales_insights |
| 3900 | 39 | tables, delivery_channels, sales_orders, online_store, b2b_credit |
| 4900 | 49 | deep_analytics, axiz_reach, uae_einvoicing, fleet_dispatch |
| 7900 | 79 | ai_insights |

`delivery_integrations` stays at zero and is contact-sales. Hardware lease (AED 150 per month and a AED 500 refundable deposit), equipment protection (AED 39 per month), and an extra register (AED 49 per month) stay at their existing configured prices.

A module named on the tenant's current package is Included and cannot be quoted again.

## 4. Deploy order

1. Confirm the backup.
2. Deploy the application build that contains this revision.
3. From `apps/api`, run `python -m alembic -c alembic_control.ini upgrade head`. The expected new step is `control_0035 -> control_0036`, which creates `commercial_catalog_releases` and does not change prices.
4. Start the application. Catalog startup applies `2026-11-14-uae-1` once.
5. Run the verification queries.

`control_0035` (retire Lite, Standard, and Pro from sale) can run in the same upgrade because it is the previous revision. It does not move the Standard tenant. Do not approve a tenant mapping in the same step.

## 5. Verification

```sql
SELECT revision FROM commercial_catalog_releases;
-- 2026-11-14-uae-1

SELECT code, monthly_fils FROM billing_plans
WHERE code IN ('FREE', 'GROWTH', 'PRO_AI', 'ENTERPRISE')
ORDER BY code;

SELECT code, monthly_fils FROM billing_addons WHERE code = 'uae_einvoicing';
-- 4900

SELECT code, monthly_fils FROM billing_addons WHERE code = 'delivery_integrations';
-- 0
```

Then, without creating an invoice:

- `GET /api/v1/billing/catalog` shows Free 0, Growth 12900, Pro AI 29900, Enterprise custom.
- A Growth monthly quote is 12900 recurring. Onboarding assistance adds 25000 only when the customer opts in.
- A Growth annual quote uses 20% and a recurring amount of 123840 fils.
- Enterprise quote returns `custom_pricing`.
- An included module quote returns `already_included`.
- Invoice totals and the Standard subscription are unchanged.

## 6. Rollback

`downgrade` of `control_0036` drops `commercial_catalog_releases` only. It does not restore previous add-on prices. Those prices were zero for the module add-ons and are not a safe automatic undo.

Restore the backup from section 1 if the price change must be reversed. Do not edit invoice rows to compensate.
