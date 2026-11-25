# Supplier expenses and petty cash — acceptance

## Supplier association

Status: **PASSED WITH LIMITATIONS**

`expenses.supplier_id` points at the existing `suppliers` row. The register and Business Pro both send that id. Paid to stays optional text. When Paid to is blank, the supplier name is stored there. A supplier TRN fills a blank tax-invoice TRN. A paid expense does not create an accounts-payable bill.

The supplier page does not yet list that supplier's expenses. The expense list shows the supplier name, and the list API accepts `supplier_id`.

## Petty cash

Status: **PASSED WITH LIMITATIONS**

- Balance is `PettyCash.balance_cents` from `GET /api/v1/expenses/petty-cash/{store_id}`.
- Top up posts amount, source (`bank` or `till`), and note through the existing top-up route.
- Count float shows the book balance, the counted amount, and the difference. Saving calls the existing count route, which posts that difference on the book. The page does not write a balance itself.
- A petty-cash expense is refused by the API when the float is short. The message is shown on the payment-source control.
- Void of a petty-cash expense is the existing reversal entry.

The book on the register shows the latest entries returned by the API, with kind, note, user, expense number, amount, and running balance.

A live top-up was not posted from this register during acceptance, so no production or tenant float was changed. The existing API tests already cover top-up, shortfall, expense, void, and count.
