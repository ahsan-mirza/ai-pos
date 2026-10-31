import { describe, expect, it } from "vitest";
import { catalogGridClass } from "../../components/RegisterLayout";
import { cardKind, catalogCardClass, productCode, productDetail, stockTone, stockUnit } from "./catalogCard";

describe("catalogue card slots", () => {
  it("keeps a sku line and a two-line detail even when fields are missing", () => {
    expect(productCode("  ", null)).toBe("");
    expect(productCode("SKU-1", "  ")).toBe("SKU-1");
    expect(productCode("SKU-1", "MDL-9")).toBe("SKU-1 · MDL-9");
    expect(productDetail(undefined)).toBe("");
    expect(productDetail({ ram: "16GB", disk: "512GB" })).toBe("16GB · 512GB");
  });

  it("keeps a two-line name and a compact footer, without a sku or description line", () => {
    expect(catalogCardClass.name).toContain("line-clamp-2");
    expect(catalogCardClass.name).toContain("min-h-10");
    expect(catalogCardClass).not.toHaveProperty("code");
    expect(catalogCardClass).not.toHaveProperty("detail");
    expect(catalogCardClass.footer).toContain("min-h-10");
    expect(catalogCardClass.footer).toContain("flex-nowrap");
  });

  it("follows the tenant business type and the branch reorder point", () => {
    expect(cardKind("restaurant")).toBe("menu");
    expect(cardKind("cafe")).toBe("menu");
    expect(cardKind("quick_service")).toBe("menu");
    expect(cardKind("grocery")).toBe("stock");
    expect(cardKind("electronics_wholesale")).toBe("stock");
    expect(cardKind("wholesale_retail")).toBe("stock");
    expect(cardKind("retail_fashion")).toBe("stock");
    expect(stockTone({ tracked: false, available: 4 })).toBe("untracked");
    expect(stockTone({ tracked: true, available: 0, onHand: 2 })).toBe("out");
    expect(stockTone({ tracked: true, available: 3, onHand: 3, reorder: 5 })).toBe("low");
    expect(stockTone({ tracked: true, available: 8 })).toBe("in");
    expect(stockUnit({ sold_by_weight: true })).toBe("");
    expect(stockUnit({ sellable_units: ["PIECE"] })).toBe("Pieces");
  });

  it("stretches every density so cards in a row share one height", () => {
    for (const density of ["compact", "comfortable", "large"] as const) {
      const grid = catalogGridClass(density);
      expect(grid).toContain("items-stretch");
      expect(grid).toContain("[&>li]:h-full");
      expect(grid).toContain("[&>li]:min-w-0");
    }
  });
});
