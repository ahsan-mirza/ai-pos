# Expense access and synchronization — acceptance

## Access

Status: **PASSED WITH LIMITATIONS**

The only expense permission is the existing `expenses:manage`. Super Admin already grants and revokes it on the role screen. Store Manager receives it with the other back-office permissions. Cashier does not.

The register hides Expenses without that permission and sends the view back to Checkout. The API still checks the permission. A cashier PIN receives “You do not have permission for this action.” A manager PIN on the register can read the expense list.

Separate view, edit, delete, export, category, and petty-cash keys were not added. They would duplicate `expenses:manage`.

## Synchronization

Status: **PASSED WITH LIMITATIONS**

Both apps read and write `/api/v1/expenses`. An expense saved on the register is the same row Business Pro lists. An expense saved in Business Pro is the same row the register lists. There is no register expense table and no expense event on the sale queue.

Expense recording is online only. If the API cannot be reached, the form says nothing was recorded. The API does not take an idempotency key, so a pending offline expense could be posted twice after reconnect. That queue was not built.

## Not verified in a live session

A signed-in register and a signed-in Business Pro window were not both open, so the same expense was not clicked through in both UIs during this pass. The shared route is the path both screens already use.
