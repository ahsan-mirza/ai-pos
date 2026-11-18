import { describe, expect, it } from "vitest";
import { aedFromFils, componentValueFils, filsFromAed, productFieldErrors, savingsFils } from "./pricing";

describe("hardware catalogue pricing", () => {
  it("keeps fils as integers and shows savings only when the components cost more", () => {
    expect(filsFromAed("1899.00")).toBe(189900);
    expect(filsFromAed("")).toBeNull();
    expect(filsFromAed("12.345")).toBeNull();
    expect(aedFromFils(9900)).toBe("99.00");
    const parts = [
      { quantity: 1, displayPriceFils: 100000, optional: false },
      { quantity: 2, displayPriceFils: 5000, optional: false },
      { quantity: 1, displayPriceFils: 9000, optional: true },
    ];
    expect(componentValueFils(parts)).toBe(110000);
    expect(savingsFils(parts, 100000)).toBe(10000);
    expect(savingsFils(parts, 110000)).toBeNull();
    expect(componentValueFils([{ quantity: 1, displayPriceFils: null, optional: false }])).toBeNull();
  });

  it("rejects an incomplete product before it is sent", () => {
    expect(productFieldErrors({ name: "", sku: "ok", displayPrice: "", reason: "Add a terminal" }).name).toBeTruthy();
    expect(productFieldErrors({ name: "Terminal", sku: "bad sku", displayPrice: "10", reason: "Add a terminal" }).sku).toBeTruthy();
    expect(productFieldErrors({ name: "Terminal", sku: "POS-1", displayPrice: "10.5", reason: "Add a terminal" })).toEqual({});
  });
});
