import { clampPage, pageCount, pageOffset, pageRange, pageWindow } from "@ai-pos/ui";
import { describe, expect, it } from "vitest";

describe("pagination math", () => {
  it("counts pages and never returns zero", () => {
    expect(pageCount(383, 25)).toBe(16);
    expect(pageCount(0, 25)).toBe(1);
    expect(pageCount(25, 25)).toBe(1);
  });

  it("clamps pages into range", () => {
    expect(clampPage(0, 5)).toBe(1);
    expect(clampPage(9, 5)).toBe(5);
    expect(clampPage(Number.NaN, 5)).toBe(1);
  });

  it("maps pages to API offsets", () => {
    expect(pageOffset(1, 25)).toBe(0);
    expect(pageOffset(3, 25)).toBe(50);
  });

  it("describes the visible range", () => {
    expect(pageRange(1, 25, 383)).toEqual({ from: 1, to: 25 });
    expect(pageRange(16, 25, 383)).toEqual({ from: 376, to: 383 });
    expect(pageRange(1, 25, 0)).toEqual({ from: 0, to: 0 });
  });

  it("windows page buttons with ellipses at a constant length", () => {
    expect(pageWindow(1, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageWindow(1, 16)).toEqual([1, 2, 3, 4, 5, "ellipsis-end", 16]);
    expect(pageWindow(8, 16)).toEqual([1, "ellipsis-start", 7, 8, 9, "ellipsis-end", 16]);
    expect(pageWindow(16, 16)).toEqual([1, "ellipsis-start", 12, 13, 14, 15, 16]);
    for (let page = 1; page <= 16; page += 1) {
      const items = pageWindow(page, 16);
      expect(items).toHaveLength(7);
      expect(items).toContain(page);
    }
  });
});
