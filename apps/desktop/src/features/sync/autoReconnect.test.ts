import { describe, expect, it } from "vitest";
import { reconnectPlan } from "./autoReconnect";

describe("reconnect plan", () => {
  it("syncs as soon as the server answers and again on the interval", () => {
    expect(reconnectPlan({ wasUp: false, up: true, sinceFlushMs: 0, intervalMs: 15_000 })).toEqual({
      flush: true,
      restored: true,
    });
    expect(reconnectPlan({ wasUp: true, up: true, sinceFlushMs: 4_000, intervalMs: 15_000 })).toEqual({
      flush: false,
      restored: false,
    });
    expect(reconnectPlan({ wasUp: true, up: true, sinceFlushMs: 15_000, intervalMs: 15_000 })).toEqual({
      flush: true,
      restored: false,
    });
  });

  it("does not sync while the server is unreachable", () => {
    expect(reconnectPlan({ wasUp: true, up: false, sinceFlushMs: 60_000, intervalMs: 15_000 })).toEqual({
      flush: false,
      restored: false,
    });
  });
});
