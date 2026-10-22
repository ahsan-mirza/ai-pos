import { describe, expect, it } from "vitest";
import { foreignNeeded, foreignValue } from "./fx";
import { emptyPayment, planTenders } from "./tenders";

describe("foreign cash", () => {
  it("rounds what the customer must hand over up, and its value half up", () => {
    expect(foreignNeeded(3000, 1_100_000)).toBe(2728);
    expect(foreignValue(2728, 1_100_000)).toBe(3001);
    expect(foreignValue(3000, 1_100_000)).toBe(3300);
  });

  it("plans a foreign tender with business-currency change", () => {
    const plan = planTenders(
      { ...emptyPayment, cashReceived: "30.00", cashCurrency: { code: "EUR", rateMicros: 1_100_000 } },
      3000,
      null,
    );
    expect(plan.blocker).toBeNull();
    expect(plan.changeCents).toBe(300);
    expect(plan.tenders).toEqual([
      {
        method: "cash",
        amount_cents: 3000,
        reference: "",
        currency: "EUR",
        foreign_amount_cents: 3000,
        rate_micros: 1_100_000,
        change_cents: 300,
      },
    ]);
  });

  it("splits a loyalty redemption from the tender that pays the rest", () => {
    const customer = { id: "c1", customer_type: "RETAIL", loyalty_points: 500 } as never;
    const plan = planTenders(
      { ...emptyPayment, choice: "card", loyalty: { points: 300, valueCents: 300 } },
      1500,
      customer,
    );
    expect(plan.loyaltyPoints).toBe(300);
    expect(plan.tenders).toEqual([
      { method: "loyalty", amount_cents: 300, reference: "300 pts" },
      { method: "card", amount_cents: 1200, reference: "" },
    ]);
  });

  it("blocks when the foreign cash falls short", () => {
    const plan = planTenders(
      { ...emptyPayment, cashReceived: "20.00", cashCurrency: { code: "EUR", rateMicros: 1_100_000 } },
      3000,
      null,
    );
    expect(plan.blocker).toBe("Enter the EUR received.");
    expect(plan.tenders).toEqual([]);
  });
});
