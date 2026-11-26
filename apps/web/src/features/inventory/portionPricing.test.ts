import { portionCents, portionIssues, priceOptionsPayload, type PriceDraft } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { catalogPriceLabel, isMultiplePortionProduct, movePortion, portionsFromOptions, portionsSeededFromPrice } from "./portionPricing";

const daal: PriceDraft[] = [
  { id: "small", name: "Small Plate", price: "3.00", active: true },
  { id: "medium", name: "Medium Plate", price: "5.00", active: true },
  { id: "full", name: "Full Plate", price: "9.00", active: true },
];

describe("menu item portion pricing", () => {
  it("keeps a single price when the portion rows are blank", () => {
    expect(priceOptionsPayload([{ name: "", price: "" }, { name: "", price: "" }], portionCents)).toBeNull();
    expect(portionIssues([{ name: "", price: "" }, { name: "", price: "" }])).toEqual([]);
  });

  it("saves several portions of one item and keeps their ids", () => {
    expect(priceOptionsPayload(daal, portionCents)).toEqual({
      options: [
        { id: "small", name: "Small Plate", price_cents: 300, is_active: true, position: 0 },
        { id: "medium", name: "Medium Plate", price_cents: 500, is_active: true, position: 1 },
        { id: "full", name: "Full Plate", price_cents: 900, is_active: true, position: 2 },
      ],
    });
  });

  it("adds a portion without a sku of its own", () => {
    const withExtra = [...daal, { name: "Family", price: "14", active: true }];
    const body = priceOptionsPayload(withExtra, portionCents);
    expect(body?.options).toHaveLength(4);
    expect(body?.options[3]).toEqual({ name: "Family", price_cents: 1400, is_active: true, position: 3 });
    expect(body?.options.every((option) => !("sku" in option))).toBe(true);
  });

  it("edits a name and a price without replacing the option id", () => {
    const edited = daal.map((row) => (row.id === "medium" ? { ...row, name: "Medium Plate", price: "5.50" } : row));
    const body = priceOptionsPayload(edited, portionCents);
    expect(body?.options[1]).toEqual({ id: "medium", name: "Medium Plate", price_cents: 550, is_active: true, position: 1 });
  });

  it("deactivates a portion and still requires one active price", () => {
    const paused = daal.map((row) => (row.id === "full" ? { ...row, active: false } : row));
    expect(priceOptionsPayload(paused, portionCents)?.options.map((option) => option.is_active)).toEqual([true, true, false]);
    const none = daal.map((row) => ({ ...row, active: false }));
    expect(portionIssues(none).some((issue) => issue.message.includes("stay active"))).toBe(true);
    expect(() => priceOptionsPayload(none, portionCents)).toThrow(/stay active/);
  });

  it("rejects a duplicate option name", () => {
    const issues = portionIssues([
      { name: "Small Plate", price: "3" },
      { name: "small plate", price: "4" },
    ]);
    expect(issues.some((issue) => issue.key === "1.name" && issue.message.includes("share a name"))).toBe(true);
  });

  it("rejects an empty option name", () => {
    const issues = portionIssues([
      { name: "Small Plate", price: "3" },
      { name: "   ", price: "4" },
    ]);
    expect(issues.some((issue) => issue.message === "Option name is required.")).toBe(true);
  });

  it("rejects an invalid price and a negative price", () => {
    const invalid = portionIssues([
      { name: "Small Plate", price: "3" },
      { name: "Full Plate", price: "9.999" },
    ]);
    expect(invalid.some((issue) => issue.key === "1.price" && issue.message.includes("two decimal places"))).toBe(true);
    const negative = portionIssues([
      { name: "Small Plate", price: "3" },
      { name: "Full Plate", price: "-1" },
    ]);
    expect(negative.some((issue) => issue.message === "Price cannot be negative.")).toBe(true);
    expect(portionCents("-1")).toBeNull();
  });

  it("allows a zero portion price because stored prices are zero or more", () => {
    const issues = portionIssues([
      { name: "Small Plate", price: "0" },
      { name: "Full Plate", price: "9.00" },
    ]);
    expect(issues.filter((issue) => issue.key.endsWith(".price"))).toEqual([]);
    expect(priceOptionsPayload([{ name: "Small Plate", price: "0.00" }, { name: "Full Plate", price: "9" }], portionCents)?.options[0]?.price_cents).toBe(0);
  });

  it("refuses a multiple-price item with only one named price", () => {
    expect(portionIssues([{ name: "Lunch", price: "12" }, { name: "", price: "" }]).some((issue) => issue.key === "list")).toBe(true);
    expect(() => priceOptionsPayload([{ name: "Lunch", price: "12" }, { name: "", price: "" }], portionCents)).toThrow(/two named prices/);
  });

  it("keeps the current price when switching a single-price item to portions", () => {
    expect(portionsSeededFromPrice([{ name: "", price: "" }, { name: "", price: "" }], "6.00")).toEqual([
      { name: "", price: "6.00", active: true },
      { name: "", price: "", active: true },
    ]);
  });

  it("reorders portions and drops one before save without minting new ids", () => {
    const moved = movePortion(daal, 2, -1);
    expect(moved.map((row) => row.id)).toEqual(["small", "full", "medium"]);
    const removed = moved.filter((row) => row.id !== "full");
    expect(priceOptionsPayload(removed, portionCents)?.options.map((option) => option.id)).toEqual(["small", "medium"]);
  });

  it("labels a single price and a from price without a second product", () => {
    expect(catalogPriceLabel({ price_cents: 200, currency: "AED" })).toBe(catalogPriceLabel({ price_cents: 200, currency: "AED", price_options: [] }));
    const multiple = {
      price_cents: 600,
      currency: "AED",
      price_options: portionsFromOptions([
        { id: "small", product_id: "daal", name: "Small Plate", price_cents: 300, is_active: true, position: 0 },
        { id: "full", product_id: "daal", name: "Full Plate", price_cents: 900, is_active: true, position: 1 },
      ]).map((row, position) => ({
        id: row.id ?? "",
        product_id: "daal",
        name: row.name,
        price_cents: portionCents(row.price) ?? 0,
        is_active: row.active !== false,
        position,
      })),
    };
    expect(isMultiplePortionProduct(multiple)).toBe(true);
    expect(catalogPriceLabel(multiple).startsWith("From ")).toBe(true);
    expect(isMultiplePortionProduct({ price_options: [] })).toBe(false);
  });
});
