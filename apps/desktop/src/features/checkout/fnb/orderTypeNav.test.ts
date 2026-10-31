import { describe, expect, it } from "vitest";
import { changeTypeGate, sectionChoices } from "./orderTypeNav";

describe("order type navigation", () => {
  it("opens a type switch when the order is empty", () => {
    expect(changeTypeGate(0, 0, false)).toBe("switch");
  });

  it("asks before switching once the cart or the ticket has items", () => {
    expect(changeTypeGate(2, 0, false)).toBe("confirm");
    expect(changeTypeGate(0, 1, false)).toBe("confirm");
  });

  it("blocks a switch after the kitchen has the order", () => {
    expect(changeTypeGate(1, 1, true)).toBe("blocked");
  });

  it("lists only configured sections", () => {
    expect(
      sectionChoices([
        { id: "hall", name: "Main Hall", is_active: true, tables: [{}] },
        { id: "old", name: "Closed", is_active: false, tables: [{}] },
        { id: "empty", name: "Empty", is_active: true, tables: [] },
      ]),
    ).toEqual([{ id: "hall", name: "Main Hall" }]);
    expect(sectionChoices([])).toEqual([]);
  });
});
