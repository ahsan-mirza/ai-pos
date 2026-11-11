import { describe, expect, it } from "vitest";
import { scrollEdges, stepTarget } from "./CategoryScroller";

describe("category scroll edges", () => {
  it("hides controls when every category fits", () => {
    expect(scrollEdges(0, 200, 200, false)).toEqual({ overflow: false, atStart: true, atEnd: true });
    expect(scrollEdges(0, 201, 200, false).overflow).toBe(false);
  });

  it("enables only the later direction at the start of a long row", () => {
    expect(scrollEdges(0, 2400, 200, false)).toEqual({ overflow: true, atStart: true, atEnd: false });
  });

  it("enables only the earlier direction at the end", () => {
    expect(scrollEdges(2200, 2400, 200, false)).toEqual({ overflow: true, atStart: false, atEnd: true });
  });

  it("reads a negative RTL offset as distance from the first category", () => {
    expect(scrollEdges(0, 800, 200, true)).toEqual({ overflow: true, atStart: true, atEnd: false });
    expect(scrollEdges(-600, 800, 200, true)).toEqual({ overflow: true, atStart: false, atEnd: true });
  });

  it("steps toward later categories without passing the ends", () => {
    expect(stepTarget(0, 2400, 200, false, "later")).toBe(160);
    expect(stepTarget(2300, 2400, 200, false, "later")).toBe(2200);
    expect(stepTarget(400, 2400, 200, false, "earlier")).toBe(240);
    expect(stepTarget(0, 800, 200, true, "later")).toBe(-160);
    expect(stepTarget(-600, 800, 200, true, "earlier")).toBe(-440);
  });
});
