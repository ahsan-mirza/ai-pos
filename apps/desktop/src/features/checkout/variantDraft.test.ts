import { applyBulkToDrafts, mergeVariantDrafts, variantCombinations, variantDraftKey } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

const axes = [
  { key: "size", values: ["S", "M"] },
  { key: "color", values: ["Black", "White"] },
];

describe("fashion variant drafts", () => {
  it("builds every combination and keeps a stable key", () => {
    const combinations = variantCombinations(axes);
    expect(combinations).toHaveLength(4);
    expect(variantDraftKey({ color: "Black", size: "S" })).toBe("color=black|size=s");
    expect(variantDraftKey({ size: "S", color: "Black" })).toBe(variantDraftKey({ color: "black", size: "s" }));
  });

  it("regenerates without duplicating or restoring an excluded combination", () => {
    const defaults = { price: "49.00", opening: "0", reorder: "0", skuPrefix: "TEE", axisOrder: ["size", "color"] };
    const first = mergeVariantDrafts([], variantCombinations(axes), defaults);
    expect(first).toHaveLength(4);
    const excluded = first.map((row) =>
      row.attributes.size === "M" && row.attributes.color === "White" ? { ...row, included: false, price: "80.00", locked: { price: true } } : row,
    );
    const again = mergeVariantDrafts(excluded, variantCombinations(axes), defaults);
    expect(again).toHaveLength(4);
    const white = again.find((row) => row.attributes.size === "M" && row.attributes.color === "White");
    expect(white?.included).toBe(false);
    expect(white?.price).toBe("80.00");
    const wider = variantCombinations([
      { key: "size", values: ["S", "M", "L"] },
      { key: "color", values: ["Black", "White"] },
    ]);
    const added = mergeVariantDrafts(again, wider, defaults);
    expect(added).toHaveLength(6);
    expect(added.filter((row) => row.attributes.size === "S")).toHaveLength(2);
    expect(new Set(added.map((row) => row.sku)).size).toBe(6);
  });

  it("bulk fill skips a cell that was edited and existing stock", () => {
    const [first, second] = mergeVariantDrafts([], variantCombinations(axes), {
      price: "49.00",
      opening: "1",
      reorder: "0",
      skuPrefix: "TEE",
      axisOrder: ["size", "color"],
    });
    const rows = [
      { ...first!, price: "55.00", locked: { price: true } },
      { ...second!, existingId: "already", opening: "9", cost: "12.00" },
    ];
    const priced = applyBulkToDrafts(rows, "price", "40.00");
    expect(priced[0]?.price).toBe("55.00");
    expect(priced[1]?.price).toBe("40.00");
    const stocked = applyBulkToDrafts(priced, "opening", "3");
    expect(stocked[0]?.opening).toBe("3");
    expect(stocked[1]?.opening).toBe("9");
    const costed = applyBulkToDrafts(stocked, "cost", "4.00");
    expect(costed[1]?.cost).toBe("12.00");
    expect(costed[0]?.cost).toBe("4.00");
  });
});
