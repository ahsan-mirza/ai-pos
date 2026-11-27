# Global DataTable actions menu and filter drawer

Date: 27-11-2026

Status: **PASSED WITH LIMITATIONS**. Nothing was deployed.

The kebab menu and the filter drawer live once, in `@ai-pos/ui`. Business Pro, the register app, and Super Admin import that table. A screen passes its own actions and filters. It does not draw a second menu or a second drawer.

## Shared behaviour

- The Actions column is one three-dot button. The menu lists the actions that role and record state allow, with the existing icon and label. Hidden actions are omitted. Disabled actions stay visible and do not run.
- The menu and the drawer are portalled to `document.body` with fixed placement, so the table's horizontal scroll does not clip them. The menu flips above the row when there is more room, and it follows scroll and resize.
- Search stays in the toolbar and filters as the user types, or on Enter where that screen already searched on Enter. Escape clears the search text.
- Every other table filter opens from the Filter button. Apply writes the draft and returns to page 1 through the existing pagination reset. Close throws the draft away. Clear all restores each filter's cleared value, or the screen's own clear handler when one reset also clears search.
- The Filter button shows a count when a filter is not on its cleared value. Reopening the drawer shows the applied values.
- Dependent filters use the draft: a brand change clears the model, a category change clears the sub-category and the model, and custom date bounds follow the other date.
- Touch targets are at least 2.75rem. Menu items and drawer actions are reachable by keyboard.

## Screens

| Screen | What moved |
| --- | --- |
| Products and menu items | Activate, Deactivate, Delete, Print labels, and Edit. Price, status, brand, and model filters. |
| Stock | Adjust (disabled with the consolidated-stock hint), Reorder levels, Movement history. Store, category, sub-category, brand, model, fashion attributes, and stock status. The raw-stock / menu-availability switch stays on the page because it changes the list. |
| Categories, brands, models | Edit and Delete. Brand search, and the models brand filter. |
| Customers | Statement, Reorders (when the module is on), and Edit. Customer type and Show inactive. |
| Quotations | Open PDF, and Cancel, Take deposit, Make sales order, and Convert to sale when the quote is open and the role allows them. Quote status. |
| Repairs, Business Pro and register | View details. Status, type, received dates, technician, and warranty. The register list treats Active jobs as the cleared status. Jobs / Bench stays on the page. |
| Purchase orders and transfers | Receiving store or branch, and status. |
| Pricing | Category and brand. Bulk update and Save stay beside search. |
| Audit trail | Date range, custom dates, user, branch, action, and Sensitive only. |
| Sales orders | Search and branch. The order-view switch stays on the page because it changes the table. |
| Fulfillment | Search, order view, dates, and branch. View stays in the row menu. |
| Payroll register | Employee search and calculation status. Month, year, and branch stay on the payroll-run form. |
| Registers | Activate, Rotate key, Revoke, and Release on the existing register table. |
| Super Admin tenants, receipts, add-ons, packages, subscriptions, hardware catalogue, hardware orders, hardware products, packages, and enquiries | The same search, filter drawer, and row menu. |

Screens that already had no row buttons and no extra filters, including modules, batches, price lists, and the register's recent-returns list, keep the shared table. The recent-returns chevron is the row-click hint, not a set of actions.

Dialog fields, payroll-run inputs, and fleet assignment selects were left where they were. They are form fields, not table filters.

## Acceptance

| # | Check | Result |
| --- | --- | --- |
| 1 | One shared menu and one shared drawer | PASSED. `RowActionsMenu`, `FilterDrawer`, and `TableToolbar` are exported from `@ai-pos/ui`. Page files pass configuration. |
| 2 | Existing row actions, confirmations, and API calls | PASSED in code review and unit tests. Handlers were moved, not rewritten. |
| 3 | Role and record-state visibility | PASSED in the action config. Hidden and disabled flags match the previous conditions, including consolidated stock, open quotes, revoked tills, and admin-only Super Admin actions. |
| 4 | Filters, dependencies, Apply, Clear all, and Close | PASSED. `packages/ui` DataTable tests cover Apply, Close without Apply, Clear all, and the badge. Brand clears model. Category clears sub-category and model. |
| 5 | Search stays visible | PASSED. The DataTable test and the fulfillment markup test both find the search field with the drawer closed. |
| 6 | Pagination and server filtering | PASSED for the shared reset. Apply and Clear all call `onFiltersCommit`, and the existing `resetKey` / `resetKeys` still return to page 1. |
| 7 | No second copy of the menu or drawer | PASSED. Registers is the only custom table, and it uses `RowActionsMenu` directly. |
| 8 | TypeScript | PASSED. `@ai-pos/ui`, `apps/web`, `apps/desktop`, and `apps/super-admin`. |
| 9 | Tests | PASSED. `@ai-pos/ui` 56 tests, including 4 DataTable tests. Fulfillment board 12 tests. Super Admin page filters 6 tests. Product detail drawer 3 tests. Arabic catalog check passed. |
| 10 | Click-through in the browser | NOT RUN. Business Pro was not being served on port 5173. |
| 11 | 125%, 150%, and 200% zoom | NOT RUN. |
| 12 | Native register click-through | NOT RUN. |

## Tests run

- `packages/ui`: `pnpm exec vitest run` (56 passed)
- `apps/web`: `FulfillmentBoardPage.test.tsx`, `ProductDetailDrawer.test.tsx`
- `apps/super-admin`: `PageFilters.test.tsx`, `HardwareCatalog.test.tsx`
- `pnpm exec tsc -p tsconfig.json --noEmit` in `@ai-pos/ui`, `apps/web`, `apps/desktop`, and `apps/super-admin`
- `node scripts/i18n-check.mjs`
