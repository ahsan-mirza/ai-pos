# Split receipt output

Status: **PASSED WITH LIMITATIONS**

Date: 22-11-2026

## Reused

`equalShares` in checkout tenders. Item checks still settle as their own sales. An equal guest split is still one sale.

## Added

The equal-split section of Split Checks has a receipt choice:

- One combined receipt, the existing slip.
- Separate receipt for each split.

Separate slips are built after the sale is recorded. Each is titled `Split n of N`, shows only that share of the invoice total, and says it is not a second invoice. The shares sum to the bill total. Tax is not printed again on each slip. The cash drawer kicks only on the first slip, and only when the sale took cash. Later slip failures do not reverse the payment. The choice resets to combined after printing.

## Limits

- The choice changes printing for an equal guest split. It does not merge item checks into one sale, and it does not split one sale into several payments.
- Separate slips do not repeat every menu line, so a line is not shown as if each guest owed the full item.
- Native print was not run.

## Tests

`src/features/restaurant/splitReceipts.test.ts`: 3 passed, exit 0. Combined returns the original document. Three shares of 10500 are 3500, 3500, and 3500.
