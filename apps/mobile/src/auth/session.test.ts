/// <reference types="jest" />
import { parseSession, restorePlan, renewFailureSignsOut } from "@/auth/session";

describe("session", () => {
  const now = 1_000_000;

  it("signs out when nothing is stored", () => {
    expect(restorePlan(null, now)).toBe("sign-out");
  });

  it("uses a token that has not expired", () => {
    expect(restorePlan({ token: "a", expiresAt: now + 1 }, now)).toBe("use");
  });

  it("refreshes inside the grace window", () => {
    expect(restorePlan({ token: "a", expiresAt: now - 1_000 }, now)).toBe("refresh");
  });

  it("signs out after the grace window", () => {
    expect(restorePlan({ token: "a", expiresAt: now - 130_000 }, now)).toBe("sign-out");
  });

  it("rejects stored passwords", () => {
    expect(parseSession(JSON.stringify({ token: "a", expiresAt: 1, password: "no" }))).toBeNull();
  });

  it("only treats 401 as a dead session", () => {
    expect(renewFailureSignsOut(401)).toBe(true);
    expect(renewFailureSignsOut(500)).toBe(false);
    expect(renewFailureSignsOut(0)).toBe(false);
  });
});
