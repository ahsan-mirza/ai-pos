# POS product and inventory implementation

Date: 22-11-2026

Overall: **PASSED WITH LIMITATIONS**.

| Profile | Result |
| --- | --- |
| Grocery & Supermarket | PASSED WITH LIMITATIONS |
| Electronics & Wholesale | PASSED WITH LIMITATIONS |
| Fashion & Retail | PASSED WITH LIMITATIONS |
| Restaurant & Cafe | PASSED WITH LIMITATIONS |
| Laundry | PASSED WITH LIMITATIONS |

The limitation is the same for the retail profiles: the POS already used the portal product and stock APIs. This pass did not retest those screens in a live window. Restaurant gained menu-item labeling and priced-option save. Modifier editing, recipe editing, and laundry service editing remain portal-only.

## What changed

Restaurant and Cafe inventory uses the existing product record.

- The products tab is labeled **Menu items**. Stock is labeled **Ingredient stock**.
- The create button is **Add menu item**. The drawer title is **New menu item**.
- Prepared dishes can carry two or more named prices (Small and Large, Lunch and Dinner). They are saved with `PUT /api/v1/menu/products/{id}/price-options` after the product create or update. An empty list keeps the single base price. One named price is refused, matching the API rule that a single option is not a variant list.
- Existing active options load when the item is edited.
- Opening stock stays off for a prepared dish. Raw ingredients remain a separate item type.
- Cashiers still lack `portal:inventory_manage`, so the workspace stays hidden. The API rejects a direct create with the same permission.

No new table, migration, or stock writer was added. Offline create stays disabled.

## Acceptance matrix

| Test | Grocery | Electronics | Fashion | Restaurant/Cafe | Laundry |
| --- | --- | --- | --- | --- | --- |
| Product/service listing | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| Create entry | NOT RUN | NOT RUN | NOT RUN | NOT RUN live. Payload helper PASS | NOT APPLICABLE for services in this pass |
| Edit entry | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| Category selection | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT APPLICABLE |
| Pricing | NOT RUN | NOT RUN | NOT RUN | NOT RUN live. Two-option payload PASS | NOT RUN |
| Variants | NOT APPLICABLE unless the matrix capability is on | NOT RUN | NOT RUN | NOT RUN live | NOT APPLICABLE |
| Branch assignment | NOT RUN | NOT RUN | NOT RUN | NOT APPLICABLE for a prepared dish | NOT RUN |
| Inventory view | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| Stock management | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| RBAC | PASS in the tab unit test | PASS in the tab unit test | PASS in the tab unit test | PASS in the tab unit test | PASS in the tab unit test |
| Business Portal consistency | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| Offline behavior | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

Live browser walks of each profile were **NOT RUN**. Automated coverage is the tab gate and the priced-option payload.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/inventory/menuEntry.test.ts src/features/inventory/tabs.test.ts`

And `pnpm exec tsc -p tsconfig.json --noEmit`.

Results:

- `vitest` exit 0. 2 files, 9 tests passed (`menuEntry` 3, `tabs` 6). Duration 1.00s.
- `tsc -p tsconfig.json --noEmit` exit 0.

A full API suite, Rust tests, and a live window walk were not run.

## Remaining phase

Next unresolved work, in order:

1. Modifier group attach and edit inside the menu item drawer, using `PUT /api/v1/menu/products/{id}/modifier-groups`.
2. Recipe line editor using `PUT /api/v1/recipes/{product_id}`, with raw ingredients selected from existing ingredient products. Do not create a second ingredient catalogue.
3. Laundry service create and price edit for users who hold `laundry:catalogue`, without putting services on the stock ledger.
4. A live walk of grocery, electronics, fashion, restaurant, and laundry on isolated tenants, including a cashier API rejection and a branch-scoped manager.

Do not deploy.
