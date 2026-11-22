# O6 authoritative inventory audit

Traced before allocation code was added. No protected database was opened.

## Authority

`inventory_levels` is one product at one branch: `quantity_on_hand`, `quantity_reserved`, and `available = quantity_on_hand - quantity_reserved`. The model says only `services.inventory` writes quantities.

`stock_movements` is append-only. `quantity` is signed and non-zero. `quantity_after` is branch on-hand after the row.

`move_stock` in `apps/api/app/services/inventory.py` is the write path. A negative quantity is refused when it would pass `available`, unless the caller passes `allow_reserved=True`. `reserve` increases `quantity_reserved` only up to `available`. `release` decreases it. Quotes already hold stock this way.

Creating an allocation does not insert a stock movement and does not change `quantity_on_hand`.

## Stock-changing paths

| Operation | Source | Effect | Respects `available` |
| --- | --- | --- | --- |
| POS sale | `sale_service.record_sale` → `move_stock` `SALE_OUT` | Decrement | Yes |
| POS return | `returns_service.apply_return` → `RETURN_IN` | Increment | Incoming |
| Purchase receive | `inventory.receive_purchase_order` → `PURCHASE_IN` | Increment | Incoming |
| Manual adjustment | `inventory.manual_adjust` → `move_stock` | Either | Yes for removals |
| Transfer create | `inventory.create_transfer` → `reserve` for quantity lines | Holds `quantity_reserved` | Yes |
| Transfer ship | `ship_transfer` releases that transfer hold, then `TRANSFER_OUT` | Decrement | The transfer reserved first |
| Transfer receive | `receive_transfer` → `TRANSFER_IN` | Increment | Incoming |
| Serial status change | `transition_serial` | ±1 | Uses `allow_reserved=True` when a unit leaves in-stock |
| Recipe sale | `recipe_service.consume` after the sale | Ingredient decrement | Through `move_stock` |

Batch rows (`batch_items`) record which purchase lot a movement drew. That is cost history, not a terminal grant. Pharmacy lot status can block a lot. O6 does not change those rules.

Serialized products identify a unit with `serial_numbers`. Weighed products store grams as integers and price per kilogram (`weighed.amount`). There is no separate decimal stock type.

## What O6 adds

`terminal_allocations` and `terminal_allocation_consumptions`. They name who may consume reserved units. The hold itself remains `inventory_levels.quantity_reserved`. The sale still posts one `SALE_OUT` through `move_stock`.
