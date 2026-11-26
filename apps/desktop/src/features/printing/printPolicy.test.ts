import { describe, expect, it } from "vitest";
import { shouldKickDrawer } from "./print";

describe("cash drawer kick policy", () => {
  const enabled = { drawer_kick: true, transport: "windows" as const };

  it("kicks only when cash was taken and the register policy allows it", () => {
    expect(shouldKickDrawer({ kickDrawer: true }, enabled)).toBe(true);
    expect(shouldKickDrawer({ kickDrawer: false }, enabled)).toBe(false);
    expect(shouldKickDrawer({ kickDrawer: true }, { ...enabled, drawer_kick: false })).toBe(false);
    expect(shouldKickDrawer({ kickDrawer: true }, { ...enabled, transport: "none" })).toBe(false);
    expect(shouldKickDrawer({ kickDrawer: true }, { ...enabled, drawer_connection: "none" })).toBe(false);
    expect(shouldKickDrawer({ kickDrawer: true }, { drawer_kick: true, transport: "none", drawer_connection: "separate" })).toBe(true);
    expect(shouldKickDrawer({ kickDrawer: false }, enabled)).toBe(false);
  });

  it("does not kick for card, failed, cancelled, or replayed sales", () => {
    expect(shouldKickDrawer({ kickDrawer: false }, enabled)).toBe(false);
  });
});
