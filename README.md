# ai-pos

Offline-first point of sale with a FastAPI cloud API, a Tauri cashier, and a web admin dashboard. The workspace is a pnpm Turborepo.

## Prerequisites

- Node.js 20+
- pnpm 10.18.2 (`corepack enable`)
- Python 3.12+
- Rust stable, for the desktop shell
- Docker, for local PostgreSQL

## Bootstrap

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

macOS and Linux:

```bash
./scripts/bootstrap.sh
```

The script installs workspace packages, creates `apps/api/.venv`, creates each app's `.env.development` from its `.env.development.example` (or moves an existing `.env` there, keeping its values), and generates desktop icons. When it creates `apps/api/.env.development` it also replaces the `change-me` secrets (`JWT_SECRET`, `PIN_SALT`, `ENCRYPTION_SECRET`, `API_KEY`, `ADMIN_PASSWORD`, `ADMIN_PIN`) with random values and copies the same `API_KEY` into `apps/desktop/.env.development`. It never touches an existing env file, because rotating `ENCRYPTION_SECRET` or `PIN_SALT` on a live database makes stored IMEIs and PINs unusable.

## Environments

Every app has the same three env files; no app reads a plain `.env`.

| File | Where | Selected by |
| --- | --- | --- |
| `.env.development` | your machine (`localhost`, `demo` tenant) | `pnpm dev:*`, `migrate`, `seed` |
| `.env.dev` | shared dev server, `https://{tenant}.dev.qios.ae` | `APP_ENV=dev`, `vite build --mode dev`, `POS_ENV=dev` |
| `.env.production` | live, `https://{tenant}.qios.ae` | `APP_ENV=production`, `vite build`, `POS_ENV=production` |

- Backend (`apps/api`): all three hold secrets and are gitignored; copy them from `.env.<name>.example`. `node scripts/generate-secrets.mjs --env dev` (or `--env production`) creates the file and fills fresh secrets; set the database credentials by hand. Production refuses to start while any value contains `change-me`, `CONTROL_DATABASE_URL` is unset, or `DEFAULT_TENANT` is set. Tests run with `APP_ENV=test` and read no file.
- Admin and POS: `.env.dev` and `.env.production` hold only public values (Vite inlines them into the bundle) and are committed; `.env.development` is gitignored.
- POS installers bake the activation endpoint (`TENANT_URL_TEMPLATE`, `TENANT_BASE_DOMAIN`) in at compile time and never read the build machine's files. Setting `TENANT_URL_TEMPLATE` on a register PC still overrides it, for LAN testing. The dev installer is a separate app ("AI POS Dev") that installs side by side with the live one.

| Task | Dev server | Production |
| --- | --- | --- |
| Run the API | `pnpm start:backend:dev` | `pnpm start:backend:prod` |
| Migrate every tenant | `pnpm --filter @ai-pos/api migrate:dev` | `pnpm --filter @ai-pos/api migrate:prod` |
| Build the admin portal | `pnpm build:admin:dev` | `pnpm build:admin:prod` |
| Build the POS installer | `pnpm build:pos:dev` | `pnpm build:pos:prod` |

## Run

Skip `docker compose up -d` if PostgreSQL already runs on port 5432; point `DATABASE_URL` in `apps/api/.env.development` at it instead (URL-encode special characters in the password, for example `@` as `%40`).

```bash
docker compose up -d
pnpm --filter @ai-pos/api migrate
pnpm --filter @ai-pos/api seed
pnpm dev
```

- API: `http://localhost:8000` (`/health`, OpenAPI at `/docs`)
- Admin: `http://localhost:5173`
- Cashier UI: `http://localhost:1420`
- Native cashier: `pnpm --filter @ai-pos/desktop tauri:dev`

`pnpm dev` starts the API, admin, and cashier UI. The Tauri shell is separate so Vite is not launched twice.

## Inventory

- Products are one global catalog linked to a category and optional sub-category (`/api/v1/categories`). Stock lives per branch in `inventory_levels` (on hand, reserved, reorder/max levels, shelf location).
- Every stock change goes through `app/services/inventory.py`: sales (`SALE_OUT`), returns (`RETURN_IN`), goods receipts (`PURCHASE_IN`), transfers (`TRANSFER_OUT` on ship, `TRANSFER_IN` on receipt), damage and audit adjustments. Each writes a `stock_movements` row; stock never goes negative.
- IMEI/serial units carry the branch that physically holds them. Selling a unit that sits at another branch is refused until it is transferred.
- Purchase orders (`/api/v1/inventory/purchase-orders`) go draft → ordered → partially received / received through goods receipts at their `destination_store_id`. Transfers (`/api/v1/inventory/transfers`) go requested (stock reserved at the source) → in transit → received.
- Store-bound users only see and change their own branch; global users can pick a branch or view consolidated totals. `GET /api/v1/inventory/availability` is open to registers so cashiers can check other branches.
- Each register sells from the store it was activated for (`STORE_ID` / `VITE_STORE_ID` in `apps/desktop/.env.development` for the legacy developer setup).

## Grocery and restaurant modules

Each business type switches on its own modules (Store Settings → Business profile); routers for a module answer 403 while it is off.

- **Expiry-first stock (`fefo`)**: batches with the soonest expiry sell first; expired stock is flagged, a daily `batch_expiry` job raises alerts, and Inventory → Expiring lists and writes off stock.
- **Weighed items (`weighed_items`)**: stock and sale quantities count grams with prices per kg; registers read serial scales (Tauri `scale.rs`) and price-embedded EAN-13 scale labels.
- **Menu modifiers (`menu_modifiers`)**: option groups (size, milk, extras) priced from the catalogue at sale time; the sale line keeps a snapshot.
- **Open orders and tables (`open_orders`, `tables`)**: tabs shared by every register (`/api/v1/orders`, revision-checked, offline-safe `open_order` sync), a drag-and-snap floor plan (Inventory → Floor plan), move and merge.
- **Kitchen display (`kds`)**: sending an order (or a counter sale) fires one ticket per station, routed by category. The full-screen board runs at `/kds` on the portal, signed in with a register activation key; stations can also print tickets at the sending register.
- **Split bills (`split_bills`)**: by item or seat (one sale per check, the tab closes when every line is paid) or equally between up to 12 guests (one sale, one tender per guest).
- **Tips and service charge (`tips_service_charge`)**: service charge is revenue (taxable if configured); tips are owed to staff (GL 2700), shown per server in the shift report and Finance → Tips & service.
- **Recipes (`recipes`)**: a dish with a recipe draws its ingredients (`RECIPE_OUT`) instead of its own stock, with modifier deltas; Inventory → Recipes shows live cost and margin, and Ingredient usage compares theoretical with actual usage after stock counts.
- **Delivery channels (`delivery_channels`)**: apps post orders to `POST /api/v1/channels/{code}/orders` signed with `X-Channel-Signature: sha256=<HMAC-SHA256 of the body>` (deduplicated by `external_id`), or cashiers key them in. Registers accept (with prep time) or reject them, settle them with the `channel` tender, and Administration → Delivery channels tracks commission, payouts and what each app still owes. Named provider adapters plug into `ChannelAdapter` in `app/services/channel_service.py`.

## Tenant governance and console

- **Business type lock.** Once a store finishes onboarding, its business type is fixed. `PUT /api/v1/settings/profile` answers 409 `business_type_locked` with the IT Support contact (`SUPPORT_EMAIL`, default support@qios.ae). Stores can switch on only the modules that fit their type (`COMPATIBLE` in `app/core/capabilities.py`); `GET /api/v1/tenant/modules` returns the locked type and those modules for Store Settings → Business profile.
- **Change requests.** `POST /api/v1/tenant/change-requests` files a business-type or module request in the control database, with a snapshot of the store's size, and emails support. Single-store servers fall back to a mailto link.
- **Console.** `apps/super-admin` (`pnpm dev:console`, port 5174) is the POS company's own app at `/api/v1/super-admin`, outside tenant resolution:
  - Sign-in uses operator accounts (email, password and an authenticator code) and tokens signed with `CONSOLE_JWT_SECRET`, which must differ from `JWT_SECRET`. Store tokens never open it, and console tokens never open a store.
  - Create staff with `python -m app.tenancy.cli create-operator --email … --name … --role ADMIN|SUPPORT`. It prompts for the password and prints the authenticator key once.
  - Add the console's origin to `CONSOLE_ORIGINS`.
- **Directory and stats.** `GET /tenants` reads the `tenant_stats` snapshot (stores, registers, customers, 30-day sales, database size). Refresh it with `python -m app.tenancy.cli collect-stats` (schedule it daily), the console's Refresh button, or automatically after every override or migration. Customer records are break-glass: each view needs a reason, is audited, and masks contacts unless an ADMIN reveals them.
- **Module overrides.** `PUT /tenants/{id}/modules` forces modules on or off. The control database keeps the record (`tenant_module_overrides`), and the applied copy is written to the store's `business_settings.managed_capabilities`. Requests see the change at once (within 30 seconds on other API workers) and registers on their next sync; stores cannot change managed modules.
- **Business-type migration.** `POST /tenants/{id}/migrate-business-type/preflight` lists the modules gained and lost, blockers (open tabs, on-account balances, open quotes, uncleared cheques, active repairs, consignment stock) and warnings, and signs that exact diff for 15 minutes. The apply endpoint (ADMIN only) needs that token, the store's subdomain typed to confirm, and no blockers. It resolves the linked change request.
- Every console action is written to `operator_audit_log`, and applied changes also go to the store's own audit trail.

## Access control

- `seed` creates the four system roles (Super Admin, Store Manager, Cashier, Technician) and, if the username does not exist yet, the root Super Admin from `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_PIN`. It never overwrites existing credentials.
- Admin portal: `POST /api/v1/auth/login-password` issues a `portal` token. Users need `has_portal_access` and the `portal:access` permission.
- Registers: `POST /api/v1/auth/login-pin` requires the device `X-Api-Key` and issues a `pos` token. Users need `has_pos_access` and `pos:access`. The Tauri shell caches an Argon2 verifier of the PIN after each online unlock so cashiers can unlock offline.
- Accounts lock for `LOGIN_LOCKOUT_MINUTES` after `LOGIN_MAX_ATTEMPTS` failures. Password and PIN resets revoke existing tokens.
- Users can only grant permissions they hold. Store-bound users only see and manage their own store.
- Every synced sale must name a cashier who exists, holds `pos:access`, and belongs to the sale's store (or to every store).
- Demo staff: `pnpm --filter @ai-pos/api seed:demo` adds the roles and users in `packages/catalog/demo-users.json` (skipping usernames that already exist). Set `VITE_SHOW_DEMO_ACCOUNTS=true` in `apps/web/.env.development` and `apps/desktop/.env.development` to list them on the login and unlock screens. Only `vite dev` honors the flag; production builds never include the file.

## Database access

- API code in `apps/api/app` reaches the database only through SQLAlchemy ORM models and `select()` / `update()` / `delete()` on a `Session`. Raw SQL is not allowed.
- `pnpm --filter @ai-pos/api lint` rejects raw-SQL imports (`sqlalchemy.text`, `literal_column`, `sqlite3`, `psycopg`), and `tests/test_no_raw_sql.py` rejects `exec_driver_sql()`, `execute()` with a SQL string, and `sa.text()`.
- The one exception is the SQLite `PRAGMA foreign_keys=ON` in `app/core/database.py`, marked `# raw-sql: allowed (<reason>)`. The marker is only accepted in files allowlisted in that test.
- Alembic migrations (`apps/api/alembic/versions`) are outside the rule: triggers and one-off data fixes may use `op.execute`.

## Layout

- `apps/api` — FastAPI, SQLAlchemy, Alembic. Routers for `/auth`, `/users`, `/roles`, and `/sync`. `POST /api/v1/sync/push` applies a batch in one transaction and treats idempotency keys as replay-safe.
- `apps/desktop` — Tauri 2, React, and SQLite. PIN unlock screen, offline credential cache, and the sale queue. The Rust process holds `API_KEY`.
- `apps/web` — React admin dashboard using the shared Archivo / `#FD3706` / `#222026` tokens, with Users and Roles management.
- `packages/shared-types` — permission enums plus user, role, product, serial, sale, repair, and sync contracts.
- `packages/design-tokens` — brand CSS variables and the Tailwind preset.
- `packages/catalog` — shared demo store and products.

Money is integer cents. IMEIs and serial numbers are encrypted at rest in PostgreSQL.
