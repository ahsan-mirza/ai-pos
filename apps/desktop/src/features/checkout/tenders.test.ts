import { describe, expect, it } from "vitest";
import { emptyPayment, equalShares, planTenders, quickCashAmounts, splitEqually } from "./tenders";
import { normalizeVoucher } from "./storeCredit";

describe("delivery-app orders", () => {
  it("are paid in full by the channel tender", () => {
    const plan = planTenders({ ...emptyPayment, choice: "channel", reference: "Talabat" }, 4_200, null);
    expect(plan.blocker).toBeNull();
    expect(plan.paymentMethod).toBe("channel");
    expect(plan.tenders).toEqual([{ method: "channel", amount_cents: 4_200, reference: "Talabat" }]);
  });
});

describe("integrated card terminal", () => {
  const paid = { id: "intent-1", amountCents: 5_000, status: "PAID" as const, provider: "ngenius", simulated: false, cardLabel: "VISA •••• 4242" };

  it("is a plain card tender while the store has no terminal", () => {
    const plan = planTenders({ ...emptyPayment, choice: "card" }, 5_000, null);
    expect(plan.blocker).toBeNull();
    expect(plan.tenders).toEqual([{ method: "card", amount_cents: 5_000, reference: "" }]);
  });

  it("waits for the terminal's approval and references it", () => {
    const waiting = planTenders({ ...emptyPayment, choice: "card", cardTerminal: true }, 5_000, null);
    expect(waiting.blocker).toBe("Send the amount to the card terminal.");
    const plan = planTenders({ ...emptyPayment, choice: "card", cardTerminal: true, cardIntent: paid }, 5_000, null);
    expect(plan.blocker).toBeNull();
    expect(plan.tenders[0]).toMatchObject({ method: "card", payment_intent_id: "intent-1", reference: "VISA •••• 4242" });
    const changed = planTenders({ ...emptyPayment, choice: "card", cardTerminal: true, cardIntent: paid }, 6_000, null);
    expect(changed.blocker).toBe("The total changed after the card was approved.");
  });

  it("carries the manager's approval on a manual entry", () => {
    const manual = { approvedById: "manager-1", approverName: "Mona", note: "Terminal offline" };
    const plan = planTenders({ ...emptyPayment, choice: "card", cardTerminal: true, cardManual: manual }, 5_000, null);
    expect(plan.tenders[0]).toMatchObject({ manual_override: { approved_by_id: "manager-1", note: "Terminal offline" } });
  });

  it("pay later needs the captured provider payment", () => {
    expect(planTenders({ ...emptyPayment, choice: "bnpl" }, 5_000, null).blocker).toMatch(/pay-later checkout/);
    const plan = planTenders({ ...emptyPayment, choice: "bnpl", bnplIntent: { ...paid, provider: "tabby" } }, 5_000, null);
    expect(plan.paymentMethod).toBe("bnpl");
    expect(plan.tenders).toEqual([{ method: "bnpl", amount_cents: 5_000, reference: "tabby", payment_intent_id: "intent-1" }]);
  });
});

describe("split between guests", () => {
  it("shares the bill equally to the cent", () => {
    expect(equalShares(10_000, 3)).toEqual([3334, 3333, 3333]);
    expect(equalShares(500, 20)).toHaveLength(12);
  });

  it("collects one tender per guest once every share is paid", () => {
    const guests = splitEqually(10_000, 3);
    const waiting = planTenders({ ...emptyPayment, choice: "split", guests }, 10_000, null);
    expect(waiting.blocker).toBe("Collect guest 1's share.");
    const paid = guests.map((guest, index) => ({ ...guest, paid: true, method: index === 0 ? ("cash" as const) : guest.method }));
    const plan = planTenders({ ...emptyPayment, choice: "split", guests: paid }, 10_000, null);
    expect(plan.blocker).toBeNull();
    expect(plan.paymentMethod).toBe("cash");
    expect(plan.tenders.map((tender) => [tender.method, tender.amount_cents, tender.reference])).toEqual([
      ["cash", 3334, "Guest 1"],
      ["card", 3333, "Guest 2"],
      ["card", 3333, "Guest 3"],
    ]);
  });

  it("refuses shares that do not add up", () => {
    const guests = [
      { method: "card" as const, amount: "40.00", paid: true },
      { method: "card" as const, amount: "50.00", paid: true },
    ];
    expect(planTenders({ ...emptyPayment, choice: "split", guests }, 10_000, null).blocker).toBe(
      "The guests' shares must add up to the amount due.",
    );
  });
});

describe("quickCashAmounts", () => {
  it("rounds the total up to common banknotes", () => {
    expect(quickCashAmounts(4725)).toEqual([5000, 10000]);
    expect(quickCashAmounts(1234)).toEqual([1500, 2000, 5000]);
  });

  it("skips amounts equal to the total and empty carts", () => {
    expect(quickCashAmounts(10000)).toEqual([]);
    expect(quickCashAmounts(0)).toEqual([]);
  });
});

describe("trade-in credit", () => {
  const tradeIn = { id: "trade-1", number: "DT-01-TRD-000001", amountCents: 30_000 };

  it("comes off the sale first and the chosen tender collects the rest", () => {
    const plan = planTenders({ ...emptyPayment, choice: "card", tradeIn }, 45_000, null);
    expect(plan.blocker).toBeNull();
    expect(plan.tenders).toEqual([
      { method: "trade_in", amount_cents: 30_000, reference: tradeIn.number, trade_in_id: tradeIn.id },
      { method: "card", amount_cents: 15_000, reference: "" },
    ]);
  });

  it("blocks a trade-in worth more than the sale", () => {
    const plan = planTenders({ ...emptyPayment, choice: "cash", tradeIn }, 20_000, null);
    expect(plan.blocker).toMatch(/worth more than the sale/);
  });
});

describe("store credit", () => {
  const voucher = { code: "SC-AB12-CD34-EF56", balanceCents: 3000 };

  it("pays up to the voucher balance and leaves the rest to the chosen tender", () => {
    const plan = planTenders({ ...emptyPayment, choice: "card", storeCredit: voucher }, 5000, null);
    expect(plan.blocker).toBeNull();
    expect(plan.paymentMethod).toBe("card");
    expect(plan.tenders).toEqual([
      { method: "store_credit", amount_cents: 3000, reference: voucher.code, store_credit_code: voucher.code },
      { method: "card", amount_cents: 2000, reference: "" },
    ]);
  });

  it("covers the whole sale when the balance is enough", () => {
    const plan = planTenders({ ...emptyPayment, choice: "cash", storeCredit: voucher }, 1200, null);
    expect(plan.blocker).toBeNull();
    expect(plan.paymentMethod).toBe("store_credit");
    expect(plan.tenders).toEqual([
      { method: "store_credit", amount_cents: 1200, reference: voucher.code, store_credit_code: voucher.code },
    ]);
  });

  it("reads typed or scanned codes", () => {
    expect(normalizeVoucher(" sc ab12 cd34 ef56 ")).toBe("SC-AB12-CD34-EF56");
    expect(normalizeVoucher("SCAB12CD34EF56")).toBe("SC-AB12-CD34-EF56");
  });
});
