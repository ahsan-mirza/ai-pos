# Payment receipt confirmation

Status: **AUTOMATED CHECKS PASSED. NATIVE ACCEPTANCE NOT RUN.**

Date: 23-11-2026

Pay now asks whether to print after the sale is actually saved. The question is not stored, and the next payment asks again.

## Payment success trigger

The question opens only after `submitCharge` returns `recorded` or `queued`.

It does not open when the charge is still being submitted, when the outcome is `rejected` or `unavailable`, or when a card, QR, or pay-later intent is anything other than `PAID`. A pending, declined, expired, or cancelled provider payment stays blocked by the existing tender plan, and the confirmation helper refuses it even if a recorded outcome is passed in.

`queued` is an accepted tender saved on the register. It asks. It does not offer a PDF, because the API has not accepted the sale yet.

Opening a sale from Bill History, or using the header reprint and gift-receipt buttons, does not ask again. Those paths still call the existing print service directly.

## Receipt confirmation UI

The dialog uses the existing modal backdrop and card. It shows:

- Payment Successful, or Invoice recorded, or Cash on delivery recorded.
- Invoice number.
- Customer name, when the saved receipt has one.
- Payment method.
- Payment received, with the currency from the sale.
- Change due, when the cash tender produced change.
- Remaining balance, amount on account, or payment not yet received, when that amount is above zero.

The actions are **No, Skip** and **Yes, Print Receipt**. Yes is the primary button and takes focus. Escape skips while the question is open, and closes the printer-error panel. Escape does nothing while a print is in progress. The buttons are at least 3.5rem tall and the card scrolls inside the viewport.

## Yes and No

Yes prints the slips captured from the saved receipt. Prices and tax are not calculated again. The print call is the existing `printReceipt` service, with `manual: true` so the old auto-print flag cannot suppress it, and `kickDrawer: false`.

A combined sale prints one slip. An equal guest split prints the output that was selected for that sale: one combined slip, or one slip per share. The choice then resets to combined, as it did before.

No sends no print command, does not start another charge, and does not change the saved payment. The sale stays available for a later reprint or PDF from Bill History and from the header reprint button.

A second Yes while the first print is still claimed is ignored. A retry continues at the first slip that did not print.

## Printer failure and PDF

A failed print shows:

`Receipt printer is unavailable. Your payment was successful, but the receipt could not be printed.`

The panel then offers Retry Print, Download PDF when a desktop sale id was recorded, and Close. The payment is not reversed, the invoice is not marked unpaid, and no second sale is created. A failed print is not reported as a successful print.

Download PDF uses the existing `openDocumentPdf` invoice path. It is offered only when the desktop shell has a recorded sale id. A browser register and a queued offline sale do not offer it.

On a register with no thermal printer, Yes still uses the existing manual path and opens the system print dialog. That path reports the dialog as opened. It is not the unavailable-printer error.

## Split, partial payment, and credit

Split printing follows the receipt output already chosen for the equal guest split. Separate slips are presentation copies of the one saved sale. They are not extra payments.

A partial payment says Payment Successful, shows the amount received, and shows the remaining balance. The saved slip is the one already built for that sale, including its on-account line.

A credit sale with nothing received says Invoice recorded and Amount on account. It does not say Payment received, and it is not marked as a paid receipt. Cash on delivery says the payment has not yet been received. The printed document is still the saved sale snapshot, which already says the amount was not paid.

## Cash drawer

Cash still kicks once, after the tender is accepted and before the question, and only when the existing policy allows it: cash was taken, drawer kick is enabled, and a printer transport is configured. Card, failed, cancelled, and cash-on-delivery sales do not kick.

Yes, No, Retry, and a second call after the kick do not kick again. A failed print does not kick.

## Automatic print setting

Register settings no longer has **Print a receipt after every sale**. That control could print or skip a Pay receipt without asking.

The setting is now **Ask before printing a sale receipt**. It stays on and cannot be turned off. The Yes or No answer is not written back as a default.

The stored `auto_print` value is left in the register printer record so a save of the other printer fields does not wipe it. Pay does not read it. Refund receipts still use that stored flag when they print without `manual`.

## Tests

No API or payment service changed. API tests were not run.

From `apps/desktop`:

`pnpm exec tsc -p tsconfig.json --noEmit`

Exit 0.

`pnpm exec vitest run src/features/checkout/receiptConfirmation.test.tsx src/features/printing/printerSettingsModal.test.tsx src/features/printing/printPolicy.test.ts src/features/restaurant/splitReceipts.test.ts --reporter=dot`

4 files, 33 tests, 0 failed, exit 0. Duration 1.41s.

`receiptConfirmation.test.tsx` is 16 of those tests. They cover cash, card only after `PAID`, failed and cancelled outcomes, a submitted request that is not success, Yes once, No never, a fresh prompt for the next payment, no remembered choice, one dialog across a rerender, a second Yes ignored, the unavailable-printer sentence, PDF only for a recorded desktop sale, retry without another payment, no drawer kick from Print, Skip, or Retry, combined and separate split slips, a partial remaining balance, and a credit or cash-on-delivery document that is not a paid receipt.

The printer settings test covers the replacement copy and that the old sale-print switch is gone. Node printed a localStorage-path warning. It did not fail the run.

## Native acceptance

Not run. No disposable register was opened, no cash or card test payment was taken, and no confirmation, skip, printer-failure, retry, or second-payment screenshot was captured. No production payment account was used. This pass does not claim a physical printer or cash drawer was exercised.

## Known limitations

- The cashier question is covered by desktop tests and the typecheck. It has not been accepted on a running register.
- Refund receipts can still print from the stored `auto_print` flag. Pay cannot.
- PDF download is the existing invoice PDF for a recorded desktop sale. It is not offered for a queued sale or in the browser.
- A register with printer transport set to none opens the system print dialog on Yes. That is the existing manual fallback.
- Bill History and the header reprint button print immediately and do not ask.
- Separate split slips do not repeat every sold line. They show each share of the saved total, as they did before this change.
