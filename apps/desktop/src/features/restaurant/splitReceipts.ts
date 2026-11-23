import type { ReceiptDoc } from "@ai-pos/receipt";
import { equalShares } from "../checkout/tenders";

export type ReceiptOutput = "combined" | "separate";

let output: ReceiptOutput = "combined";

export function receiptOutput(): ReceiptOutput {
  return output;
}

export function setReceiptOutput(next: ReceiptOutput): void {
  output = next;
}

/** Presentation only. The combined slip is unchanged. Separate slips each show one share of the same total. */
export function presentEqualSplit(doc: ReceiptDoc, guests: number, choice: ReceiptOutput): ReceiptDoc[] {
  if (choice !== "separate" || guests < 2) return [doc];
  const shares = equalShares(doc.totalCents, guests);
  return shares.map((amount, index) => ({
    ...doc,
    title: `Split ${index + 1} of ${guests}`,
    titleAr: null,
    lines: [
      {
        name: `Share of ${doc.number}`,
        detail: "This amount is already included in the combined bill. Tax and discounts are not charged again.",
        quantity: 1,
        unitCents: amount,
        totalCents: amount,
      },
    ],
    subtotalCents: amount,
    taxCents: 0,
    totalCents: amount,
    tenders: [],
    changeCents: null,
    qr: null,
    youSavedCents: 0,
    footer: `Split ${index + 1} of ${guests} for invoice ${doc.number}. This slip is not a second invoice.`,
  }));
}

export function duplicateReceipt(doc: ReceiptDoc): ReceiptDoc {
  return {
    ...doc,
    title: "DUPLICATE RECEIPT",
    titleAr: null,
    footer: "DUPLICATE RECEIPT. Reprint only. This does not create a sale, payment, or stock movement.",
  };
}
