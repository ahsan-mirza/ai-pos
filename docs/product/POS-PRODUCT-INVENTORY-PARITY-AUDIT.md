# POS product and inventory parity audit

Date: 22-11-2026

Status after the first implementation pass: restaurant menu items and priced options are saved from the POS. Modifier groups, recipe editing, and laundry service editing remain portal-only. See `POS-PRODUCT-INVENTORY-IMPLEMENTATION-ACCEPTANCE.md`.

The Business Portal is `apps/web`. The Desktop POS is `apps/desktop`. Both call the same API in `apps/api`. There is no second product table and no second stock ledger for the POS.

## Shared authority

| Concern | Authority |
| --- | --- |
| Create product | `POST /api/v1/inventory/products` requires `portal:inventory_manage` |
| Update product | `PATCH /api/v1/products/{id}` requires `portal:inventory_manage` |
| Opening stock | Fields `opening_store_id` and `opening_quantity` on create. Not a second call |
| Later stock | `POST /api/v1/inventory/adjust`, purchase receive, transfers, and counts. The POS does not write `quantity_on_hand` |
| Menu prices | `PUT /api/v1/menu/products/{id}/price-options` requires `portal:inventory_manage` |
| Recipes | `PUT /api/v1/recipes/{product_id}` requires `portal:inventory_manage` and the recipes module |
| Laundry services | `/api/v1/laundry/services` requires laundry catalogue permissions. Separate from sellable products |
| Offline product create | Not supported. The POS disables create while offline. Product rows are not written to the sale `sync_queue` |

System roles from the RBAC migration: Cashier holds `pos:access` and `repairs:create`, not `portal:inventory_manage` or `inventory:adjust_stock`. Store Manager holds inventory manage. Super Admin holds the full set, including inventory manage. A cashier therefore does not see the inventory workspace.

## Capability matrix

| Capability | Portal | POS before this pass | API | Permission | Change |
| --- | --- | --- | --- | --- | --- |
| Product list, create, edit, archive | `/inventory/products` | Inventory → Products, `ProductDrawer` | Yes | `portal:inventory_manage` or `pharmacy:catalogue` to open the form | Already shared |
| Categories, brands, units | Yes | Yes, same tabs | Yes | `portal:inventory_manage`; tenant-wide create needs `store_id` null | None |
| Grocery barcode, SKU, weight, FEFO, opening stock | Yes | Yes on the same drawer and expiry/batch tabs | Yes | Inventory manage / `inventory:adjust_stock` for counts | None |
| Electronics models, serials, wholesale price | Yes | Yes when the capability is on | Yes | Inventory manage; serial view is `portal:access` | None |
| Fashion size and colour matrix | Yes | Yes, `generateMatrix` | Yes | Inventory manage | None |
| Stock, branch filter, adjust, movements, counts, transfers, purchase orders | Yes | Yes, same endpoints | Yes | View `portal:access`; adjust `inventory:adjust_stock`; transfers inventory manage | None |
| Restaurant menu item create | Same product form, item type Prepared dish / Raw ingredient / Pre-packaged | Same drawer, but the button said Add product and priced options were sell-time only | Yes | `portal:inventory_manage` | This pass labels it Add menu item and saves priced options |
| Restaurant modifiers, combos, recipe editor | Portal pages | Read-only recipe list. Modifiers are chosen at the till | Yes | `portal:inventory_manage` plus `menu_modifiers` or `recipes` | Not built in this pass |
| Laundry services | Editable catalogue | Read-only catalogue. Physical supplies use Inventory | Yes | `laundry:catalogue` and related production permissions | Not built. Services stay out of grocery stock |
| Cost and valuation | Portal product history | Not a POS screen | Yes | `portal:reports_read` / inventory manage | Not built |

## Profile notes

Grocery, electronics, and fashion already use the portal product payload: name, category, barcode, SKU, tax, image, opening stock, and profile fields such as weighed items, serials, and the fashion matrix. Creating a prepared dish does not post opening stock.

Restaurant menu items are products with `item_type`. Raw ingredients are a different item type, not a second menu product. `pos:skip_recipe` remains a per-line cashier choice and is not a catalogue field.

Laundry order intake is unchanged. Services are not stocked products.

## Offline

Product create, stock adjust, receiving, counts, and transfers require a live API session. The screen says so and disables the write. No local product is inserted that would never sync.
