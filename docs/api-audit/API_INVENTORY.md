# API inventory

Generated from the FastAPI application object (`app.main.create_app`), not from a guessed module list.
Paths include router prefixes. `HEAD` is omitted because FastAPI adds it beside every `GET`.

Registered operations: **652**.
Hidden from the OpenAPI schema: **9**.

Authentication is classified from the endpoint's parameter names.
`authenticated` means the function takes a principal, the current user, or an ignored auth dependency.
A route can still require a permission, a capability, or a tenant even when this column says `public`,
because some routers attach those dependencies on the router rather than the function.
Tenant routing is applied by middleware to every path that is not in the public allow-list
(`/health`, `/ready`, docs, signup, console, media, and the billing and download exceptions).

## Counts by area

| Area | Operations |
| --- | ---: |
| `accounting` | 19 |
| `addon-access` | 4 |
| `analytics` | 1 |
| `api` | 1 |
| `approvals` | 4 |
| `assistant` | 4 |
| `audit-logs` | 5 |
| `auth` | 16 |
| `bank` | 13 |
| `billing` | 13 |
| `brands` | 4 |
| `catalog` | 1 |
| `categories` | 5 |
| `channels` | 8 |
| `cheques` | 1 |
| `consignment` | 2 |
| `currencies` | 2 |
| `customers` | 14 |
| `deep-analytics` | 2 |
| `devices` | 4 |
| `dining` | 6 |
| `docs` | 2 |
| `downloads` | 3 |
| `einvoices` | 3 |
| `einvoicing` | 7 |
| `expenses` | 4 |
| `exports` | 5 |
| `fnb` | 6 |
| `gift-cards` | 4 |
| `grocery` | 1 |
| `health` | 1 |
| `insights` | 7 |
| `integrations` | 4 |
| `inventory` | 49 |
| `jobs` | 1 |
| `kds` | 8 |
| `kitchen-agent` | 1 |
| `labels` | 2 |
| `loyalty` | 5 |
| `manager` | 3 |
| `margin` | 5 |
| `markdowns` | 3 |
| `media` | 1 |
| `menu` | 14 |
| `messaging` | 6 |
| `onboarding` | 4 |
| `openapi.json` | 1 |
| `orders` | 12 |
| `payables` | 13 |
| `payments` | 18 |
| `peripherals` | 1 |
| `price-lists` | 16 |
| `pricing` | 3 |
| `product-models` | 8 |
| `products` | 10 |
| `promotions` | 3 |
| `quotes` | 5 |
| `reach` | 25 |
| `ready` | 1 |
| `recipes` | 7 |
| `redoc` | 1 |
| `rentals` | 14 |
| `reorders` | 15 |
| `repair` | 2 |
| `repairs` | 23 |
| `replenishment` | 10 |
| `reports` | 11 |
| `reservations` | 15 |
| `returns` | 4 |
| `roles` | 3 |
| `sales` | 3 |
| `sales-orders` | 16 |
| `serials` | 1 |
| `settings` | 11 |
| `shifts` | 1 |
| `signup` | 12 |
| `site` | 1 |
| `staff` | 14 |
| `store-credits` | 1 |
| `stores` | 4 |
| `super-admin` | 61 |
| `sync` | 1 |
| `tenant` | 4 |
| `terminals` | 1 |
| `timesheets` | 3 |
| `track` | 1 |
| `trade-ins` | 2 |
| `units` | 2 |
| `users` | 6 |
| `warranties` | 6 |
| `ws` | 2 |

## accounting

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/accounting/accounts` | `app.routers.v1.accounting` | authenticated | `list` |
| POST | `/api/v1/accounting/accounts` | `app.routers.v1.accounting` | authenticated | `GlAccountRow` |
| PUT | `/api/v1/accounting/accounts/{account_id}` | `app.routers.v1.accounting` | authenticated | `GlAccountRow` |
| GET | `/api/v1/accounting/accounts/{account_id}/ledger` | `app.routers.v1.accounting` | authenticated | `AccountLedger` |
| GET | `/api/v1/accounting/balance-sheet` | `app.routers.v1.accounting` | authenticated | `BalanceSheet` |
| POST | `/api/v1/accounting/close-year` | `app.routers.v1.accounting` | authenticated | `` |
| GET | `/api/v1/accounting/corporate-tax` | `app.routers.v1.accounting` | authenticated | `CorporateTaxEstimate` |
| POST | `/api/v1/accounting/corporate-tax/provision` | `app.routers.v1.accounting` | authenticated | `JournalEntryOut` |
| GET | `/api/v1/accounting/cost-reconciliation` | `app.routers.v1.accounting` | authenticated | `CostReconciliation` |
| PUT | `/api/v1/accounting/costing-method` | `app.routers.v1.accounting` | authenticated | `AccountingSettings` |
| GET | `/api/v1/accounting/income-statement` | `app.routers.v1.accounting` | authenticated | `IncomeStatement` |
| GET | `/api/v1/accounting/journals` | `app.routers.v1.accounting` | authenticated | `list` |
| POST | `/api/v1/accounting/journals` | `app.routers.v1.accounting` | authenticated | `JournalEntryOut` |
| POST | `/api/v1/accounting/journals/{entry_id}/reverse` | `app.routers.v1.accounting` | authenticated | `JournalEntryOut` |
| POST | `/api/v1/accounting/lock` | `app.routers.v1.accounting` | authenticated | `AccountingSettings` |
| POST | `/api/v1/accounting/post` | `app.routers.v1.accounting` | authenticated | `PostResult` |
| GET | `/api/v1/accounting/settings` | `app.routers.v1.accounting` | authenticated | `AccountingSettings` |
| PUT | `/api/v1/accounting/settings` | `app.routers.v1.accounting` | authenticated | `AccountingSettings` |
| GET | `/api/v1/accounting/trial-balance` | `app.routers.v1.accounting` | authenticated | `TrialBalance` |

## addon-access

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| PUT | `/api/v1/addon-access/assignments` | `app.routers.v1.addon_access` | public | `list` |
| GET | `/api/v1/addon-access/history` | `app.routers.v1.addon_access` | authenticated | `list` |
| GET | `/api/v1/addon-access/modules` | `app.routers.v1.addon_access` | authenticated | `list` |
| GET | `/api/v1/addon-access/users` | `app.routers.v1.addon_access` | public | `list` |

## analytics

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/analytics/summary` | `app.routers.v1.analytics` | authenticated | `AnalyticsSummary` |

## api

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/download/installer/win` (hidden) | `app.main` | public | `` |

## approvals

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/approvals/{request_id}` | `app.routers.v1.approvals` | authenticated | `ApprovalOut` |
| POST | `/api/v1/approvals/{request_id}/approve` | `app.routers.v1.approvals` | authenticated | `ApprovalOut` |
| POST | `/api/v1/approvals/{request_id}/cancel` | `app.routers.v1.approvals` | authenticated | `ApprovalOut` |
| POST | `/api/v1/approvals/{request_id}/decline` | `app.routers.v1.approvals` | authenticated | `ApprovalOut` |

## assistant

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/assistant/ask` | `app.routers.v1.assistant` | authenticated | `AssistantReply` |
| DELETE | `/api/v1/assistant/conversations/{conversation_id}` | `app.routers.v1.assistant` | authenticated | `` |
| GET | `/api/v1/assistant/conversations/{conversation_id}` | `app.routers.v1.assistant` | authenticated | `AssistantConversation` |
| GET | `/api/v1/assistant/health` | `app.routers.v1.assistant` | authenticated | `AssistantHealth` |

## audit-logs

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/audit-logs/export` | `app.routers.v1.audit` | authenticated | `` |
| GET | `/api/v1/audit-logs/facets` | `app.routers.v1.audit` | authenticated | `AuditFacets` |
| GET | `/api/v1/audit-logs/summary` | `app.routers.v1.audit` | authenticated | `AuditSummary` |
| POST | `/api/v1/audit-logs/sync` | `app.routers.v1.audit` | authenticated | `DesktopAuditResult` |
| GET | `/api/v1/audit-logs/{log_id}` | `app.routers.v1.audit` | authenticated | `AuditLogDetail` |

## auth

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/auth/cashiers` | `app.routers.v1.auth` | authenticated | `list` |
| POST | `/api/v1/auth/forgot-password` | `app.routers.v1.auth` | public | `ForgotPasswordResponse` |
| POST | `/api/v1/auth/handoff` | `app.routers.v1.auth` | public | `TokenResponse` |
| POST | `/api/v1/auth/login-password` | `app.routers.v1.auth` | public | `TokenResponse` |
| POST | `/api/v1/auth/login-pin` | `app.routers.v1.auth` | authenticated | `TokenResponse` |
| GET | `/api/v1/auth/me` | `app.routers.v1.auth` | authenticated | `UserOut` |
| PATCH | `/api/v1/auth/me` | `app.routers.v1.auth` | authenticated | `UserOut` |
| DELETE | `/api/v1/auth/me/avatar` | `app.routers.v1.auth` | authenticated | `UserOut` |
| POST | `/api/v1/auth/me/avatar` | `app.routers.v1.auth` | authenticated | `UserOut` |
| POST | `/api/v1/auth/me/password` | `app.routers.v1.auth` | authenticated | `TokenResponse` |
| POST | `/api/v1/auth/recover-store-code` | `app.routers.v1.auth` | public | `ForgotPasswordResponse` |
| POST | `/api/v1/auth/recover-store-code/verify` | `app.routers.v1.auth` | public | `StoreCodeVerifyResponse` |
| POST | `/api/v1/auth/refresh` | `app.routers.v1.auth` | public | `TokenResponse` |
| POST | `/api/v1/auth/reset-password` | `app.routers.v1.auth` | public | `ForgotPasswordResponse` |
| POST | `/api/v1/auth/unlock` | `app.routers.v1.auth` | authenticated | `TokenResponse` |
| POST | `/api/v1/auth/verify-reset-code` | `app.routers.v1.auth` | public | `ForgotPasswordResponse` |

## bank

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/bank/accounts` | `app.routers.v1.banking` | authenticated | `list` |
| POST | `/api/v1/bank/accounts` | `app.routers.v1.banking` | authenticated | `BankAccountOut` |
| PUT | `/api/v1/bank/accounts/{account_id}` | `app.routers.v1.banking` | authenticated | `BankAccountOut` |
| POST | `/api/v1/bank/accounts/{account_id}/auto-match` | `app.routers.v1.banking` | authenticated | `AutoMatchOut` |
| GET | `/api/v1/bank/accounts/{account_id}/lines` | `app.routers.v1.banking` | authenticated | `list` |
| GET | `/api/v1/bank/accounts/{account_id}/statements` | `app.routers.v1.banking` | authenticated | `list` |
| POST | `/api/v1/bank/accounts/{account_id}/statements` | `app.routers.v1.banking` | authenticated | `StatementImportOut` |
| GET | `/api/v1/bank/accounts/{account_id}/summary` | `app.routers.v1.banking` | authenticated | `ReconciliationSummary` |
| POST | `/api/v1/bank/lines/{line_id}/book-charge` | `app.routers.v1.banking` | authenticated | `StatementLineOut` |
| GET | `/api/v1/bank/lines/{line_id}/candidates` | `app.routers.v1.banking` | authenticated | `list` |
| POST | `/api/v1/bank/lines/{line_id}/ignore` | `app.routers.v1.banking` | authenticated | `StatementLineOut` |
| POST | `/api/v1/bank/lines/{line_id}/match` | `app.routers.v1.banking` | authenticated | `StatementLineOut` |
| POST | `/api/v1/bank/lines/{line_id}/unmatch` | `app.routers.v1.banking` | authenticated | `StatementLineOut` |

## billing

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/billing/access` | `app.routers.v1.billing` | authenticated | `AccessOut` |
| POST | `/api/v1/billing/addons/{code}/checkout` | `app.routers.v1.billing` | authenticated | `CheckoutOut` |
| GET | `/api/v1/billing/catalog` | `app.routers.v1.billing` | authenticated | `CatalogOut` |
| POST | `/api/v1/billing/checkout` | `app.routers.v1.billing` | authenticated | `CheckoutOut` |
| GET | `/api/v1/billing/checkout/return` | `app.routers.v1.billing` | public | `` |
| GET | `/api/v1/billing/checkout/{checkout_id}` | `app.routers.v1.billing` | authenticated | `CheckoutStatus` |
| POST | `/api/v1/billing/checkout/{checkout_id}/simulate` | `app.routers.v1.billing` | authenticated | `CheckoutStatus` |
| GET | `/api/v1/billing/marketplace` | `app.routers.v1.billing` | authenticated | `MarketplaceOut` |
| GET | `/api/v1/billing/public-catalog` | `app.routers.v1.billing` | public | `CatalogOut` |
| POST | `/api/v1/billing/quote` | `app.routers.v1.billing` | authenticated | `QuoteOut` |
| POST | `/api/v1/billing/stripe-webhook` | `app.routers.v1.billing` | public | `dict` |
| POST | `/api/v1/billing/transfers` | `app.routers.v1.billing` | authenticated | `dict` |
| GET | `/api/v1/billing/transfers/{transfer_id}/receipt` | `app.routers.v1.billing` | authenticated | `` |

## brands

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/brands/{brand_id}` | `app.routers.v1.brands` | authenticated | `` |
| PATCH | `/api/v1/brands/{brand_id}` | `app.routers.v1.brands` | authenticated | `BrandOut` |
| DELETE | `/api/v1/brands/{brand_id}/sub-categories/{sub_category_id}` | `app.routers.v1.brands` | authenticated | `BrandOut` |
| POST | `/api/v1/brands/{brand_id}/sub-categories/{sub_category_id}` | `app.routers.v1.brands` | authenticated | `BrandOut` |

## catalog

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/catalog/attributes` | `app.routers.v1.catalogue` | authenticated | `CatalogAttributesOut` |

## categories

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/categories/sub-categories/{sub_category_id}` | `app.routers.v1.categories` | authenticated | `CategoryOut` |
| PATCH | `/api/v1/categories/sub-categories/{sub_category_id}` | `app.routers.v1.categories` | authenticated | `CategoryOut` |
| DELETE | `/api/v1/categories/{category_id}` | `app.routers.v1.categories` | authenticated | `` |
| PATCH | `/api/v1/categories/{category_id}` | `app.routers.v1.categories` | authenticated | `CategoryOut` |
| POST | `/api/v1/categories/{category_id}/sub-categories` | `app.routers.v1.categories` | authenticated | `CategoryOut` |

## channels

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/channels/manual-orders` | `app.routers.v1.channels` | authenticated | `OrderOut` |
| POST | `/api/v1/channels/orders/{order_id}/accept` | `app.routers.v1.channels` | authenticated | `OrderOut` |
| POST | `/api/v1/channels/orders/{order_id}/reject` | `app.routers.v1.channels` | authenticated | `OrderOut` |
| GET | `/api/v1/channels/settlement` | `app.routers.v1.channels` | authenticated | `SettlementReport` |
| PUT | `/api/v1/channels/{channel_id}` | `app.routers.v1.channels` | authenticated | `ChannelOut` |
| POST | `/api/v1/channels/{channel_id}/payouts` | `app.routers.v1.channels` | authenticated | `PayoutOut` |
| POST | `/api/v1/channels/{channel_id}/rotate-secret` | `app.routers.v1.channels` | authenticated | `ChannelSecretOut` |
| POST | `/api/v1/channels/{code}/orders` | `app.routers.v1.channels` | public | `WebhookResult` |

## cheques

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/cheques/{cheque_id}/{action}` | `app.routers.v1.cheques` | authenticated | `ChequeOut` |

## consignment

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/consignment/settlements` | `app.routers.v1.consignment` | authenticated | `list` |
| POST | `/api/v1/consignment/settlements` | `app.routers.v1.consignment` | authenticated | `list` |

## currencies

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/currencies/sync` | `app.routers.v1.currencies` | authenticated | `list` |
| PUT | `/api/v1/currencies/{code}/rate` | `app.routers.v1.currencies` | authenticated | `list` |

## customers

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/customers/risk` | `app.routers.v1.customers` | authenticated | `list` |
| POST | `/api/v1/customers/statements/send` | `app.routers.v1.customers` | authenticated | `DunningResult` |
| GET | `/api/v1/customers/sync` | `app.routers.v1.customers` | authenticated | `list` |
| GET | `/api/v1/customers/{customer_id}` | `app.routers.v1.customers` | authenticated | `CustomerOut` |
| PATCH | `/api/v1/customers/{customer_id}` | `app.routers.v1.customers` | authenticated | `CustomerOut` |
| POST | `/api/v1/customers/{customer_id}/adjustments` | `app.routers.v1.customers` | authenticated | `CustomerOut` |
| GET | `/api/v1/customers/{customer_id}/coupons` | `app.routers.v1.customers` | authenticated | `list` |
| POST | `/api/v1/customers/{customer_id}/credit-hold` | `app.routers.v1.customers` | authenticated | `CustomerOut` |
| GET | `/api/v1/customers/{customer_id}/history` | `app.routers.v1.customers` | authenticated | `list` |
| POST | `/api/v1/customers/{customer_id}/payments` | `app.routers.v1.customers` | authenticated | `PaymentOut` |
| GET | `/api/v1/customers/{customer_id}/risk` | `app.routers.v1.customers` | authenticated | `CreditRiskOut` |
| GET | `/api/v1/customers/{customer_id}/sales` | `app.routers.v1.customers` | authenticated | `list` |
| GET | `/api/v1/customers/{customer_id}/statement` | `app.routers.v1.customers` | authenticated | `StatementOut` |
| GET | `/api/v1/customers/{customer_id}/statement.pdf` | `app.routers.v1.customers` | authenticated | `` |

## deep-analytics

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/deep-analytics/export` | `app.routers.v1.deep_analytics` | authenticated | `` |
| GET | `/api/v1/deep-analytics/overview` | `app.routers.v1.deep_analytics` | authenticated | `DeepOverview` |

## devices

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/devices/me` | `app.routers.v1.devices` | authenticated | `DeviceSelfOut` |
| POST | `/api/v1/devices/{device_id}/activation-key` | `app.routers.v1.devices` | authenticated | `ActivationKeyOut` |
| POST | `/api/v1/devices/{device_id}/revoke` | `app.routers.v1.devices` | authenticated | `DeviceOut` |
| POST | `/api/v1/devices/{device_id}/rotate` | `app.routers.v1.devices` | authenticated | `DeviceKeyOut` |

## dining

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/dining/areas` | `app.routers.v1.dining` | authenticated | `FloorOut` |
| PUT | `/api/v1/dining/areas/{area_id}` | `app.routers.v1.dining` | authenticated | `FloorOut` |
| GET | `/api/v1/dining/floor` | `app.routers.v1.dining` | authenticated | `FloorOut` |
| POST | `/api/v1/dining/tables` | `app.routers.v1.dining` | authenticated | `FloorOut` |
| DELETE | `/api/v1/dining/tables/{table_id}` | `app.routers.v1.dining` | authenticated | `` |
| PUT | `/api/v1/dining/tables/{table_id}` | `app.routers.v1.dining` | authenticated | `FloorOut` |

## docs

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/docs` (hidden) | `fastapi.applications` | public | `` |
| GET | `/docs/oauth2-redirect` (hidden) | `fastapi.applications` | public | `` |

## downloads

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/downloads/latest.json` | `app.routers.v1.downloads` | public | `LatestInstaller` |
| GET | `/api/v1/downloads/pos/{version}/{filename}` | `app.routers.v1.downloads` | authenticated | `` |
| GET | `/api/v1/downloads/win` | `app.routers.v1.downloads` | public | `` |

## einvoices

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/einvoices/summary` | `app.routers.v1.einvoices` | authenticated | `EInvoiceSummary` |
| GET | `/api/v1/einvoices/{einvoice_id}` | `app.routers.v1.einvoices` | authenticated | `EInvoiceOut` |
| GET | `/api/v1/einvoices/{einvoice_id}/xml` | `app.routers.v1.einvoices` | authenticated | `` |

## einvoicing

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/einvoicing/configuration` | `app.routers.v1.einvoicing_addon` | public | `dict` |
| PUT | `/api/v1/einvoicing/configuration` | `app.routers.v1.einvoicing_addon` | public | `dict` |
| GET | `/api/v1/einvoicing/dashboard` | `app.routers.v1.einvoicing_addon` | public | `dict` |
| GET | `/api/v1/einvoicing/invoices` | `app.routers.v1.einvoicing_addon` | public | `list` |
| GET | `/api/v1/einvoicing/invoices/{invoice_id}` | `app.routers.v1.einvoicing_addon` | public | `dict` |
| POST | `/api/v1/einvoicing/invoices/{invoice_id}/retry` | `app.routers.v1.einvoicing_addon` | public | `dict` |
| POST | `/api/v1/einvoicing/providers/test` | `app.routers.v1.einvoicing_addon` | public | `dict` |

## expenses

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/expenses/petty-cash/count` | `app.routers.v1.expenses` | authenticated | `PettyCashOut` |
| POST | `/api/v1/expenses/petty-cash/top-up` | `app.routers.v1.expenses` | authenticated | `PettyCashOut` |
| GET | `/api/v1/expenses/petty-cash/{store_id}` | `app.routers.v1.expenses` | authenticated | `PettyCashOut` |
| POST | `/api/v1/expenses/{expense_id}/void` | `app.routers.v1.expenses` | authenticated | `ExpenseOut` |

## exports

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/exports/accounts` | `app.routers.v1.loyalty` | authenticated | `list` |
| PUT | `/api/v1/exports/accounts` | `app.routers.v1.loyalty` | authenticated | `list` |
| GET | `/api/v1/exports/einvoices.zip` | `app.routers.v1.loyalty` | authenticated | `` |
| GET | `/api/v1/exports/einvoices/{sale_id}.xml` | `app.routers.v1.loyalty` | authenticated | `` |
| GET | `/api/v1/exports/gl.csv` | `app.routers.v1.loyalty` | authenticated | `` |

## fnb

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/fnb/menu` | `app.routers.v1.fnb_table_orders` | authenticated | `TableMenuOut` |
| GET | `/api/v1/fnb/tables/{table_id}/active-session` | `app.routers.v1.fnb_table_orders` | authenticated | `ActiveSessionOut` |
| POST | `/api/v1/fnb/tables/{table_id}/call-waiter` | `app.routers.v1.fnb_table_orders` | authenticated | `WaiterCallOut` |
| POST | `/api/v1/fnb/tables/{table_id}/orders/add-round` | `app.routers.v1.fnb_table_orders` | authenticated | `ActiveSessionOut` |
| POST | `/api/v1/fnb/tables/{table_id}/request-bill` | `app.routers.v1.fnb_table_orders` | authenticated | `ActiveSessionOut` |
| POST | `/api/v1/fnb/tables/{table_id}/session/start` | `app.routers.v1.fnb_table_orders` | authenticated | `ActiveSessionOut` |

## gift-cards

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/gift-cards/issue` | `app.routers.v1.gift_cards` | authenticated | `list` |
| GET | `/api/v1/gift-cards/product` | `app.routers.v1.gift_cards` | authenticated | `GiftCardProductOut` |
| GET | `/api/v1/gift-cards/{code}` | `app.routers.v1.gift_cards` | authenticated | `StoreCreditOut` |
| POST | `/api/v1/gift-cards/{code}/void` | `app.routers.v1.gift_cards` | authenticated | `StoreCreditOut` |

## grocery

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/grocery/suggestions` | `app.routers.v1.grocery` | authenticated | `GuestSuggestionsOut` |

## health

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/health` | `app.main` | public | `dict` |

## insights

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/insights/anomalies` | `app.routers.v1.insights` | authenticated | `AnomalyReport` |
| GET | `/api/v1/insights/feed` | `app.routers.v1.insights` | authenticated | `InsightFeed` |
| GET | `/api/v1/insights/kitchen` | `app.routers.v1.insights` | authenticated | `KitchenReport` |
| GET | `/api/v1/insights/pricing` | `app.routers.v1.insights` | authenticated | `PricingReport` |
| GET | `/api/v1/insights/shrink` | `app.routers.v1.insights` | authenticated | `ShrinkReport` |
| GET | `/api/v1/insights/tables` | `app.routers.v1.insights` | authenticated | `TableReport` |
| GET | `/api/v1/insights/upsell` | `app.routers.v1.insights` | authenticated | `UpsellReport` |

## integrations

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/integrations/payments/return/{intent_id}` | `app.routers.v1.integrations` | public | `` |
| GET | `/api/v1/integrations/payments/simulator/checkout/{intent_id}` | `app.routers.v1.integrations` | public | `` |
| POST | `/api/v1/integrations/payments/simulator/checkout/{intent_id}` | `app.routers.v1.integrations` | public | `` |
| POST | `/api/v1/integrations/payments/{provider}/webhook` | `app.routers.v1.integrations` | public | `IntentOut` |

## inventory

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/inventory/adjust` | `app.routers.v1.inventory` | authenticated | `ManualAdjustmentOut` |
| GET | `/api/v1/inventory/adjust/cost` | `app.routers.v1.inventory` | authenticated | `ProductCosting` |
| GET | `/api/v1/inventory/availability` | `app.routers.v1.inventory` | authenticated | `AvailabilityOut` |
| GET | `/api/v1/inventory/batches` | `app.routers.v1.batches` | authenticated | `BatchPage` |
| GET | `/api/v1/inventory/batches/{batch_id}` | `app.routers.v1.batches` | authenticated | `BatchDetail` |
| PATCH | `/api/v1/inventory/batches/{batch_id}` | `app.routers.v1.batches` | authenticated | `BatchDetail` |
| GET | `/api/v1/inventory/batches/{batch_id}/file` | `app.routers.v1.batches` | authenticated | `` |
| POST | `/api/v1/inventory/batches/{batch_id}/rollback` | `app.routers.v1.batches` | authenticated | `RollbackResult` |
| GET | `/api/v1/inventory/batches/{batch_id}/rollback-preview` | `app.routers.v1.batches` | authenticated | `RollbackPreview` |
| GET | `/api/v1/inventory/counts/{count_id}` | `app.routers.v1.stock_counts` | authenticated | `StockCountOut` |
| PUT | `/api/v1/inventory/counts/{count_id}/lines` | `app.routers.v1.stock_counts` | authenticated | `StockCountOut` |
| POST | `/api/v1/inventory/counts/{count_id}/submit` | `app.routers.v1.stock_counts` | authenticated | `StockCountOut` |
| POST | `/api/v1/inventory/counts/{count_id}/{action}` | `app.routers.v1.stock_counts` | authenticated | `StockCountOut` |
| GET | `/api/v1/inventory/expiring` | `app.routers.v1.expiry` | authenticated | `list` |
| POST | `/api/v1/inventory/expiry-writeoff` | `app.routers.v1.expiry` | authenticated | `ExpiryWriteOffOut` |
| DELETE | `/api/v1/inventory/images/{image_id}` | `app.routers.v1.catalogue` | authenticated | `` |
| PATCH | `/api/v1/inventory/images/{image_id}` | `app.routers.v1.catalogue` | authenticated | `ProductImageOut` |
| POST | `/api/v1/inventory/import/commit` | `app.routers.v1.batches` | authenticated | `BatchDetail` |
| POST | `/api/v1/inventory/import/preview` | `app.routers.v1.batches` | authenticated | `PreviewOut` |
| GET | `/api/v1/inventory/import/templates` | `app.routers.v1.batches` | authenticated | `list` |
| POST | `/api/v1/inventory/import/templates` | `app.routers.v1.batches` | authenticated | `TemplateOut` |
| DELETE | `/api/v1/inventory/import/templates/{template_id}` | `app.routers.v1.batches` | authenticated | `` |
| POST | `/api/v1/inventory/import/upload` | `app.routers.v1.batches` | authenticated | `UploadOut` |
| PATCH | `/api/v1/inventory/levels/{product_id}/{store_id}` | `app.routers.v1.inventory` | authenticated | `StockRow` |
| GET | `/api/v1/inventory/movements` | `app.routers.v1.inventory` | authenticated | `list` |
| POST | `/api/v1/inventory/products` | `app.routers.v1.inventory` | authenticated | `ProductOut` |
| GET | `/api/v1/inventory/products/{product_id}/images` | `app.routers.v1.catalogue` | authenticated | `list` |
| POST | `/api/v1/inventory/products/{product_id}/images` | `app.routers.v1.catalogue` | authenticated | `ProductImageOut` |
| GET | `/api/v1/inventory/purchase-orders` | `app.routers.v1.inventory` | authenticated | `list` |
| POST | `/api/v1/inventory/purchase-orders` | `app.routers.v1.inventory` | authenticated | `PurchaseOrderOut` |
| GET | `/api/v1/inventory/purchase-orders/{order_id}` | `app.routers.v1.inventory` | authenticated | `PurchaseOrderOut` |
| POST | `/api/v1/inventory/purchase-orders/{order_id}/cancel` | `app.routers.v1.inventory` | authenticated | `PurchaseOrderOut` |
| POST | `/api/v1/inventory/purchase-orders/{order_id}/order` | `app.routers.v1.inventory` | authenticated | `PurchaseOrderOut` |
| POST | `/api/v1/inventory/purchase-orders/{order_id}/receive` | `app.routers.v1.inventory` | authenticated | `PurchaseOrderOut` |
| GET | `/api/v1/inventory/register-serials` | `app.routers.v1.register` | authenticated | `list` |
| GET | `/api/v1/inventory/serials` | `app.routers.v1.inventory` | authenticated | `list` |
| GET | `/api/v1/inventory/serials/trace` | `app.routers.v1.inventory` | authenticated | `SerialTraceOut` |
| GET | `/api/v1/inventory/stock` | `app.routers.v1.inventory` | authenticated | `StockSummary` |
| GET | `/api/v1/inventory/suppliers` | `app.routers.v1.batches` | authenticated | `list` |
| POST | `/api/v1/inventory/suppliers` | `app.routers.v1.batches` | authenticated | `SupplierOut` |
| GET | `/api/v1/inventory/transfers` | `app.routers.v1.inventory` | authenticated | `list` |
| POST | `/api/v1/inventory/transfers` | `app.routers.v1.inventory` | authenticated | `TransferOut` |
| GET | `/api/v1/inventory/transfers/{transfer_id}` | `app.routers.v1.inventory` | authenticated | `TransferOut` |
| POST | `/api/v1/inventory/transfers/{transfer_id}/cancel` | `app.routers.v1.inventory` | authenticated | `TransferOut` |
| POST | `/api/v1/inventory/transfers/{transfer_id}/receive` | `app.routers.v1.inventory` | authenticated | `TransferOut` |
| POST | `/api/v1/inventory/transfers/{transfer_id}/ship` | `app.routers.v1.inventory` | authenticated | `TransferOut` |
| GET | `/api/v1/inventory/waste` | `app.routers.v1.expiry` | authenticated | `list` |
| POST | `/api/v1/inventory/waste` | `app.routers.v1.expiry` | authenticated | `WasteOut` |
| GET | `/api/v1/inventory/waste/sources` | `app.routers.v1.expiry` | authenticated | `list` |

## jobs

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/jobs/{name}/run` | `app.routers.v1.messaging` | authenticated | `JobOut` |

## kds

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/kds/orders/{order_id}/tickets` | `app.routers.v1.kds` | authenticated | `list` |
| GET | `/api/v1/kds/stations` | `app.routers.v1.kds` | authenticated | `list` |
| POST | `/api/v1/kds/stations` | `app.routers.v1.kds` | authenticated | `KitchenStationOut` |
| PUT | `/api/v1/kds/stations/{station_id}` | `app.routers.v1.kds` | authenticated | `KitchenStationOut` |
| GET | `/api/v1/kds/stations/{station_id}/tickets` | `app.routers.v1.kds` | authenticated | `TicketBoard` |
| POST | `/api/v1/kds/tickets/{ticket_id}/items/{item_id}/ready` | `app.routers.v1.kds` | authenticated | `TicketOut` |
| POST | `/api/v1/kds/tickets/{ticket_id}/recall` | `app.routers.v1.kds` | authenticated | `TicketOut` |
| POST | `/api/v1/kds/tickets/{ticket_id}/status` | `app.routers.v1.kds` | authenticated | `TicketOut` |

## kitchen-agent

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/kitchen-agent/actions` | `app.routers.v1.kitchen_agent` | authenticated | `KitchenActionOut` |

## labels

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/labels/batches/{batch_id}` | `app.routers.v1.labels` | authenticated | `` |
| GET | `/api/v1/labels/models/{model_id}` | `app.routers.v1.labels` | authenticated | `` |

## loyalty

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/loyalty/customers/{customer_id}` | `app.routers.v1.loyalty` | authenticated | `list` |
| POST | `/api/v1/loyalty/customers/{customer_id}/adjust` | `app.routers.v1.loyalty` | authenticated | `list` |
| GET | `/api/v1/loyalty/customers/{customer_id}/standing` | `app.routers.v1.loyalty` | authenticated | `LoyaltyStanding` |
| GET | `/api/v1/loyalty/settings` | `app.routers.v1.loyalty` | authenticated | `LoyaltySettingsOut` |
| PUT | `/api/v1/loyalty/settings` | `app.routers.v1.loyalty` | authenticated | `LoyaltySettingsOut` |

## manager

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/manager/credit-holds` | `app.routers.v1.manager` | authenticated | `list` |
| GET | `/api/v1/manager/dashboard` | `app.routers.v1.manager` | authenticated | `ManagerDashboard` |
| GET | `/api/v1/manager/timesheets` | `app.routers.v1.manager` | authenticated | `list` |

## margin

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/margin/exceptions` | `app.routers.v1.margin` | authenticated | `MarginExceptionList` |
| GET | `/api/v1/margin/floors` | `app.routers.v1.margin` | authenticated | `list` |
| GET | `/api/v1/margin/policies` | `app.routers.v1.margin` | authenticated | `list` |
| PUT | `/api/v1/margin/policies` | `app.routers.v1.margin` | authenticated | `list` |
| DELETE | `/api/v1/margin/policies/{policy_id}` | `app.routers.v1.margin` | authenticated | `list` |

## markdowns

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/markdowns/preview` | `app.routers.v1.markdowns` | authenticated | `MarkdownPreview` |
| POST | `/api/v1/markdowns/{event_id}/end` | `app.routers.v1.markdowns` | authenticated | `MarkdownEventOut` |
| GET | `/api/v1/markdowns/{event_id}/labels.pdf` | `app.routers.v1.markdowns` | authenticated | `` |

## media

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/media/{tenant}/{folder}/{name}` (hidden) | `app.routers.media` | public | `` |

## menu

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/menu/combos` | `app.routers.v1.menu` | authenticated | `list` |
| POST | `/api/v1/menu/combos` | `app.routers.v1.menu` | authenticated | `ComboOut` |
| DELETE | `/api/v1/menu/combos/{product_id}` | `app.routers.v1.menu` | authenticated | `` |
| GET | `/api/v1/menu/combos/{product_id}` | `app.routers.v1.menu` | authenticated | `ComboOut` |
| PUT | `/api/v1/menu/combos/{product_id}` | `app.routers.v1.menu` | authenticated | `ComboOut` |
| GET | `/api/v1/menu/modifier-groups` | `app.routers.v1.menu` | authenticated | `list` |
| POST | `/api/v1/menu/modifier-groups` | `app.routers.v1.menu` | authenticated | `ModifierGroupOut` |
| POST | `/api/v1/menu/modifier-groups/from-template` | `app.routers.v1.menu` | authenticated | `ModifierGroupOut` |
| DELETE | `/api/v1/menu/modifier-groups/{group_id}` | `app.routers.v1.menu` | authenticated | `` |
| PUT | `/api/v1/menu/modifier-groups/{group_id}` | `app.routers.v1.menu` | authenticated | `ModifierGroupOut` |
| POST | `/api/v1/menu/modifier-groups/{group_id}/duplicate` | `app.routers.v1.menu` | authenticated | `ModifierGroupOut` |
| GET | `/api/v1/menu/modifier-templates` | `app.routers.v1.menu` | authenticated | `list` |
| PUT | `/api/v1/menu/products/{product_id}/modifier-groups` | `app.routers.v1.menu` | authenticated | `list` |
| GET | `/api/v1/menu/register` | `app.routers.v1.menu` | authenticated | `RegisterMenu` |

## messaging

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/messaging/outbox` | `app.routers.v1.messaging` | authenticated | `list` |
| GET | `/api/v1/messaging/settings` | `app.routers.v1.messaging` | authenticated | `MessagingSettingsOut` |
| PUT | `/api/v1/messaging/settings` | `app.routers.v1.messaging` | authenticated | `MessagingSettingsOut` |
| GET | `/api/v1/messaging/templates` | `app.routers.v1.messaging` | authenticated | `list` |
| PUT | `/api/v1/messaging/templates/{key}` | `app.routers.v1.messaging` | authenticated | `TemplateOut` |
| POST | `/api/v1/messaging/test` | `app.routers.v1.messaging` | authenticated | `OutboundOut` |

## onboarding

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/onboarding/checklist` | `app.routers.v1.onboarding` | authenticated | `Checklist` |
| POST | `/api/v1/onboarding/explore` | `app.routers.v1.onboarding` | authenticated | `Checklist` |
| POST | `/api/v1/onboarding/go-live` | `app.routers.v1.onboarding` | authenticated | `GoLiveResult` |
| POST | `/api/v1/onboarding/skip` | `app.routers.v1.onboarding` | authenticated | `Checklist` |

## openapi.json

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/openapi.json` (hidden) | `fastapi.applications` | public | `` |

## orders

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/orders/suggestions` | `app.routers.v1.orders` | authenticated | `GuestSuggestionsOut` |
| GET | `/api/v1/orders/{order_id}` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| PATCH | `/api/v1/orders/{order_id}` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/bill` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/hand-over` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/items` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/items/{item_id}/quantity` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/items/{item_id}/void` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/merge` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/move` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/send` | `app.routers.v1.orders` | authenticated | `OrderOut` |
| POST | `/api/v1/orders/{order_id}/void` | `app.routers.v1.orders` | authenticated | `OrderOut` |

## payables

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/payables/bills` | `app.routers.v1.payables` | authenticated | `list` |
| POST | `/api/v1/payables/bills` | `app.routers.v1.payables` | authenticated | `BillOut` |
| POST | `/api/v1/payables/bills/from-receipt` | `app.routers.v1.payables` | authenticated | `BillOut` |
| POST | `/api/v1/payables/bills/{bill_id}/void` | `app.routers.v1.payables` | authenticated | `BillOut` |
| GET | `/api/v1/payables/payments` | `app.routers.v1.payables` | authenticated | `list` |
| POST | `/api/v1/payables/payments` | `app.routers.v1.payables` | authenticated | `SupplierPaymentOut` |
| POST | `/api/v1/payables/payments/{payment_id}/clear` | `app.routers.v1.payables` | authenticated | `SupplierPaymentOut` |
| POST | `/api/v1/payables/payments/{payment_id}/void` | `app.routers.v1.payables` | authenticated | `SupplierPaymentOut` |
| GET | `/api/v1/payables/receipts/unbilled` | `app.routers.v1.payables` | authenticated | `list` |
| GET | `/api/v1/payables/summary` | `app.routers.v1.payables` | authenticated | `PayablesSummary` |
| POST | `/api/v1/payables/suppliers` | `app.routers.v1.payables` | authenticated | `SupplierOut` |
| PUT | `/api/v1/payables/suppliers/{supplier_id}` | `app.routers.v1.payables` | authenticated | `SupplierBalance` |
| GET | `/api/v1/payables/suppliers/{supplier_id}/statement` | `app.routers.v1.payables` | authenticated | `SupplierStatement` |

## payments

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/payments/bnpl-intents` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| POST | `/api/v1/payments/card-intents` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| GET | `/api/v1/payments/config` | `app.routers.v1.payments` | authenticated | `PaymentsConfig` |
| GET | `/api/v1/payments/dev/{intent_id}/pay` | `app.routers.v1.payments` | public | `IntentOut` |
| POST | `/api/v1/payments/dev/{intent_id}/pay` | `app.routers.v1.payments` | public | `IntentOut` |
| POST | `/api/v1/payments/intents` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| GET | `/api/v1/payments/intents/{intent_id}` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| POST | `/api/v1/payments/intents/{intent_id}/cancel` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| POST | `/api/v1/payments/intents/{intent_id}/simulate` | `app.routers.v1.payments` | authenticated | `IntentOut` |
| GET | `/api/v1/payments/list` | `app.routers.v1.payments` | authenticated | `PaymentList` |
| GET | `/api/v1/payments/providers` | `app.routers.v1.payments` | authenticated | `list` |
| GET | `/api/v1/payments/refunds` | `app.routers.v1.payments` | authenticated | `list` |
| POST | `/api/v1/payments/refunds/{refund_id}/retry` | `app.routers.v1.payments` | authenticated | `RefundOut` |
| GET | `/api/v1/payments/terminals` | `app.routers.v1.payments` | authenticated | `list` |
| POST | `/api/v1/payments/terminals` | `app.routers.v1.payments` | authenticated | `TerminalOut` |
| PATCH | `/api/v1/payments/terminals/{terminal_id}` | `app.routers.v1.payments` | authenticated | `TerminalOut` |
| POST | `/api/v1/payments/terminals/{terminal_id}/check` | `app.routers.v1.payments` | authenticated | `TerminalCheck` |
| POST | `/api/v1/payments/webhooks/{provider}` | `app.routers.v1.payments` | public | `IntentOut` |

## peripherals

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/peripherals/card-terminal/check` | `app.routers.v1.peripherals` | authenticated | `TerminalCheck` |

## price-lists

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/price-lists/changes` | `app.routers.v1.price_lists` | authenticated | `list` |
| POST | `/api/v1/price-lists/changes` | `app.routers.v1.price_lists` | authenticated | `PriceChangeOut` |
| GET | `/api/v1/price-lists/changes/{change_id}` | `app.routers.v1.price_lists` | authenticated | `PriceChangeOut` |
| POST | `/api/v1/price-lists/changes/{change_id}/apply` | `app.routers.v1.price_lists` | authenticated | `PriceChangeOut` |
| POST | `/api/v1/price-lists/changes/{change_id}/cancel` | `app.routers.v1.price_lists` | authenticated | `PriceChangeOut` |
| GET | `/api/v1/price-lists/changes/{change_id}/labels.pdf` | `app.routers.v1.price_lists` | authenticated | `` |
| GET | `/api/v1/price-lists/customers/{customer_id}` | `app.routers.v1.price_lists` | authenticated | `CustomerPricingOut` |
| GET | `/api/v1/price-lists/groups` | `app.routers.v1.price_lists` | authenticated | `list` |
| POST | `/api/v1/price-lists/groups` | `app.routers.v1.price_lists` | authenticated | `CustomerGroupOut` |
| PUT | `/api/v1/price-lists/groups/{group_id}` | `app.routers.v1.price_lists` | authenticated | `CustomerGroupOut` |
| DELETE | `/api/v1/price-lists/{list_id}` | `app.routers.v1.price_lists` | authenticated | `` |
| GET | `/api/v1/price-lists/{list_id}` | `app.routers.v1.price_lists` | authenticated | `PriceListOut` |
| PUT | `/api/v1/price-lists/{list_id}` | `app.routers.v1.price_lists` | authenticated | `PriceListOut` |
| GET | `/api/v1/price-lists/{list_id}/export.csv` | `app.routers.v1.price_lists` | authenticated | `` |
| POST | `/api/v1/price-lists/{list_id}/import` | `app.routers.v1.price_lists` | authenticated | `CsvImportResult` |
| PUT | `/api/v1/price-lists/{list_id}/items` | `app.routers.v1.price_lists` | authenticated | `PriceListOut` |

## pricing

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| PUT | `/api/v1/pricing/bulk` | `app.routers.v1.pricing` | authenticated | `BulkPriceResult` |
| GET | `/api/v1/pricing/matrix` | `app.routers.v1.pricing` | authenticated | `PricingMatrix` |
| PUT | `/api/v1/pricing/products/{product_id}` | `app.routers.v1.pricing` | authenticated | `PricingRow` |

## product-models

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/product-models/{model_id}` | `app.routers.v1.brands` | authenticated | `` |
| PATCH | `/api/v1/product-models/{model_id}` | `app.routers.v1.brands` | authenticated | `ProductModelOut` |
| GET | `/api/v1/product-models/{model_id}/images` | `app.routers.v1.catalogue` | authenticated | `list` |
| POST | `/api/v1/product-models/{model_id}/images` | `app.routers.v1.catalogue` | authenticated | `ProductImageOut` |
| GET | `/api/v1/product-models/{model_id}/matrix` | `app.routers.v1.brands` | authenticated | `MatrixOut` |
| POST | `/api/v1/product-models/{model_id}/matrix` | `app.routers.v1.brands` | authenticated | `MatrixOut` |
| POST | `/api/v1/product-models/{model_id}/matrix/bulk` | `app.routers.v1.brands` | authenticated | `MatrixBulkResult` |
| POST | `/api/v1/product-models/{model_id}/matrix/preview` | `app.routers.v1.brands` | authenticated | `MatrixPreview` |

## products

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/products/revision` | `app.routers.v1.products` | authenticated | `CatalogRevision` |
| GET | `/api/v1/products/search` | `app.routers.v1.products` | authenticated | `list` |
| DELETE | `/api/v1/products/{product_id}` | `app.routers.v1.products` | authenticated | `` |
| GET | `/api/v1/products/{product_id}` | `app.routers.v1.products` | authenticated | `ProductOut` |
| PATCH | `/api/v1/products/{product_id}` | `app.routers.v1.products` | authenticated | `ProductOut` |
| GET | `/api/v1/products/{product_id}/costing` | `app.routers.v1.products` | authenticated | `ProductCosting` |
| GET | `/api/v1/products/{product_id}/movements` | `app.routers.v1.products` | authenticated | `list` |
| GET | `/api/v1/products/{product_id}/purchase-history` | `app.routers.v1.products` | authenticated | `ProductPurchaseHistory` |
| GET | `/api/v1/products/{product_id}/sales-history` | `app.routers.v1.products` | authenticated | `ProductSalesHistory` |
| GET | `/api/v1/products/{product_id}/serials` | `app.routers.v1.products` | authenticated | `ProductSerials` |

## promotions

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/promotions/active` | `app.routers.v1.promotions` | authenticated | `list` |
| GET | `/api/v1/promotions/coupon-report` | `app.routers.v1.promotions` | authenticated | `CouponReportOut` |
| PUT | `/api/v1/promotions/{promotion_id}` | `app.routers.v1.promotions` | authenticated | `PromotionOut` |

## quotes

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/quotes/{quote_id}` | `app.routers.v1.quotes` | authenticated | `QuoteOut` |
| POST | `/api/v1/quotes/{quote_id}/cancel` | `app.routers.v1.quotes` | authenticated | `QuoteOut` |
| POST | `/api/v1/quotes/{quote_id}/convert` | `app.routers.v1.quotes` | authenticated | `QuoteOut` |
| POST | `/api/v1/quotes/{quote_id}/payments` | `app.routers.v1.quotes` | authenticated | `QuoteOut` |
| GET | `/api/v1/quotes/{quote_id}/pdf` | `app.routers.v1.quotes` | authenticated | `` |

## reach

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/reach/campaigns` | `reach.router` | authenticated | `list` |
| POST | `/api/v1/reach/campaigns` | `reach.router` | authenticated | `CampaignOut` |
| POST | `/api/v1/reach/campaigns/preview` | `reach.router` | authenticated | `PreviewOut` |
| GET | `/api/v1/reach/campaigns/{campaign_id}` | `reach.router` | authenticated | `CampaignOut` |
| POST | `/api/v1/reach/campaigns/{campaign_id}/cancel` | `reach.router` | authenticated | `CampaignOut` |
| POST | `/api/v1/reach/campaigns/{campaign_id}/pause` | `reach.router` | authenticated | `CampaignOut` |
| POST | `/api/v1/reach/campaigns/{campaign_id}/resume` | `reach.router` | authenticated | `CampaignOut` |
| GET | `/api/v1/reach/channels` | `reach.router` | authenticated | `list` |
| PUT | `/api/v1/reach/channels` | `reach.router` | authenticated | `ChannelOut` |
| POST | `/api/v1/reach/channels/{channel}/test` | `reach.router` | authenticated | `ChannelOut` |
| GET | `/api/v1/reach/connections` | `reach.router` | authenticated | `list` |
| POST | `/api/v1/reach/connections` | `reach.router` | authenticated | `ConnectionOut` |
| POST | `/api/v1/reach/connections/{connection_id}/connect` | `reach.router` | authenticated | `ConnectionOut` |
| POST | `/api/v1/reach/connections/{connection_id}/disconnect` | `reach.router` | authenticated | `ConnectionOut` |
| POST | `/api/v1/reach/connections/{connection_id}/status` | `reach.router` | authenticated | `ConnectionOut` |
| GET | `/api/v1/reach/credits` | `reach.router` | authenticated | `CreditOut` |
| GET | `/api/v1/reach/credits/transactions` | `reach.router` | authenticated | `list` |
| GET | `/api/v1/reach/customers` | `reach.router` | authenticated | `list` |
| GET | `/api/v1/reach/messages` | `reach.router` | authenticated | `list` |
| GET | `/api/v1/reach/overview` | `reach.router` | authenticated | `OverviewOut` |
| PUT | `/api/v1/reach/prices` | `reach.router` | authenticated | `dict` |
| GET | `/api/v1/reach/templates` | `reach.router` | authenticated | `list` |
| PUT | `/api/v1/reach/templates` | `reach.router` | authenticated | `TemplateOut` |
| DELETE | `/api/v1/reach/templates/{template_id}` | `reach.router` | authenticated | `` |
| POST | `/api/v1/reach/webhooks/evolution/{webhook_key}` | `reach.router` | public | `dict` |

## ready

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/ready` | `app.main` | public | `` |

## recipes

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/recipes/modifier-options/{option_id}` | `app.routers.v1.recipes` | authenticated | `ModifierRecipeOut` |
| PUT | `/api/v1/recipes/modifier-options/{option_id}` | `app.routers.v1.recipes` | authenticated | `ModifierRecipeOut` |
| GET | `/api/v1/recipes/variance` | `app.routers.v1.recipes` | authenticated | `UsageVarianceReport` |
| DELETE | `/api/v1/recipes/{product_id}` | `app.routers.v1.recipes` | authenticated | `` |
| GET | `/api/v1/recipes/{product_id}` | `app.routers.v1.recipes` | authenticated | `RecipeOut` |
| PUT | `/api/v1/recipes/{product_id}` | `app.routers.v1.recipes` | authenticated | `RecipeOut` |
| POST | `/api/v1/recipes/{product_id}/preview` | `app.routers.v1.recipes` | authenticated | `RecipeOut` |

## redoc

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/redoc` (hidden) | `fastapi.applications` | public | `` |

## rentals

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/rentals/customers` | `app.routers.v1.rentals` | authenticated | `list` |
| GET | `/api/v1/rentals/products` | `app.routers.v1.rentals` | authenticated | `list` |
| PUT | `/api/v1/rentals/products/{product_id}` | `app.routers.v1.rentals` | authenticated | `RentalPolicyOut` |
| POST | `/api/v1/rentals/quote` | `app.routers.v1.rentals` | authenticated | `RentalQuote` |
| GET | `/api/v1/rentals/summary` | `app.routers.v1.rentals` | authenticated | `RentalSummary` |
| GET | `/api/v1/rentals/{rental_id}` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| GET | `/api/v1/rentals/{rental_id}/agreement` | `app.routers.v1.rentals` | authenticated | `AgreementOut` |
| POST | `/api/v1/rentals/{rental_id}/cancel` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/extend` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/handover` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/payments` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/ready` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/release` | `app.routers.v1.rentals` | authenticated | `RentalOut` |
| POST | `/api/v1/rentals/{rental_id}/return` | `app.routers.v1.rentals` | authenticated | `RentalOut` |

## reorders

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/reorders/occurrences` | `app.routers.v1.reorders` | authenticated | `list` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/complete` | `app.routers.v1.reorders` | authenticated | `OccurrenceOut` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/link` | `app.routers.v1.reorders` | authenticated | `OccurrenceOut` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/order` | `app.routers.v1.reorders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/retry-notification` | `app.routers.v1.reorders` | authenticated | `OccurrenceOut` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/skip` | `app.routers.v1.reorders` | authenticated | `OccurrenceOut` |
| POST | `/api/v1/reorders/occurrences/{occurrence_id}/snooze` | `app.routers.v1.reorders` | authenticated | `OccurrenceOut` |
| GET | `/api/v1/reorders/plans` | `app.routers.v1.reorders` | authenticated | `list` |
| POST | `/api/v1/reorders/plans` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| GET | `/api/v1/reorders/plans/{plan_id}` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| PATCH | `/api/v1/reorders/plans/{plan_id}` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| POST | `/api/v1/reorders/plans/{plan_id}/archive` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| POST | `/api/v1/reorders/plans/{plan_id}/pause` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| POST | `/api/v1/reorders/plans/{plan_id}/resume` | `app.routers.v1.reorders` | authenticated | `PlanOut` |
| GET | `/api/v1/reorders/summary` | `app.routers.v1.reorders` | authenticated | `SummaryOut` |

## repair

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/repair/approve/{token}` | `app.routers.repair_public` | public | `` |
| POST | `/repair/approve/{token}` | `app.routers.repair_public` | public | `` |

## repairs

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/repairs/board` | `app.routers.v1.repair_workshop` | authenticated | `RepairBoard` |
| GET | `/api/v1/repairs/devices` | `app.routers.v1.repairs` | authenticated | `list` |
| GET | `/api/v1/repairs/lookup` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| GET | `/api/v1/repairs/matches` | `app.routers.v1.repairs` | authenticated | `list` |
| GET | `/api/v1/repairs/{ticket_id}` | `app.routers.v1.repairs` | authenticated | `RepairDetail` |
| PATCH | `/api/v1/repairs/{ticket_id}` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/approval` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/approval/request` | `app.routers.v1.repair_workshop` | authenticated | `ApprovalSent` |
| POST | `/api/v1/repairs/{ticket_id}/attachments` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/attachments/json` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| DELETE | `/api/v1/repairs/{ticket_id}/attachments/{attachment_id}` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| GET | `/api/v1/repairs/{ticket_id}/attachments/{attachment_id}` | `app.routers.v1.repair_workshop` | authenticated | `` |
| POST | `/api/v1/repairs/{ticket_id}/deposits` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/deposits/{deposit_id}/refund` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/invoice` | `app.routers.v1.repairs` | authenticated | `RepairDetail` |
| GET | `/api/v1/repairs/{ticket_id}/job-card` | `app.routers.v1.repair_workshop` | authenticated | `JobCardFile` |
| GET | `/api/v1/repairs/{ticket_id}/job-card.pdf` | `app.routers.v1.repair_workshop` | authenticated | `` |
| POST | `/api/v1/repairs/{ticket_id}/lines` | `app.routers.v1.repairs` | authenticated | `RepairDetail` |
| DELETE | `/api/v1/repairs/{ticket_id}/lines/{line_id}` | `app.routers.v1.repairs` | authenticated | `RepairDetail` |
| GET | `/api/v1/repairs/{ticket_id}/passcode` | `app.routers.v1.repair_workshop` | authenticated | `PasscodeOut` |
| POST | `/api/v1/repairs/{ticket_id}/pickup` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |
| POST | `/api/v1/repairs/{ticket_id}/status` | `app.routers.v1.repairs` | authenticated | `RepairDetail` |
| GET | `/api/v1/repairs/{ticket_id}/workshop` | `app.routers.v1.repair_workshop` | authenticated | `RepairDetail` |

## replenishment

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/replenishment/events` | `app.routers.v1.replenishment` | authenticated | `list` |
| POST | `/api/v1/replenishment/events` | `app.routers.v1.replenishment` | authenticated | `list` |
| DELETE | `/api/v1/replenishment/events/{event_id}` | `app.routers.v1.replenishment` | authenticated | `list` |
| POST | `/api/v1/replenishment/runs` | `app.routers.v1.replenishment` | authenticated | `RunOut` |
| GET | `/api/v1/replenishment/runs/latest` | `app.routers.v1.replenishment` | authenticated | `` |
| POST | `/api/v1/replenishment/runs/{run_id}/accept` | `app.routers.v1.replenishment` | authenticated | `AcceptResult` |
| POST | `/api/v1/replenishment/suggestions/{suggestion_id}/dismiss` | `app.routers.v1.replenishment` | authenticated | `RunOut` |
| GET | `/api/v1/replenishment/suppliers` | `app.routers.v1.replenishment` | authenticated | `list` |
| PUT | `/api/v1/replenishment/suppliers/{supplier_id}/lead-time` | `app.routers.v1.replenishment` | authenticated | `list` |
| PUT | `/api/v1/replenishment/suppliers/{supplier_id}/terms` | `app.routers.v1.replenishment` | authenticated | `list` |

## reports

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/reports/cancellations` | `app.routers.v1.reports` | authenticated | `CancellationReport` |
| GET | `/api/v1/reports/management/aged-stock` | `app.routers.v1.management_reports` | authenticated | `AgedStockReport` |
| GET | `/api/v1/reports/management/discounts` | `app.routers.v1.management_reports` | authenticated | `DiscountReport` |
| GET | `/api/v1/reports/management/pnl` | `app.routers.v1.management_reports` | authenticated | `PnlReport` |
| GET | `/api/v1/reports/management/staff` | `app.routers.v1.management_reports` | authenticated | `StaffSalesReport` |
| GET | `/api/v1/reports/management/valuation` | `app.routers.v1.management_reports` | authenticated | `ValuationReport` |
| GET | `/api/v1/reports/management/{report}.csv` | `app.routers.v1.management_reports` | authenticated | `` |
| GET | `/api/v1/reports/size-curve` | `app.routers.v1.reports` | authenticated | `SizeCurveReport` |
| GET | `/api/v1/reports/tips` | `app.routers.v1.reports` | authenticated | `TipReport` |
| GET | `/api/v1/reports/vat` | `app.routers.v1.reports` | authenticated | `VatReport` |
| GET | `/api/v1/reports/vat/export` | `app.routers.v1.reports` | authenticated | `` |

## reservations

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/reservations/availability` | `app.routers.v1.reservations` | authenticated | `AvailabilityOut` |
| GET | `/api/v1/reservations/customers` | `app.routers.v1.reservations` | authenticated | `list` |
| GET | `/api/v1/reservations/settings` | `app.routers.v1.reservations` | authenticated | `ReservationSettingsOut` |
| PUT | `/api/v1/reservations/settings` | `app.routers.v1.reservations` | authenticated | `ReservationSettingsOut` |
| GET | `/api/v1/reservations/tables/{table_id}/history` | `app.routers.v1.reservations` | authenticated | `TableHistoryOut` |
| POST | `/api/v1/reservations/tables/{table_id}/release` | `app.routers.v1.reservations` | authenticated | `TableHistoryOut` |
| POST | `/api/v1/reservations/walk-ins` | `app.routers.v1.reservations` | authenticated | `SeatResult` |
| GET | `/api/v1/reservations/{reservation_id}` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| PATCH | `/api/v1/reservations/{reservation_id}` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/arrive` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/cancel` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/confirm` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/no-show` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/reject` | `app.routers.v1.reservations` | authenticated | `ReservationOut` |
| POST | `/api/v1/reservations/{reservation_id}/seat` | `app.routers.v1.reservations` | authenticated | `SeatResult` |

## returns

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/returns/analytics` | `app.routers.v1.returns` | authenticated | `ReturnsAnalytics` |
| GET | `/api/v1/returns/receipts/{code}` | `app.routers.v1.returns` | authenticated | `ReceiptOut` |
| GET | `/api/v1/returns/{return_id}` | `app.routers.v1.returns` | authenticated | `ReturnOut` |
| GET | `/api/v1/returns/{return_id}/credit-note.pdf` | `app.routers.v1.returns` | authenticated | `` |

## roles

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/roles/permissions` | `app.routers.v1.roles` | authenticated | `list` |
| DELETE | `/api/v1/roles/{role_id}` | `app.routers.v1.roles` | public | `` |
| PATCH | `/api/v1/roles/{role_id}` | `app.routers.v1.roles` | public | `RoleOut` |

## sales

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/sales/{sale_id}` | `app.routers.v1.sales` | authenticated | `SaleOut` |
| GET | `/api/v1/sales/{sale_id}/gift-receipt.pdf` | `app.routers.v1.sales` | authenticated | `` |
| GET | `/api/v1/sales/{sale_id}/invoice.pdf` | `app.routers.v1.sales` | authenticated | `` |

## sales-orders

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/sales-orders/backorders` | `app.routers.v1.sales_orders` | authenticated | `list` |
| GET | `/api/v1/sales-orders/deliveries/{note_id}` | `app.routers.v1.sales_orders` | authenticated | `DeliveryNoteOut` |
| POST | `/api/v1/sales-orders/deliveries/{note_id}/deliver` | `app.routers.v1.sales_orders` | authenticated | `DeliveryNoteOut` |
| GET | `/api/v1/sales-orders/deliveries/{note_id}/pdf` | `app.routers.v1.sales_orders` | authenticated | `` |
| POST | `/api/v1/sales-orders/from-quote/{quote_id}` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| GET | `/api/v1/sales-orders/pick-lists/{pick_id}/pdf` | `app.routers.v1.sales_orders` | authenticated | `` |
| GET | `/api/v1/sales-orders/{order_id}` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| PATCH | `/api/v1/sales-orders/{order_id}` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/allocate` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/cancel` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/cancel-lines` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/close` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/confirm` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| POST | `/api/v1/sales-orders/{order_id}/dispatch` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |
| GET | `/api/v1/sales-orders/{order_id}/pdf` | `app.routers.v1.sales_orders` | authenticated | `` |
| POST | `/api/v1/sales-orders/{order_id}/pick` | `app.routers.v1.sales_orders` | authenticated | `SalesOrderOut` |

## serials

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/serials/search` | `app.routers.v1.serials` | authenticated | `SerialSearchOut` |

## settings

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| PUT | `/api/v1/settings/appearance` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |
| GET | `/api/v1/settings/country-tax/{code}` | `app.routers.v1.settings` | public | `dict` |
| PUT | `/api/v1/settings/currency` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |
| GET | `/api/v1/settings/exchange-rates` | `app.routers.v1.settings` | authenticated | `RateBoard` |
| GET | `/api/v1/settings/exchange-rates/convert` | `app.routers.v1.settings` | authenticated | `ConvertResult` |
| PUT | `/api/v1/settings/modules` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |
| PUT | `/api/v1/settings/pos-policy` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |
| PUT | `/api/v1/settings/profile` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |
| GET | `/api/v1/settings/receipt` | `app.routers.v1.settings` | authenticated | `ReceiptProfileOut` |
| PUT | `/api/v1/settings/receipt` | `app.routers.v1.settings` | authenticated | `ReceiptProfileOut` |
| PUT | `/api/v1/settings/tax` | `app.routers.v1.settings` | authenticated | `BusinessSettingsOut` |

## shifts

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/shifts/{shift_id}` | `app.routers.v1.shifts` | authenticated | `ShiftOut` |

## signup

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/signup/availability/email` | `app.routers.signup` | public | `AvailabilityResult` |
| POST | `/api/v1/signup/availability/phone` | `app.routers.signup` | public | `AvailabilityResult` |
| POST | `/api/v1/signup/resume` | `app.routers.signup` | public | `SignupStarted` |
| GET | `/api/v1/signup/slug-check` | `app.routers.signup` | public | `SlugCheck` |
| POST | `/api/v1/signup/start` | `app.routers.signup` | public | `SignupStarted` |
| GET | `/api/v1/signup/{request_id}` | `app.routers.signup` | public | `SignupState` |
| POST | `/api/v1/signup/{request_id}/business` | `app.routers.signup` | public | `SignupState` |
| POST | `/api/v1/signup/{request_id}/resend` | `app.routers.signup` | public | `SignupStarted` |
| POST | `/api/v1/signup/{request_id}/retry` | `app.routers.signup` | public | `SignupState` |
| GET | `/api/v1/signup/{request_id}/status` | `app.routers.signup` | public | `SignupState` |
| POST | `/api/v1/signup/{request_id}/store` | `app.routers.signup` | public | `SignupState` |
| POST | `/api/v1/signup/{request_id}/verify` | `app.routers.signup` | public | `SignupState` |

## site

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/site/contact` | `app.routers.v1.site` | public | `SiteContactOut` |

## staff

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/staff/commission-rules` | `app.routers.v1.staff` | authenticated | `list` |
| POST | `/api/v1/staff/commission-rules` | `app.routers.v1.staff` | authenticated | `CommissionRuleOut` |
| PUT | `/api/v1/staff/commission-rules/{rule_id}` | `app.routers.v1.staff` | authenticated | `CommissionRuleOut` |
| GET | `/api/v1/staff/commissions` | `app.routers.v1.staff` | authenticated | `CommissionReport` |
| GET | `/api/v1/staff/employees` | `app.routers.v1.staff` | authenticated | `list` |
| PUT | `/api/v1/staff/employees/{user_id}` | `app.routers.v1.staff` | authenticated | `list` |
| GET | `/api/v1/staff/payroll/runs` | `app.routers.v1.staff` | authenticated | `list` |
| POST | `/api/v1/staff/payroll/runs` | `app.routers.v1.staff` | authenticated | `PayrollRunOut` |
| POST | `/api/v1/staff/payroll/runs/{run_id}/finalize` | `app.routers.v1.staff` | authenticated | `PayrollRunOut` |
| PUT | `/api/v1/staff/payroll/runs/{run_id}/lines/{line_id}` | `app.routers.v1.staff` | authenticated | `PayrollRunOut` |
| POST | `/api/v1/staff/payroll/runs/{run_id}/recalculate` | `app.routers.v1.staff` | authenticated | `PayrollRunOut` |
| GET | `/api/v1/staff/payroll/runs/{run_id}/wps.sif` | `app.routers.v1.staff` | authenticated | `` |
| GET | `/api/v1/staff/payroll/settings` | `app.routers.v1.staff` | authenticated | `` |
| PUT | `/api/v1/staff/payroll/settings` | `app.routers.v1.staff` | authenticated | `PayrollSettings` |

## store-credits

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/store-credits/{code}` | `app.routers.v1.store_credits` | authenticated | `StoreCreditOut` |

## stores

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| PATCH | `/api/v1/stores/{store_id}` | `app.routers.v1.stores` | authenticated | `StoreOut` |
| GET | `/api/v1/stores/{store_id}/tax` | `app.routers.v1.stores` | authenticated | `BranchTaxOut` |
| PUT | `/api/v1/stores/{store_id}/tax` | `app.routers.v1.stores` | authenticated | `BranchTaxOut` |
| POST | `/api/v1/stores/{store_id}/tax/preview` | `app.routers.v1.stores` | authenticated | `dict` |

## super-admin

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/super-admin/auth/login` | `app.routers.super_admin` | public | `ConsoleSession` |
| PATCH | `/api/v1/super-admin/billing/addons/{addon_id}` | `app.routers.super_admin` | public | `AddonOut` |
| GET | `/api/v1/super-admin/billing/bank-accounts` | `app.routers.super_admin` | authenticated | `list` |
| POST | `/api/v1/super-admin/billing/bank-accounts` | `app.routers.super_admin` | public | `BankAccountOut` |
| PATCH | `/api/v1/super-admin/billing/bank-accounts/{account_id}` | `app.routers.super_admin` | public | `BankAccountOut` |
| GET | `/api/v1/super-admin/billing/catalog` | `app.routers.super_admin` | authenticated | `CatalogOut` |
| PATCH | `/api/v1/super-admin/billing/cycles/{cycle_id}` | `app.routers.super_admin` | public | `CycleOut` |
| PATCH | `/api/v1/super-admin/billing/fees/{fee_id}` | `app.routers.super_admin` | public | `FeeOut` |
| GET | `/api/v1/super-admin/billing/grace` | `app.routers.super_admin` | authenticated | `dict` |
| PUT | `/api/v1/super-admin/billing/grace` | `app.routers.super_admin` | public | `dict` |
| APIWebSocketRoute | `/api/v1/super-admin/billing/live` (hidden) | `app.routers.super_admin` | public | `` |
| PATCH | `/api/v1/super-admin/billing/plans/{plan_id}` | `app.routers.super_admin` | public | `PlanOut` |
| GET | `/api/v1/super-admin/billing/review-notices` | `app.routers.super_admin` | public | `list` |
| POST | `/api/v1/super-admin/billing/review-notices/{notice_id}/read` | `app.routers.super_admin` | public | `ReviewNotice` |
| GET | `/api/v1/super-admin/billing/review-summary` | `app.routers.super_admin` | authenticated | `ReviewSummary` |
| GET | `/api/v1/super-admin/billing/transfers` | `app.routers.super_admin` | authenticated | `list` |
| POST | `/api/v1/super-admin/billing/transfers/{transfer_id}/approve` | `app.routers.super_admin` | public | `PaymentOut` |
| GET | `/api/v1/super-admin/billing/transfers/{transfer_id}/receipt` | `app.routers.super_admin` | authenticated | `` |
| POST | `/api/v1/super-admin/billing/transfers/{transfer_id}/reject` | `app.routers.super_admin` | public | `TransferOut` |
| POST | `/api/v1/super-admin/billing/transfers/{transfer_id}/reopen` | `app.routers.super_admin` | public | `TransferOut` |
| POST | `/api/v1/super-admin/billing/transfers/{transfer_id}/revoke` | `app.routers.super_admin` | public | `PaymentOut` |
| GET | `/api/v1/super-admin/change-requests` | `app.routers.super_admin` | public | `list` |
| POST | `/api/v1/super-admin/change-requests/{request_id}/reject` | `app.routers.super_admin` | public | `ConsoleChangeRequest` |
| POST | `/api/v1/super-admin/change-requests/{request_id}/resolve` | `app.routers.super_admin` | public | `ConsoleChangeRequest` |
| GET | `/api/v1/super-admin/hardware/categories` | `app.routers.super_admin` | authenticated | `` |
| POST | `/api/v1/super-admin/hardware/categories` | `app.routers.super_admin` | public | `` |
| PATCH | `/api/v1/super-admin/hardware/categories/{category_id}` | `app.routers.super_admin` | public | `` |
| POST | `/api/v1/super-admin/hardware/deposits` | `app.routers.super_admin` | public | `dict` |
| GET | `/api/v1/super-admin/hardware/items` | `app.routers.super_admin` | authenticated | `` |
| POST | `/api/v1/super-admin/hardware/items` | `app.routers.super_admin` | public | `` |
| PATCH | `/api/v1/super-admin/hardware/items/{item_id}` | `app.routers.super_admin` | public | `` |
| GET | `/api/v1/super-admin/hardware/orders` | `app.routers.super_admin` | authenticated | `` |
| GET | `/api/v1/super-admin/hardware/orders/{order_id}` | `app.routers.super_admin` | authenticated | `` |
| POST | `/api/v1/super-admin/hardware/orders/{order_id}/fulfill` | `app.routers.super_admin` | public | `` |
| GET | `/api/v1/super-admin/mail` | `app.routers.super_admin` | authenticated | `MailSettingsOut` |
| PATCH | `/api/v1/super-admin/mail` | `app.routers.super_admin` | public | `MailSettingsOut` |
| POST | `/api/v1/super-admin/mail/test` | `app.routers.super_admin` | authenticated | `MailTestOut` |
| GET | `/api/v1/super-admin/me` | `app.routers.super_admin` | public | `OperatorOut` |
| GET | `/api/v1/super-admin/modules` | `app.routers.super_admin` | authenticated | `list` |
| GET | `/api/v1/super-admin/modules/business-types` | `app.routers.super_admin` | authenticated | `list` |
| GET | `/api/v1/super-admin/modules/summary` | `app.routers.super_admin` | authenticated | `ModuleSummary` |
| GET | `/api/v1/super-admin/operators` | `app.routers.super_admin` | authenticated | `list` |
| POST | `/api/v1/super-admin/operators` | `app.routers.super_admin` | public | `OperatorOut` |
| PATCH | `/api/v1/super-admin/operators/{operator_id}` | `app.routers.super_admin` | public | `OperatorOut` |
| GET | `/api/v1/super-admin/overview` | `app.routers.super_admin` | authenticated | `OverviewOut` |
| GET | `/api/v1/super-admin/site/contact` | `app.routers.super_admin` | authenticated | `SiteContactOut` |
| PATCH | `/api/v1/super-admin/site/contact` | `app.routers.super_admin` | public | `SiteContactOut` |
| GET | `/api/v1/super-admin/subscriptions` | `app.routers.super_admin` | authenticated | `list` |
| GET | `/api/v1/super-admin/tenants` | `app.routers.super_admin` | public | `list` |
| PATCH | `/api/v1/super-admin/tenants/{tenant_id}` | `app.routers.super_admin` | public | `TenantRow` |
| GET | `/api/v1/super-admin/tenants/{tenant_id}/addon-access` | `app.routers.super_admin` | authenticated | `ConsoleAddonAccessOut` |
| GET | `/api/v1/super-admin/tenants/{tenant_id}/customers` | `app.routers.super_admin` | public | `list` |
| GET | `/api/v1/super-admin/tenants/{tenant_id}/details` | `app.routers.super_admin` | public | `TenantDetail` |
| GET | `/api/v1/super-admin/tenants/{tenant_id}/entitlements` | `app.routers.super_admin` | authenticated | `list` |
| POST | `/api/v1/super-admin/tenants/{tenant_id}/migrate-business-type` | `app.routers.super_admin` | public | `list` |
| POST | `/api/v1/super-admin/tenants/{tenant_id}/migrate-business-type/preflight` | `app.routers.super_admin` | public | `MigrationPreflight` |
| GET | `/api/v1/super-admin/tenants/{tenant_id}/modules` | `app.routers.super_admin` | public | `list` |
| PUT | `/api/v1/super-admin/tenants/{tenant_id}/modules` | `app.routers.super_admin` | public | `list` |
| POST | `/api/v1/super-admin/tenants/{tenant_id}/reach/credits` | `app.routers.super_admin` | public | `dict` |
| POST | `/api/v1/super-admin/tenants/{tenant_id}/refresh-stats` | `app.routers.super_admin` | public | `TenantStatsOut` |
| PUT | `/api/v1/super-admin/tenants/{tenant_id}/subscription` | `app.routers.super_admin` | public | `SubscriptionOut` |

## sync

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/sync/push` | `app.routers.v1.sync` | authenticated | `SyncPushResponse` |

## tenant

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/tenant/change-requests` | `app.routers.v1.tenant` | authenticated | `list` |
| POST | `/api/v1/tenant/change-requests` | `app.routers.v1.tenant` | authenticated | `ChangeRequestOut` |
| GET | `/api/v1/tenant/modules` | `app.routers.v1.tenant` | authenticated | `TenantModulesOut` |
| GET | `/api/v1/tenant/profile` | `app.routers.v1.tenant` | authenticated | `TenantProfileOut` |

## terminals

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/terminals/activate` | `app.routers.v1.terminals` | public | `TerminalActivation` |

## timesheets

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/timesheets/approve` | `app.routers.v1.timesheets` | authenticated | `dict` |
| POST | `/api/v1/timesheets/entries` | `app.routers.v1.timesheets` | authenticated | `dict` |
| PUT | `/api/v1/timesheets/entries/{entry_id}` | `app.routers.v1.timesheets` | authenticated | `dict` |

## track

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/track/{token}` | `app.routers.repair_public` | public | `` |

## trade-ins

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/trade-ins/check` | `app.routers.v1.trade_ins` | authenticated | `TradeInCheckOut` |
| POST | `/api/v1/trade-ins/{trade_in_id}/cancel` | `app.routers.v1.trade_ins` | authenticated | `TradeInOut` |

## units

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/units/{unit_id}` | `app.routers.v1.units` | authenticated | `` |
| PATCH | `/api/v1/units/{unit_id}` | `app.routers.v1.units` | authenticated | `UnitOut` |

## users

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/users/register-staff` | `app.routers.v1.users` | authenticated | `list` |
| DELETE | `/api/v1/users/{user_id}` | `app.routers.v1.users` | public | `` |
| GET | `/api/v1/users/{user_id}` | `app.routers.v1.users` | public | `UserOut` |
| PATCH | `/api/v1/users/{user_id}` | `app.routers.v1.users` | public | `UserOut` |
| POST | `/api/v1/users/{user_id}/password` | `app.routers.v1.users` | public | `UserOut` |
| POST | `/api/v1/users/{user_id}/pin` | `app.routers.v1.users` | public | `UserOut` |

## warranties

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/warranties/lookup` | `app.routers.v1.warranties` | authenticated | `` |
| GET | `/api/v1/warranties/plans` | `app.routers.v1.warranties` | authenticated | `list` |
| POST | `/api/v1/warranties/plans` | `app.routers.v1.warranties` | authenticated | `list` |
| GET | `/api/v1/warranties/policies` | `app.routers.v1.warranties` | authenticated | `list` |
| POST | `/api/v1/warranties/policies` | `app.routers.v1.warranties` | authenticated | `list` |
| PUT | `/api/v1/warranties/policies/{policy_id}` | `app.routers.v1.warranties` | authenticated | `list` |

## ws

| Method | Path | Module | Auth | Response |
| --- | --- | --- | --- | --- |
| APIWebSocketRoute | `/api/v1/ws/live` (hidden) | `app.routers.v1.live_socket` | public | `` |
| APIWebSocketRoute | `/api/v1/ws/stores/{store_id}/tables` (hidden) | `app.routers.v1.fnb_table_orders` | public | `` |
