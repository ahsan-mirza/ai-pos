import { describe, expect, it } from "vitest";
import { decideLocalExpense, localExpenseLabel } from "./localExpense";

describe("offline expenses", () => {
  it("keeps petty cash unposted until a downloaded balance covers it", () => {
    expect(decideLocalExpense({ paidFrom: "BANK", totalCents: 2500, cachedPettyCents: null }).status).toBe("pending_sync");
    expect(decideLocalExpense({ paidFrom: "PETTY_CASH", totalCents: 2500, cachedPettyCents: null }).status).toBe("pending_review");
    expect(decideLocalExpense({ paidFrom: "PETTY_CASH", totalCents: 2500, cachedPettyCents: 1000 }).reservesPetty).toBe(false);
    const covered = decideLocalExpense({ paidFrom: "PETTY_CASH", totalCents: 2500, cachedPettyCents: 2500 });
    expect(covered.status).toBe("pending_sync");
    expect(covered.reservesPetty).toBe(true);
    expect(covered.detail).toContain("server accepts");
    expect(localExpenseLabel("pending_review")).toBe("Pending Review");
    expect(localExpenseLabel("synced")).toBe("Synced");
  });
});
