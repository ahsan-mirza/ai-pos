# Restaurant and Cafe table-order quantities

Date: 25-11-2026

Overall: **PASSED WITH LIMITATIONS**

An occupied table keeps one open order. Adding dishes and changing an unsent quantity write that same order. A line already sent to the kitchen is not rewritten. A larger quantity becomes a new kitchen line for the extra plates only. A smaller quantity is refused; the existing void-with-reason flow still removes the whole sent line. No sale was settled. The live laundry register was not opened.

| Workstream | Result |
| --- | --- |
| Add items to the occupied table | PASSED |
| Unsent quantity adjustment | PASSED |
| Sent quantity increase | PASSED |
| Sent quantity decrease | PASSED WITH LIMITATIONS |
| Kitchen ticket reconciliation | PASSED |
| Inventory reconciliation | NOT RUN |
| Offline support | PASSED WITH LIMITATIONS |
| Native window screenshots | NOT RUN |

## What the order already did

`POST /api/v1/orders/{id}/items` appends lines to the open order and leaves sent lines untouched. A second dine-in order for the same table is rejected with `table_occupied`, and the response names the existing order id.

`POST /api/v1/orders/{id}/items/{item_id}/quantity` changes a line that has not been sent. The quantity must be from 1 to 1000. A sent line returns `already_sent`.

`POST /api/v1/orders/{id}/items/{item_id}/increase` is only for a sent line. The body is the new quantity of that line, not a second copy of the whole ticket. The original line and its kitchen ticket stay at the old quantity. The difference is a new order line, already marked sent, and only that line is fired to the kitchen. Asking for a lower quantity returns `sent_reduction_blocked`.

`POST /api/v1/orders/{id}/send` fires every unsent line once. Sending again with nothing left returns `nothing_to_send`.

Voiding a sent line still requires a reason and a manager who holds `pos:void_sent_item`. There is no partial void. A reduction of a sent line is the full void, then a new line for what the table still wants.

Recipe consumption stays on the sale, not on these open-order edits. Prepared items with `skip_recipe` keep that flag on the extra line. This pass did not replay stock movements.

A sent increase is refused while the register is offline, because the extra ticket cannot be delivered. Adding unsent lines can still queue on the register.

## What changed in the table panel

Unsent lines already had minus and plus. Their status now reads “Not sent to kitchen”. The card shows the unit price, the quantity, and a line total.

A sent line no longer offers a one-step “add one more” button. **Adjust quantity** asks for the new whole quantity. A higher number sends only the extra. The same number, a lower number, and a value outside 1–1000 stay on the register and do not call the kitchen. **Void with reason** is unchanged.

New dishes still go through **Add More Items**, the existing portion and modifier dialogs, and **Add to this order**. They stay unsent until **Send new items to kitchen**. Closing the panel does not close the table.

## API evidence

From the repository root:

`node scripts/python.mjs -m pytest tests/test_orders.py::test_sent_increase_adds_only_the_extra_round tests/test_orders.py::test_occupied_table_reopens_the_same_order -q --tb=line`

2 passed, exit 0.

`test_occupied_table_reopens_the_same_order` keeps one order id, rejects a second order for the table, grows an unsent line from its original quantity to 3, sends it, then adds a later line that stays unsent. Changing the sent line in place returns `already_sent`.

`test_sent_increase_adds_only_the_extra_round` starts from quantity 3. A request for 2 is `sent_reduction_blocked`. A direct quantity edit is `already_sent`. A request for 5 leaves the original line and its kitchen ticket at 3 and writes a new ticket line for 2. The audit action is `order.sent_quantity_increase`.

## Desktop evidence

From `apps/desktop`:

`pnpm exec vitest run src/features/orders/tableQuantity.test.ts --reporter=dot`

1 file, 4 tests, 0 failed, exit 0. Going from 1 to 3 plans an extra of 2. A reduction, an unchanged quantity, and a quantity outside 1–1000 are refused before a request is sent.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

## Examples

Unsent Daal Channa Small Plate, AED 3.00, quantity 2, line total AED 6.00. Plus makes quantity 3 and the line total AED 9.00. The portion id is unchanged. Minus returns it to 2. Quantity 0 is not offered; the minus control stops at 1.

Sent Daal Channa Full Plate, quantity 1. Adjust quantity to 3. The original ticket stays at 1. A new sent line of 2 is added. The open order total counts both lines. Adjust quantity to 1 or 0 does not change the ticket.

## Limitations

- A sent line cannot be reduced by one plate. The cashier voids the whole line with a reason, then adds the quantity the table still wants.
- The extra quantity is its own order line and its own kitchen ticket. The panel lists both lines rather than folding them into one card.
- Native screenshots of the occupied-table panel were not taken in this pass.
- Recipe and stock movements were not replayed. Open-order edits do not write inventory; sale-time recipe consumption is unchanged.
- A sent increase is blocked while offline.
