# POS settings redesign acceptance

## What was checked

The laundry preview at `http://127.0.0.1:1421/#/settings` showed the overview with Business settings and System and register settings cards. Search for "printer" left Hardware and peripherals as the only sidebar result and opened `#/settings/hardware`, including the existing printer settings and weighing scale card. Both navigation groups expand. The outer sidebar gear stayed on Settings. Open drawer remained the icon-only navbar button. The bottom line stayed Downtown Flagship · Laundry.

The preview window was about 850px wide, so the settings sidebar started collapsed and could be expanded. Zoom steps at 125%, 150%, and 200%, and the grocery, electronics, fashion, and restaurant tenants, were not switched in that window. They use the same workspace. A currency save was not submitted.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/settings/settingsRoutes.test.ts src/components/shell/settingsEntry.test.ts src/features/laundry/laundryNav.test.tsx src/components/RegisterErrorBoundary.test.tsx`

4 files, 15 tests, 0 failed.

`pnpm exec tsc -p tsconfig.json --noEmit` completed with exit code 0.

## Limits

Business Pro still owns tax, till rules, catalogue, loyalty, modules, integrations, notifications, and the full audit trail. This register shows the values it already has. Laundry production settings are read-only and split into their own routes. There is no new settings API and no simulated save.
