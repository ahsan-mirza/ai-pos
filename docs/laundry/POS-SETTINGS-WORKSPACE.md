# POS settings workspace

The gear in the POS sidebar opens one store settings page for every business profile, including laundry. The route is `#/settings/{section}`. `#/laundry/settings` remains the laundry floor panel and is opened from Laundry floor inside this page.

## Navigation

`SettingsWorkspace` renders a dark secondary sidebar inside the existing POS shell. General expands and collapses. Each item writes its own hash, so refresh and a direct visit keep that section. The laundry floor does not rewrite a `#/settings` hash.

Save currency stays disabled until a different supported currency is selected and the signed-in user is a business-wide administrator (`settings:manage` and no store scope). The confirmation dialog uses `PUT /api/v1/settings/currency`. Cancel closes it and leaves the saved currency unchanged. A failed save does not replace the current currency. Rates come from `GET /api/v1/settings/exchange-rates` and are left blank when that call fails. Convert currency calls `GET /api/v1/settings/exchange-rates/convert` and is labelled as an estimate. Prices are not converted.

## What stays read-only

Branch tax, VAT, till rules, business profile, modules, add-ons, stores, roles, add-on access, registers, downloads, extra currencies, and the audit trail show the values this register already has and say they are managed in Business Pro. Appearance, receipt printer, and staff use the existing register screens. Staff is hidden unless the user can manage staff. Laundry floor is shown only for a laundry profile.

## Files

- `apps/desktop/src/features/settings/SettingsPage.tsx`
- `apps/desktop/src/features/settings/SettingsWorkspace.tsx`
- `apps/desktop/src/features/settings/settingsUi.tsx`
- `apps/desktop/src/features/settings/settingsRoutes.ts`
- `apps/desktop/src/features/settings/CurrencyPanel.tsx`
- `apps/desktop/src/features/settings/AppearancePanel.tsx`
- `apps/desktop/src/components/shell/settingsEntry.ts`
- `apps/desktop/src/features/laundry/LaundryWorkspace.tsx`
- `apps/desktop/src/App.tsx`

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsRoutes.test.ts src/components/shell/settingsEntry.test.ts src/features/laundry/laundryNav.test.tsx src/components/RegisterErrorBoundary.test.tsx`

4 files, 14 tests, 0 failed.

The laundry preview at `http://127.0.0.1:1421` loaded `#/settings/currency` after the gear click and again after refresh. The summary showed Laundry Tenant A, country AE, currency USD, store code laundry-a, and tax number 100000000000003. Nine currency cards rendered with live rates from open.er-api.com. Choosing EUR enabled Save. Cancel left the current currency as USD. Add-ons opened `#/settings/addons` as a Business Pro notice. The navbar Open drawer button still opened the cash drawer dialog. The bottom line stayed Downtown Flagship · Laundry, v0.1.3.

The preview window was about 850px wide, so the settings sidebar started collapsed and could be expanded. Grocery, electronics, fashion, and restaurant were not switched in that laundry tenant. They use the same workspace. A currency save was not submitted.
