import { describe, expect, it } from "vitest";
import { centsFromMoney, expenseFieldErrors, firstExpenseField, includedVatCents } from "./expenseForm";

const draft = {
  category: "UTILITIES",
  spentOn: "2026-11-25",
  description: "DEWA bill",
  total: "105.00",
  taxCategory: "STANDARD" as const,
  invoice: false,
  trn: "",
  paidFrom: "BANK" as const,
  standardRateBps: 500,
};

describe("expense form", () => {
  it("splits included VAT with the same half-up rule as the API", () => {
    expect(includedVatCents(10500, 500)).toBe(500);
    expect(includedVatCents(10000, 0)).toBe(0);
    expect(centsFromMoney("10.5")).toBe(1050);
    expect(centsFromMoney("0")).toBe(0);
    expect(centsFromMoney("")).toBeNull();
  });

  it("names the first missing field and leaves a complete draft clear", () => {
    expect(expenseFieldErrors(draft)).toEqual({});
    const missing = expenseFieldErrors({ ...draft, category: "", description: " ", total: "0", paidFrom: "" });
    expect(missing.category).toBe("Select an expense category.");
    expect(missing.description).toBe("Say what this expense was for.");
    expect(missing.total).toBe("Enter an expense amount greater than zero.");
    expect(missing.paid_from).toBe("Select how this expense was paid.");
    expect(firstExpenseField(missing)).toBe("category");
    expect(expenseFieldErrors({ ...draft, invoice: true, trn: "123" }).trn).toMatch(/15-digit TRN/);
  });
});
