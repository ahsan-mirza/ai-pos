import type { ReceiptDoc } from "@ai-pos/receipt";
import { formatMoney } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReceiptConfirmationModal } from "./ReceiptConfirmationModal";
import {
  PRINTER_UNAVAILABLE_MESSAGE,
  applyReceiptChoice,
  buildReceiptPrompt,
  canDownloadReceiptPdf,
  choiceIsRemembered,
  drawerKickOnChoice,
  finishPrint,
  isSettledPayment,
  kickDrawerForCashSale,
  openReceiptPrompt,
  printConfirmationSlips,
  printOptionsForConfirmation,
  shouldAskForReceipt,
  shouldPromptOnHistoryOpen,
  startPrint,
  type ReceiptPrompt,
} from "./receiptConfirmation";

const bill: ReceiptDoc = {
  storeName: "Axiz",
  storeAddress: null,
  storePhone: null,
  legalName: null,
  legalNameAr: null,
  trn: null,
  title: "Receipt",
  titleAr: null,
  number: "INV-9",
  issuedAt: new Date("2026-11-23T08:00:00Z"),
  cashier: "Noor",
  servedBy: null,
  customer: "Layla",
  reference: null,
  lines: [{ name: "Lunch", detail: null, quantity: 1, unitCents: 20790, totalCents: 20790 }],
  subtotalCents: 20790,
  taxCents: 0,
  totalCents: 20790,
  tenders: [{ label: "Cash", amountCents: 20790 }],
  changeCents: null,
  currency: "AED",
  language: "en",
  footer: "Thanks",
  qr: null,
  youSavedCents: 0,
  vatIncluded: false,
};

function payment(patch: Record<string, unknown> = {}) {
  return {
    id: "sale-1",
    outcome: "recorded",
    blocker: null,
    providerStatus: null,
    paidCents: 20790,
    remainingCents: 0,
    changeCents: null,
    totalCents: 20790,
    currency: "AED",
    cod: false,
    invoiceNumber: "INV-9",
    customerName: "Layla",
    methodLabel: "Cash",
    saleId: "sale-1",
    guestCount: 1,
    receiptOutput: "combined" as const,
    pdfAvailable: true,
    ...patch,
  };
}

function prompt(patch: Record<string, unknown> = {}): ReceiptPrompt {
  const built = buildReceiptPrompt(payment(patch), bill);
  if (!built) throw new Error("expected a receipt prompt");
  return built;
}

describe("receipt confirmation after payment", () => {
  it("opens after a successful cash payment", () => {
    const asked = prompt();
    expect(asked.heading).toBe("Payment Successful");
    expect(asked.receivedLabel).toBe("Payment received");
    expect(asked.receivedText).toBe(formatMoney(20790, "AED"));
    expect(asked.methodLabel).toBe("Cash");
    expect(asked.customerName).toBe("Layla");
    expect(asked.invoiceNumber).toBe("INV-9");
    expect(asked.question).toBe("Would you like to print the receipt?");
    expect(asked.paidReceipt).toBe(true);
  });

  it("opens a card payment only after the provider confirms it", () => {
    expect(shouldAskForReceipt({ outcome: "recorded", blocker: "Waiting for the card terminal.", providerStatus: "PENDING" })).toBe(false);
    expect(buildReceiptPrompt(payment({ methodLabel: "Card", providerStatus: "PENDING", blocker: "Waiting for the card terminal." }), bill)).toBeNull();
    expect(buildReceiptPrompt(payment({ methodLabel: "Card", providerStatus: "AUTHORIZED", blocker: null }), bill)).toBeNull();
    expect(prompt({ methodLabel: "Card", providerStatus: "PAID" }).methodLabel).toBe("Card");
  });

  it("does not open after a failed or cancelled payment", () => {
    expect(isSettledPayment("submitted")).toBe(false);
    expect(isSettledPayment("recorded")).toBe(true);
    expect(isSettledPayment("queued")).toBe(true);
    expect(buildReceiptPrompt(payment({ outcome: "rejected" }), bill)).toBeNull();
    expect(buildReceiptPrompt(payment({ outcome: "unavailable" }), bill)).toBeNull();
    expect(buildReceiptPrompt(payment({ outcome: "cancelled" }), bill)).toBeNull();
    expect(buildReceiptPrompt(payment({ outcome: "recorded", providerStatus: "CANCELLED", blocker: null }), bill)).toBeNull();
    expect(buildReceiptPrompt(payment({ outcome: "recorded", providerStatus: "DECLINED", blocker: "Send the amount to the card terminal." }), bill)).toBeNull();
  });

  it("prints once for Yes and not at all for No", async () => {
    const idle = { printing: false, attempts: 0, payments: 1 };
    const skipped = applyReceiptChoice("no", idle);
    expect(skipped.print).toBe(false);
    expect(skipped.gate).toEqual(idle);

    const accepted = applyReceiptChoice("yes", idle);
    expect(accepted.print).toBe(true);
    const calls: { kickDrawer: boolean; manual?: boolean }[] = [];
    const result = await printConfirmationSlips([bill], async (_slip, options) => {
      calls.push(options);
      return { printed: true, message: null };
    });
    expect(result.error).toBeNull();
    expect(calls).toEqual([printOptionsForConfirmation()]);
    expect(accepted.gate.payments).toBe(1);
  });

  it("asks again for the next payment and does not remember Yes or No", () => {
    expect(choiceIsRemembered()).toBe(false);
    const first = prompt({ id: "sale-1" });
    const second = prompt({ id: "sale-2", invoiceNumber: "INV-10" });
    expect(openReceiptPrompt(first, second)?.id).toBe("sale-2");
    expect(second.heading).toBe("Payment Successful");
    expect(second.question).toBe(first.question);
  });

  it("keeps a single dialog when the same payment renders again", () => {
    const open = prompt();
    expect(openReceiptPrompt(open, { ...open, heading: "Payment Successful" })).toBe(open);
    expect(shouldPromptOnHistoryOpen()).toBe(false);
  });

  it("ignores a second Yes while the first print is still claimed", () => {
    const first = startPrint({ printing: false, attempts: 0, payments: 1 });
    const second = startPrint(first.gate);
    expect(first.started).toBe(true);
    expect(second.started).toBe(false);
    expect(second.gate.attempts).toBe(1);
    expect(second.gate.payments).toBe(1);
  });

  it("reports an unavailable printer without calling the print a success", async () => {
    const result = await printConfirmationSlips([bill], async () => ({ printed: false, message: "The printer is offline." }));
    expect(result.printed).toBe(0);
    expect(result.error).toBe(PRINTER_UNAVAILABLE_MESSAGE);
  });

  it("offers a PDF only for a recorded desktop sale", () => {
    expect(canDownloadReceiptPdf(true, "sale-1", "recorded")).toBe(true);
    expect(canDownloadReceiptPdf(false, "sale-1", "recorded")).toBe(false);
    expect(canDownloadReceiptPdf(true, "", "recorded")).toBe(false);
    expect(canDownloadReceiptPdf(true, "sale-1", "queued")).toBe(false);
  });

  it("retries printing without recording another payment", async () => {
    const payments = 1;
    let calls = 0;
    const failed = await printConfirmationSlips([bill, bill], async () => {
      expect(payments).toBe(1);
      calls += 1;
      if (calls === 1) return { printed: true, message: null };
      return { printed: false, message: "offline" };
    });
    expect(failed.printed).toBe(1);
    expect(failed.error).toBe(PRINTER_UNAVAILABLE_MESSAGE);
    const released = finishPrint({ printing: true, attempts: 1, payments });
    const retry = applyReceiptChoice("retry", released);
    expect(retry.print).toBe(true);
    expect(retry.gate.payments).toBe(1);
    expect(retry.gate.attempts).toBe(2);
    let retried = 0;
    const printed = await printConfirmationSlips(
      [bill, bill],
      async () => {
        retried += 1;
        return { printed: true, message: null };
      },
      failed.printed,
    );
    expect(printed.error).toBeNull();
    expect(retried).toBe(1);
    expect(payments).toBe(1);
  });

  it("does not kick the drawer for Print, Skip, or Retry", async () => {
    expect(drawerKickOnChoice("print")).toBe(false);
    expect(drawerKickOnChoice("skip")).toBe(false);
    expect(drawerKickOnChoice("retry")).toBe(false);
    expect(printOptionsForConfirmation().kickDrawer).toBe(false);
    let kicks = 0;
    const kick = async () => {
      kicks += 1;
    };
    const deps = { load: async () => ({ drawer_kick: true, transport: "windows" as const }), kick };
    const kicked = await kickDrawerForCashSale(true, false, deps);
    expect(kicked).toBe(true);
    expect(kicks).toBe(1);
    await kickDrawerForCashSale(true, kicked, deps);
    expect(kicks).toBe(1);
    await printConfirmationSlips([bill], async (_slip, options) => {
      expect(options.kickDrawer).toBe(false);
      return { printed: true, message: null };
    });
    expect(kicks).toBe(1);
    expect(await kickDrawerForCashSale(false, false, deps)).toBe(false);
    expect(kicks).toBe(1);
  });

  it("uses the selected split receipt output", () => {
    expect(prompt({ guestCount: 3, receiptOutput: "combined" }).slips).toEqual([bill]);
    const separate = prompt({ guestCount: 3, receiptOutput: "separate" });
    expect(separate.slips).toHaveLength(3);
    expect(separate.slips.map((slip) => slip.totalCents)).toEqual([6930, 6930, 6930]);
    expect(separate.slips[0]?.title).toBe("Split 1 of 3");
  });

  it("shows the remaining balance on a partial payment", () => {
    const partial = prompt({ paidCents: 10000, remainingCents: 10790, methodLabel: "Cash" });
    expect(partial.heading).toBe("Payment Successful");
    expect(partial.receivedText).toBe(formatMoney(10000, "AED"));
    expect(partial.remainingLabel).toBe("Remaining balance");
    expect(partial.remainingText).toBe(formatMoney(10790, "AED"));
    expect(partial.paidReceipt).toBe(false);
  });

  it("does not present an unpaid credit invoice as a paid receipt", () => {
    const credit = prompt({ paidCents: 0, remainingCents: 20790, methodLabel: "On account" });
    expect(credit.heading).toBe("Invoice recorded");
    expect(credit.receivedLabel).toBeNull();
    expect(credit.receivedText).toBeNull();
    expect(credit.remainingLabel).toBe("Amount on account");
    expect(credit.question).toBe("Would you like to print the invoice?");
    expect(credit.paidReceipt).toBe(false);
    expect(credit.documentKind).toBe("invoice");

    const cod = prompt({ paidCents: 0, remainingCents: 0, cod: true, methodLabel: "Cash on delivery" });
    expect(cod.heading).toBe("Cash on delivery recorded");
    expect(cod.receivedLabel).toBeNull();
    expect(cod.paidReceipt).toBe(false);
    expect(cod.remainingLabel).toBe("Payment not yet received");
  });
});

describe("receipt confirmation dialog", () => {
  const idle = {
    onDismiss: () => undefined,
    onPrinted: () => undefined,
    onPrint: async () => ({ printed: true, message: null }),
    onDownloadPdf: async () => undefined,
  };

  it("shows the payment and the Yes and No actions", () => {
    const html = renderToStaticMarkup(<ReceiptConfirmationModal prompt={prompt()} {...idle} />);
    expect(html).toContain("Payment Successful");
    expect(html).toContain("INV-9");
    expect(html).toContain("Layla");
    expect(html).toContain("Cash");
    expect(html).toContain("Payment received");
    expect(html).toContain(formatMoney(20790, "AED"));
    expect(html).toContain("Would you like to print the receipt?");
    expect(html).toContain("No, Skip");
    expect(html).toContain("Yes, Print Receipt");
    expect(html).not.toContain(PRINTER_UNAVAILABLE_MESSAGE);
  });

  it("shows the printer failure, retry, and PDF actions without a paid-receipt claim for credit", () => {
    const failed = renderToStaticMarkup(
      <ReceiptConfirmationModal
        prompt={prompt()}
        {...idle}
        initialPhase="failed"
        initialError={PRINTER_UNAVAILABLE_MESSAGE}
      />,
    );
    expect(failed).toContain(PRINTER_UNAVAILABLE_MESSAGE);
    expect(failed).toContain("Retry Print");
    expect(failed).toContain("Download PDF");
    expect(failed).toContain("Close");
    expect(failed).toContain("Payment Successful");

    const credit = renderToStaticMarkup(
      <ReceiptConfirmationModal prompt={prompt({ paidCents: 0, remainingCents: 20790, methodLabel: "On account", pdfAvailable: false })} {...idle} />,
    );
    expect(credit).toContain("Invoice recorded");
    expect(credit).toContain("Amount on account");
    expect(credit).not.toContain("Payment received");
    expect(credit).not.toContain("Download PDF");
  });
});
