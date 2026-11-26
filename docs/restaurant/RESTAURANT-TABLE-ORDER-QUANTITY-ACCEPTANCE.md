# Restaurant and Cafe table-order quantities

Date: 26-11-2026

Overall: **NOT PASSED**

Automated checks for plus, minus, and direct removal passed. The occupied-table screen was not clicked on a register, so the native acceptance in this note was not run. Nothing was deployed.

| Workstream | Result |
| --- | --- |
| Plus on a sent line sends only the extra | Passed |
| Minus stops at the original sent quantity | Passed |
| Unsent plus, minus, and remove | Passed |
| Sent removal without a manager PIN | Passed |
| Served line still needs a manager | Passed |
| Original kitchen ticket left in place | Passed |
| Recipe and stock movements on these edits | Passed (none written) |
| Native occupied-table walk | Not run |
| Offline cancellation of a sent extra | Not run on a device |

## Permission

The cashier who can work the table already holds `pos:orders`. That grant covers adding items, changing an unsent quantity, sending only an extra plate, cancelling that extra, and removing an unsent or unserved line. The register records that cashier's user id, the action, and the time.

`pos:void_sent_item` stays the manager grant. It is still required to void a line the kitchen has marked served (`bumped`), and to cancel a whole order after it has been sent. A user id that does not hold `pos:orders` is rejected with 403. The buttons are not the authorization check.

## Unsent lines

Plus adds one. Minus subtracts one and stops at 1. Remove asks for a short reason and drops the line. No kitchen ticket is created, and no ingredient movement is written. The open order stays open and the table stays occupied.

A repeated request with the same `event_id` returns the quantity already saved.

## Original sent quantity

A line that has been sent keeps its quantity and its kitchen ticket. Plus does not add to that row.

The extra plates are a new order line whose `source_item_id` is the original line, and a new kitchen ticket for that difference only. The panel shows one card:

`net = original sent quantity + live extra quantity`

Minus is disabled while the net equals the original sent quantity. After plus, minus cancels one extra unit. It does not change the original ticket. When the extra line's quantity is greater than one, that line and its own ticket drop by one. When it is one, the extra line is voided and the kitchen is told; the ticket row stays, with `voided_at` set.

If that extra is already served, minus stays disabled. Removing a served line still opens the manager PIN dialog.

The reason stored for a minus step is `[wrong_quantity] Quantity reduced at the table`. Removing a whole unserved sent line asks for a reason on the register and does not ask for a manager PIN. The audit row is `order.void_sent_item` or `order.sent_quantity_decrease`, with the cashier as `user_id` and no approver.

## Kitchen, recipes, and the bill

Each plus fires one new round for the extra quantity. A retry with the same `event_id` does not fire another. A stale revision returns `stale_order`.

These edits do not insert stock movements and do not change `inventory_levels.quantity_on_hand`. `skip_recipe` is copied onto the extra line. Ingredient use still happens when the table is paid, from the quantities that are still live. A voided extra is not on the bill, so it is not deducted. Cancelling a plate does not invent a return of ingredients that were never issued.

The order id, guest count, and open status stay. Open to pay is the sum of the live lines. Paying the table is a separate action.

A sent plus or minus is refused while the register is offline, because the kitchen cannot be told. The order on the register is left as it was.

## Automated results

From `apps/api`, `APP_ENV=test`:

`pytest tests/test_table_quantity.py tests/test_orders.py tests/test_order_cancel.py -q --tb=line`

25 passed, exit 0.

From `apps/desktop`:

`pnpm exec vitest run src/features/orders/tableQuantity.test.ts --reporter=dot`

1 file, 9 tests, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

`ruff check` on the touched API files exit 0.

## Native acceptance

Not run. The steps (open an occupied table, plus from 1 to 2, minus back to 1, remove another sent line with a reason and no PIN, confirm the kitchen ticket and that the table stays occupied) were not clicked on a Restaurant register. No screenshots were taken. The live laundry register was not opened.

## Remaining limitations

- Minus on a sent line records a fixed reason instead of asking the cashier to type one. Remove still asks.
- An extra added before `source_item_id` existed is shown as its own card. New extras fold into the original line.
- A served extra cannot be removed with minus. The manager PIN path remains for that case and for cancelling the whole order.
- Native confirmation on a register is still outstanding.
