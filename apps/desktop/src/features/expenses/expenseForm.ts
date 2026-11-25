import { divHalfUp, type ExpensePaidFrom, type TaxCategory } from "@ai-pos/shared-types";

export type ExpenseField = "category" | "spent_on" | "description" | "supplier" | "total" | "paid_from" | "trn" | "bill" | "note";

export const EXPENSE_FIELD_ORDER: readonly ExpenseField[] = ["category", "spent_on", "description", "supplier", "total", "paid_from", "trn", "bill", "note"];

/** VAT inside a paid total, using the same half-up split as the expense API. A zero rate yields no VAT. */
export function includedVatCents(totalCents: number, rateBps: number): number {
  if (totalCents < 1 || rateBps <= 0) return 0;
  return divHalfUp(totalCents * rateBps, 10_000 + rateBps);
}

export function rateBpsFor(category: TaxCategory, standardRateBps: number): number {
  return category === "STANDARD" ? standardRateBps : 0;
}

/** Whole cents from a money field. Empty and non-numeric values are null. Zero is 0. */
export function centsFromMoney(raw: string): number | null {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

export interface ExpenseDraft {
  category: string;
  spentOn: string;
  description: string;
  total: string;
  taxCategory: TaxCategory;
  invoice: boolean;
  trn: string;
  paidFrom: ExpensePaidFrom | "";
  standardRateBps: number;
}

export function expenseFieldErrors(draft: ExpenseDraft): Partial<Record<ExpenseField, string>> {
  const errors: Partial<Record<ExpenseField, string>> = {};
  if (draft.category === "") errors.category = "Select an expense category.";
  if (draft.spentOn.trim() === "" || Number.isNaN(Date.parse(draft.spentOn))) errors.spent_on = "Select a valid expense date.";
  if (draft.description.trim().length < 2) errors.description = "Say what this expense was for.";
  const cents = centsFromMoney(draft.total);
  if (cents === null || cents < 1) errors.total = "Enter an expense amount greater than zero.";
  if (draft.paidFrom === "") errors.paid_from = "Select how this expense was paid.";
  const vat = cents !== null && cents > 0 ? includedVatCents(cents, rateBpsFor(draft.taxCategory, draft.standardRateBps)) : 0;
  if (draft.invoice && vat > 0 && !/^\d{15}$/.test(draft.trn)) errors.trn = "Enter the 15-digit TRN printed on the tax invoice.";
  return errors;
}

export function firstExpenseField(errors: Partial<Record<ExpenseField, string>>): ExpenseField | null {
  return EXPENSE_FIELD_ORDER.find((field) => errors[field]) ?? null;
}
