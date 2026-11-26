import { describe, expect, it } from "vitest";

import { presentOrderLines, sentIncrease, type QuantityLine } from "./tableQuantity";

function row(patch: Partial<QuantityLine> & Pick<QuantityLine, "id" | "quantity">): QuantityLine {
  return {
    sentAt: null,
    voidedAt: null,
    paid: false,
    kitchen: null,
    sourceId: null,
    ...patch,
  };
}

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

describe("table line quantity controls", () => {
  it("lets an unsent line move by one and stops at one", () => {
    const one = presentOrderLines([row({ id: "a", quantity: 1 })])[0];
    expect(one?.minus).toBe("minimum");
    expect(one?.net).toBe(1);
    const two = presentOrderLines([row({ id: "a", quantity: 2 })])[0];
    expect(two?.minus).toBe("enabled");
    expect(two?.originalSent).toBeNull();
  });

  it("disables minus on a sent line until an extra exists", () => {
    const [line] = presentOrderLines([row({ id: "a", quantity: 1, sentAt: "t", kitchen: "new" })]);
    expect(line?.minus).toBe("original");
    expect(line?.originalSent).toBe(1);
    expect(line?.additional).toBe(0);
  });

  it("enables minus only for the extra quantity", () => {
    const [line] = presentOrderLines([
      row({ id: "a", quantity: 1, sentAt: "t", kitchen: "new" }),
      row({ id: "b", quantity: 1, sentAt: "t2", kitchen: "new", sourceId: "a" }),
    ]);
    expect(line?.net).toBe(2);
    expect(line?.originalSent).toBe(1);
    expect(line?.additional).toBe(1);
    expect(line?.minus).toBe("enabled");
  });

  it("returns an original quantity of 3 to the sent floor after two extras", () => {
    const withExtras = presentOrderLines([
      row({ id: "a", quantity: 3, sentAt: "t", kitchen: "new" }),
      row({ id: "b", quantity: 1, sentAt: "t2", kitchen: "new", sourceId: "a" }),
      row({ id: "c", quantity: 1, sentAt: "t3", kitchen: "new", sourceId: "a" }),
    ])[0];
    expect(withExtras?.net).toBe(5);
    expect(withExtras?.minus).toBe("enabled");
    const back = presentOrderLines([row({ id: "a", quantity: 3, sentAt: "t", kitchen: "new" })])[0];
    expect(back?.net).toBe(3);
    expect(back?.minus).toBe("original");
  });

  it("does not offer minus for an extra the kitchen has already served", () => {
    const [line] = presentOrderLines([
      row({ id: "a", quantity: 1, sentAt: "t", kitchen: "new" }),
      row({ id: "b", quantity: 1, sentAt: "t2", kitchen: "bumped", sourceId: "a" }),
    ]);
    expect(line?.minus).toBe("served");
  });
});
