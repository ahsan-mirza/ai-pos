import { describe, expect, it } from "vitest";
import { SEARCH_DEBOUNCE_MS } from "@ai-pos/shared-types";
import { POS_SEARCH_DEBOUNCE_MS, beginRequest, posButtonRadius, posButtonSize, posButtonVariant, posIconButtonSize } from "./posControls";

describe("POS search and buttons", () => {
  it("uses the shared search debounce", () => {
    expect(POS_SEARCH_DEBOUNCE_MS).toBe(SEARCH_DEBOUNCE_MS);
    expect(POS_SEARCH_DEBOUNCE_MS).toBe(150);
  });

  it("ignores a response after a newer request starts", () => {
    const gate = { current: 0 };
    const first = beginRequest(gate);
    const second = beginRequest(gate);
    expect(first()).toBe(false);
    expect(second()).toBe(true);
  });

  it("gives every button variant the same rounded rectangle", () => {
    expect(posButtonRadius).toBe("rounded-xl");
    for (const variant of Object.values(posButtonVariant)) {
      expect(variant).not.toContain("rounded-full");
      expect(variant).not.toContain("rounded-xl");
    }
    expect(posButtonSize.md).toContain("h-12");
    expect(posButtonSize.sm).toContain("h-9");
    expect(posButtonSize.lg).toContain("h-14");
    expect(posIconButtonSize.xs).toContain("--pos-control-sm");
  });
});
