# AxizPOS Business (mobile)

Native business portal for owners, managers and staff. It lives in `apps/mobile` and talks to the existing FastAPI backend. It does not replace the web portal or the register's offline sales database.

## Run

```bash
pnpm dev:mobile
```

Copy `apps/mobile/.env.example` to `apps/mobile/.env` and set `EXPO_PUBLIC_API_BASE_URL`. The store code typed at sign-in is sent as `X-Tenant-Domain`, the same way the web portal does when it is not on a store subdomain.

Expo SDK 58 expects Node 22.13, 24.3, or 26+. This workspace's `.npmrc` is `engine-strict`, so a Node 25 machine needs:

```bash
pnpm install --config.engine-strict=false
```

## What was migrated

Every staff route in `apps/web/src/App.tsx` is a module in `src/modules/catalog.ts`. The test `src/modules/catalog.test.ts` fails if one of those routes disappears from the catalog. Each module keeps its permission, capability and business-profile gate from `apps/web/src/components/layout/navigation.ts`.

Navigation is five tabs: Home, Business, Inventory, Finance, More. Tabs open a directory. A directory opens a stack screen that loads the live API. Tablets keep the list and the open record side by side.

| Area | Portal routes | Mobile behaviour |
| --- | --- | --- |
| Home | `/`, `/insights`, `/sales-insights`, `/assistant`, `/m` | Dashboard KPIs from `GET /api/v1/analytics/summary`. Other screens list the live payload. |
| Customers and sales | customers, sales, returns, payments, promotions, store credit, gift cards, margin, shifts, quotes, sales orders, deliveries, reorders, cheques, consignment | Live lists, search, and record detail. Customer create and contact update post to `/api/v1/customers`. While live capabilities include `b2b_credit`, the phone can post cash, card, or transfer payments, a credit hold, and a statement send. Cheque payments stay on the portal. |
| Inventory | stock, products, categories, brands, models, units, pricing, price lists, purchase orders, batches, suppliers, replenishment, counts, transfers, movements, expiry, waste, serials, markdowns, size matrix, modifiers, meals, floor, reservations, kitchen, recipes | Live lists. Product create can include opening stock, a library photo, and name/price/PLU update. Barcode lookup uses `/api/v1/products/search`. Supplier create, purchase-order create, place / receive remaining non-serialized lines / cancel, and stock adjustment (online only, idempotent `adjustment_id`, branch picker when the user is not pinned to a store). Stock can be filtered by the API status values. Variants and serialized setup stay on the portal. |
| Finance | payables, unbilled receipts, supplier payments, expenses, accounting, journals, bank, VAT, exports, management, cancellations, deep analytics, tips, e-invoicing | Live reports. Date range is required where the API requires `from` and `to`. Expense create, void, petty-cash top-up, and petty-cash count post to `/api/v1/expenses`. Approvals can be approved or declined. |
| AxizReach | `/reach` | Overview, connections, campaigns, AI agent, conversations, templates, automations, action center, outbox, analytics, credits, channel settings. Connection status refresh posts to the existing connect status endpoint. |
| Administration | users, roles, employees, timesheets, payroll, settings, stores, add-ons, registers, currencies, channels, delivery, audit, account | Live reads. Account can turn on biometric unlock for the session already in secure storage. |

These portal flows are not staff sessions, so they are not screens inside the signed-in app:

- `/signup` provisions a tenant before any user exists. Set `EXPO_PUBLIC_SIGNUP_URL` when a mobile signup handoff is approved.
- `/kds` and `/table` sign in with a device token. Kitchen stations are still listed for staff at `/inventory/kitchen`.

The portal does not contain a separate projects module or a fixed-asset register. Staff, timesheets and payroll are the HR screens that exist today.

## Architecture

```
src/app            Expo Router stacks and tabs
src/components     Shared buttons, inputs, cards, lists, sheets, charts
src/theme          Brand tokens. Primary #F26A21, charcoal #222026, canvas #F7F8FA
src/hooks          Window size, breakpoints, safe area, keyboard, spacing
src/api            Fetch client, 401 refresh, error envelope, read cache
src/auth           SecureStore session. Tokens are not written to AsyncStorage
src/modules        Screen inventory, permissions, row shaping
src/features       Login, dashboard, records, AxizReach, design system
```

State: TanStack Query for server data, the auth context for the session, business settings for currency, capabilities and the accent colour. The home screen shows the tenant's business-type label from the same profile presets the API uses. Enabled modules still come from the live capability list, not from the preset. Forms use React Hook Form and Zod. Large lists use FlashList. Tokens stay in `expo-secure-store` (chunked for Android's entry size). Non-sensitive list responses may be cached in AsyncStorage with the time they were saved. When that cache is shown, or the device is offline, the list is marked saved or offline. Returning online refetches the open list. The last in-app module path is restored after sign-in. Payments, refunds, stock adjustments, purchase receipts and expenses are not queued offline.

## Permissions

`moduleVisible` mirrors the web portal: permission, capability, business profile, business-wide settings, and Super Admin for downloads. The API still enforces authorization. A hidden button is not a security control.

## Builds

`eas.json` has development, staging and production profiles. Replace the staging and production API hosts, the EAS project id in `app.json`, and the App Store Connect app id before submitting. Production builds throw unless `EXPO_PUBLIC_API_BASE_URL` is `https`.

```bash
pnpm --filter @ai-pos/mobile exec expo prebuild
pnpm --filter @ai-pos/mobile exec eas build --platform android --profile production
pnpm --filter @ai-pos/mobile exec eas build --platform ios --profile production
```

iOS compilation needs macOS. Android and iOS binaries were not produced in this workspace.

## Tests

```bash
pnpm --filter @ai-pos/mobile test
pnpm --filter @ai-pos/mobile typecheck
```

Unit tests cover session restore, API error parsing, list shaping, breakpoints, the route inventory, and a permission denial. They do not replace device passes for login, purchase receiving, AxizReach, Arabic layout, or offline reads.

## Parity

`src/modules/parity.ts` classifies each module. A screen that opens is not marked complete.

| Status | Meaning |
| --- | --- |
| native-functional | The screen's own job is done: dashboard summary, account, design showcase. |
| native-partial-write | Live data plus the writes listed below. Other writes on that record stay on the portal. |
| native-read | Live list and detail. No mobile write. |
| specialized-web | Live data only. The editor stays on the portal: floor plan, pricing matrix, journals, bank import, e-invoice submission, proof of delivery, receipt designer inside settings. |
| device-or-public | Kitchen stations are listed. `/kds`, `/table` and `/signup` stay on their existing device or public flows. |

Partial writes: customers (create, contact update, statement when credit is on), products (create, barcode lookup, name/price/PLU), expenses (create, void), purchase orders (create, place, receive non-serialized, cancel), stock (status filter, adjustment), suppliers (create), approvals (approve, decline), AxizReach (connection status refresh).

Business-type defaults, from `PROFILE_PRESETS`. The API capability list is what the app shows:

| Profile | B2B credit in the preset | Can be turned on |
| --- | --- | --- |
| Electronics and wholesale | On | Yes |
| Grocery | Off | Yes |
| Fashion | Off | Yes |
| Restaurant, cafe, quick service | Off | No |

## Brand

The app icon, adaptive icon and splash use the official mark from `apps/web/public/brand/fav-icon.svg` (charcoal `#2B2B2B`, orange `#F26A21`). The mark keeps its original proportions, centered with padding, on white for the store icon and on the app canvas `#F7F8FA` for the splash. The wide wordmark in `logo.svg` is not stretched into the square icon.

## Device layout

Shared screens pad the status bar, the home indicator, and landscape cutouts. Tab screens leave the bottom inset to the tab bar. A wide window (720 points and up, including large-phone landscape and tablets) opens a record beside its list. Phone directories stay one column. Grids use equal percentage tracks with inner padding so a gap cannot spill past the screen. Charts measure their card. Sheets and dialogs scroll inside the safe area and close on the Android back button. Type grows with the system font scale up to 1.5, and line height stays above the glyphs. Arabic sets the root layout direction and field writing direction. The back chevron points toward the back edge.

`src/hooks/breakpoints.test.ts` checks logical sizes for a small iPhone, a standard iPhone, a large iPhone, iPhone landscape, iPad portrait and landscape, small and standard and large Android phones, Android tablets, and a foldable inner screen. These are layout points, not captured screenshots.

### Android

```bash
pnpm --filter @ai-pos/mobile android
```

That runs `expo run:android`. A booted emulator or a USB device is required. Gesture and three-button navigation are covered by the same bottom inset: tab screens keep it on the tab bar, and stack screens pad scroll content and sticky actions. The last debug build on this Windows machine failed while compiling the Sentry native module (`ninja: error: mkdir` under a long pnpm path). No APK was installed, and this session did not capture emulator screenshots.

### iOS

iOS simulator and device builds need macOS and Xcode. They were not run from this Windows workspace.

```bash
pnpm --filter @ai-pos/mobile ios
```

On a Mac, exercise iPhone SE, a standard iPhone, a large iPhone, and an iPad in portrait and landscape, in English and Arabic, with a larger Dynamic Type size. Confirm the status bar, notch or Dynamic Island, and home indicator stay clear of content, and that a form submit stays above the keyboard.

## Remaining limits

- Desktop canvases (floor-plan editing, receipt designer, full campaign composer, bank-statement import, journal entry, e-invoice submission, proof-of-delivery signature) open as live data, not as a copy of the wide web editor.
- Purchase receiving on mobile posts the remaining quantity for lines that are not serialized. Serialized receipt stays on the portal.
- Customer cash, card, and transfer payments, credit hold, and statement send post only while `b2b_credit` is on. Cheque payments stay on the portal. The statement view is hidden when that capability is off.
- Product variants, serialized product setup, serialized purchase receiving, and spreadsheet or invoice import stay on the portal. Opening stock is rejected by the API for serialized products, so the phone create form does not send it for those products.
- Campaign send and conversation reply stay on the portal. The phone does not call Evolution or a local model.
- Push notification registration is not sent to a new backend endpoint. In-app approval and insight data already come from the existing APIs.
- Android and iOS binaries have not been built. `eas.json` still has placeholder API hosts and `app.json` still has `REPLACE_WITH_EAS_PROJECT_ID`.
- Node 25 cannot install Expo 58 while `engine-strict` is on. Use Node 22, 24, or 26 for a reproducible install and for store builds.

## Rollback

Do not ship this client until the API host and store ids are real. Leaving the previous store binary in place is the rollback. This work does not change the API, the web portal, or the Windows register's offline sales database.
