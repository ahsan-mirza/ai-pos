import { describe, expect, it } from "vitest";
import { chargeGate } from "./checkout";

const ready = { pharmacyCatalog: false, offline: true, profileReady: true, subscriptionLocked: false };

describe("permanent entitlement selling gate", () => {
  it("keeps a fresh lease on the existing offline queue path", () => {
    expect(chargeGate({ ...ready, hold: null })).toBeNull();
  });

  it("does not let a stale lease cancel a verified permanent entitlement", () => {
    const now = 2_000_000_000_000;
    const seen = now - 25 * 60 * 60 * 1000;
    expect(now - seen).toBeGreaterThan(24 * 60 * 60 * 1000);
    expect(chargeGate({ ...ready, hold: "lease", entitlementValid: true })).toBeNull();
  });

  it("still blocks a server-reported subscription and pharmacy medicine sales", () => {
    expect(chargeGate({ ...ready, hold: "server", entitlementValid: true })).toMatch(
      /subscription is verified/,
    );
    expect(
      chargeGate({
        ...ready,
        pharmacyCatalog: true,
        hold: "lease",
        entitlementValid: true,
      }),
    ).toMatch(/live connection/);
  });

  it("blocks a stale lease when there is no permanent entitlement", () => {
    expect(chargeGate({ ...ready, hold: "lease", entitlementValid: false })).toMatch(/subscription is verified/);
  });
});
