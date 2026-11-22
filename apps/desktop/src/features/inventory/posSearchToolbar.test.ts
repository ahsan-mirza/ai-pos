import { describe, expect, it } from "vitest";
import { posSearchToolbarClass, posSearchToolbarRefreshClass, posSearchToolbarSearchClass, posSearchToolbarStatusClass } from "./ui";

describe("POS search toolbar", () => {
  it("keeps search, status, and refresh on one row", () => {
    expect(posSearchToolbarClass).toContain("flex");
    expect(posSearchToolbarClass).toContain("flex-nowrap");
    expect(posSearchToolbarClass).toContain("items-center");
    expect(posSearchToolbarClass).toContain("min-w-0");
    expect(posSearchToolbarClass).not.toContain("flex-wrap");
  });

  it("lets search grow and keeps the status and refresh from stretching", () => {
    expect(posSearchToolbarSearchClass).toContain("flex-1");
    expect(posSearchToolbarSearchClass).toContain("min-w-[11.25rem]");
    expect(posSearchToolbarStatusClass).toContain("min-w-[11.25rem]");
    expect(posSearchToolbarStatusClass).toContain("w-auto");
    expect(posSearchToolbarStatusClass).toContain("pr-12");
    expect(posSearchToolbarStatusClass).toContain("appearance-none");
    expect(posSearchToolbarRefreshClass).toContain("h-12");
    expect(posSearchToolbarRefreshClass).toContain("w-12");
    expect(posSearchToolbarRefreshClass).toContain("shrink-0");
  });
});
