import { describe, expect, it } from "vitest";
import { priceOptionsPayload } from "./menuEntry";

const cents = (price: string) => {
  const trimmed = price.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return Math.round(value * 100);
};

describe("menu priced options", () => {
  it("keeps a single base price when no option is filled", () => {
    expect(priceOptionsPayload([{ name: "", price: "" }, { name: "", price: "" }], cents)).toBeNull();
  });

  it("refuses one priced option", () => {
    expect(() => priceOptionsPayload([{ name: "Lunch", price: "12" }, { name: "", price: "" }], cents)).toThrow(/two named prices/);
  });

  it("keeps an inactive portion and refuses a list with none active", () => {
    expect(
      priceOptionsPayload(
        [
          { name: "Small Plate", price: "3", active: true },
          { name: "Full Plate", price: "9", active: false },
        ],
        cents,
      )?.options.map((option) => option.is_active),
    ).toEqual([true, false]);
    expect(() =>
      priceOptionsPayload(
        [
          { name: "Small Plate", price: "3", active: false },
          { name: "Full Plate", price: "9", active: false },
        ],
        cents,
      ),
    ).toThrow(/stay active/);
  });

  it("keeps portion ids when a price is edited", () => {
    expect(
      priceOptionsPayload(
        [
          { id: "small", name: "Small Plate", price: "3.00", active: true },
          { id: "full", name: "Full Plate", price: "9.00", active: true },
        ],
        cents,
      ),
    ).toEqual({
      options: [
        { id: "small", name: "Small Plate", price_cents: 300, is_active: true, position: 0 },
        { id: "full", name: "Full Plate", price_cents: 900, is_active: true, position: 1 },
      ],
    });
  });

  it("saves two named prices separately from the base price", () => {
    expect(
      priceOptionsPayload(
        [
          { name: "Small", price: "8.50" },
          { name: "Large", price: "12" },
        ],
        cents,
      ),
    ).toEqual({
      options: [
        { name: "Small", price_cents: 850, is_active: true, position: 0 },
        { name: "Large", price_cents: 1200, is_active: true, position: 1 },
      ],
    });
  });
});
