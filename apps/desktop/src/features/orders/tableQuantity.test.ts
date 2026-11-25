import { describe, expect, it } from "vitest";

import { sentIncrease } from "./tableQuantity";

describe("sent kitchen quantity", () => {
  it("sends only the extra plates", () => {
    expect(sentIncrease(1, 3)).toEqual({ ok: true, extra: 2 });
  });

  it("refuses to shrink a sent line", () => {
    expect(sentIncrease(3, 2)).toEqual({ ok: false, reason: "reduce" });
  });

  it("leaves the ticket alone when the quantity does not change", () => {
    expect(sentIncrease(2, 2)).toEqual({ ok: false, reason: "same" });
  });

  it("refuses a quantity outside 1 to 1000", () => {
    expect(sentIncrease(1, 0).ok).toBe(false);
    expect(sentIncrease(1, 1001).ok).toBe(false);
  });
});
