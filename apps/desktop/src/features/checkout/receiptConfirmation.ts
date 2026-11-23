import type { ReceiptDoc } from "@ai-pos/receipt";
import { formatMoney } from "@ai-pos/shared-types";
import { shouldKickDrawer } from "../printing/print";
import { presentEqualSplit, type ReceiptOutput } from "../restaurant/splitReceipts";

export const PRINTER_UNAVAILABLE_MESSAGE =
  "Receipt printer is unavailable. Your payment was successful, but the receipt could not be printed.";

/** A sale is settled only after the register accepts it. Submitting the request is not success. */
export function isSettledPayment(outcome: string): boolean {
  return outcome === "recorded" || outcome === "queued";
}

/** Bill History reprint is an explicit later action. It does not ask again. */
export function shouldPromptOnHistoryOpen(): false {
  return false;
}

/** Yes and No apply to this payment only. */
export function choiceIsRemembered(): false {
  return false;
}

/** Confirmation prints the saved slip and never kicks the drawer. The kick already happened for cash. */
export function printOptionsForConfirmation(): { kickDrawer: false; manual: true } {
  return { kickDrawer: false, manual: true };
}

export function drawerKickOnChoice(_choice: "print" | "skip" | "retry"): false {
  return false;
}

export function initialDrawerKick(takesCash: boolean, policyAllows: boolean, alreadyKicked: boolean): boolean {
  return takesCash && policyAllows && !alreadyKicked;
}

export interface PrintGate {
  printing: boolean;
  attempts: number;
  payments: number;
}

/** The first Yes or Retry claims the print. A second call while that print is running does nothing. */
export function startPrint(gate: PrintGate): { gate: PrintGate; started: boolean } {
  if (gate.printing) return { gate, started: false };
  return { gate: { printing: true, attempts: gate.attempts + 1, payments: gate.payments }, started: true };
}

export function finishPrint(gate: PrintGate): PrintGate {
  return { ...gate, printing: false };
}

export function applyReceiptChoice(
  choice: "yes" | "no" | "retry",
  gate: PrintGate,
): { print: boolean; gate: PrintGate } {
  if (choice === "no") return { print: false, gate };
  const started = startPrint(gate);
  return { print: started.started, gate: started.gate };
}

export function printFailureMessage(outcome: { printed: boolean }): string | null {
  return outcome.printed ? null : PRINTER_UNAVAILABLE_MESSAGE;
}

/** PDF export needs a sale the API has accepted. A queued offline sale is not offered. */
export function canDownloadReceiptPdf(desktop: boolean, saleId: string, outcome: string): boolean {
  return desktop && saleId !== "" && outcome === "recorded";
}

export function shouldAskForReceipt(input: {
  outcome: string;
  blocker: string | null;
  providerStatus: string | null;
}): boolean {
  if (!isSettledPayment(input.outcome)) return false;
  if (input.blocker) return false;
  if (input.providerStatus !== null && input.providerStatus !== "PAID") return false;
  return true;
}

export function slipsForConfirmation(doc: ReceiptDoc, guestCount: number, output: ReceiptOutput): ReceiptDoc[] {
  if (guestCount < 2) return [doc];
  return presentEqualSplit(doc, guestCount, output);
}

/** One open prompt per payment. A rerender of the same payment does not open another. */
export function openReceiptPrompt<T extends { id: string }>(current: T | null, next: T | null): T | null {
  if (next === null) return current;
  if (current && current.id === next.id) return current;
  return next;
}

export interface ReceiptPromptCopy {
  heading: string;
  receivedLabel: string | null;
  receivedText: string | null;
  remainingLabel: string | null;
  remainingText: string | null;
  changeText: string | null;
  question: string;
  paidReceipt: boolean;
  documentKind: "receipt" | "invoice";
}

export function describeReceiptPrompt(input: {
  paidCents: number;
  remainingCents: number;
  changeCents: number | null;
  totalCents: number;
  currency: string;
  cod: boolean;
}): ReceiptPromptCopy {
  const money = (cents: number) => formatMoney(cents, input.currency);
  const changeText = input.changeCents !== null && input.changeCents > 0 ? money(input.changeCents) : null;
  if (input.cod && input.paidCents <= 0) {
    return {
      heading: "Cash on delivery recorded",
      receivedLabel: null,
      receivedText: null,
      remainingLabel: "Payment not yet received",
      remainingText: money(input.totalCents),
      changeText,
      question: "Would you like to print the invoice?",
      paidReceipt: false,
      documentKind: "invoice",
    };
  }
  if (input.paidCents <= 0 && input.remainingCents > 0) {
    return {
      heading: "Invoice recorded",
      receivedLabel: null,
      receivedText: null,
      remainingLabel: "Amount on account",
      remainingText: money(input.remainingCents),
      changeText,
      question: "Would you like to print the invoice?",
      paidReceipt: false,
      documentKind: "invoice",
    };
  }
  return {
    heading: "Payment Successful",
    receivedLabel: "Payment received",
    receivedText: money(input.paidCents),
    remainingLabel: input.remainingCents > 0 ? "Remaining balance" : null,
    remainingText: input.remainingCents > 0 ? money(input.remainingCents) : null,
    changeText,
    question: "Would you like to print the receipt?",
    paidReceipt: input.remainingCents <= 0,
    documentKind: "receipt",
  };
}

export interface ReceiptPrompt extends ReceiptPromptCopy {
  id: string;
  invoiceNumber: string;
  customerName: string | null;
  methodLabel: string;
  slips: ReceiptDoc[];
  pdfAvailable: boolean;
  saleId: string;
}

export function buildReceiptPrompt(
  input: {
    id: string;
    outcome: string;
    blocker: string | null;
    providerStatus: string | null;
    paidCents: number;
    remainingCents: number;
    changeCents: number | null;
    totalCents: number;
    currency: string;
    cod: boolean;
    invoiceNumber: string;
    customerName: string | null;
    methodLabel: string;
    saleId: string;
    guestCount: number;
    receiptOutput: ReceiptOutput;
    pdfAvailable: boolean;
  },
  receipt: ReceiptDoc,
): ReceiptPrompt | null {
  if (!shouldAskForReceipt(input)) return null;
  return {
    id: input.id,
    invoiceNumber: input.invoiceNumber,
    customerName: input.customerName,
    methodLabel: input.methodLabel,
    slips: slipsForConfirmation(receipt, input.guestCount, input.receiptOutput),
    pdfAvailable: input.pdfAvailable,
    saleId: input.saleId,
    ...describeReceiptPrompt(input),
  };
}

/** Prints the saved slips from the first one not yet printed. A failed slip stops the job. */
export async function printConfirmationSlips(
  slips: ReceiptDoc[],
  printOne: (
    slip: ReceiptDoc,
    options: { kickDrawer: false; manual: true },
  ) => Promise<{ printed: boolean; message: string | null }>,
  alreadyPrinted = 0,
): Promise<{ printed: number; error: string | null }> {
  const options = printOptionsForConfirmation();
  let printed = alreadyPrinted;
  for (let index = alreadyPrinted; index < slips.length; index += 1) {
    const slip = slips[index];
    if (!slip) continue;
    const outcome = await printOne(slip, options);
    if (!outcome.printed) return { printed, error: printFailureMessage(outcome) ?? PRINTER_UNAVAILABLE_MESSAGE };
    printed += 1;
  }
  return { printed, error: null };
}

/** One kick for an accepted cash tender, using the register drawer policy. Later calls do not kick again. */
export async function kickDrawerForCashSale(
  takesCash: boolean,
  alreadyKicked: boolean,
  deps: {
    load: () => Promise<{ drawer_kick: boolean; transport: "none" | "tcp" | "windows" }>;
    kick: () => Promise<void>;
  },
): Promise<boolean> {
  if (alreadyKicked || !takesCash) return alreadyKicked;
  const settings = await deps.load();
  if (!shouldKickDrawer({ kickDrawer: true }, settings)) return false;
  await deps.kick().catch(() => undefined);
  return true;
}
