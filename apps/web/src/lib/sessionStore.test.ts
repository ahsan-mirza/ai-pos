import { describe, expect, it } from "vitest";
import {
  PORTAL_SESSION_KEY,
  RENEWAL_GRACE_MS,
  clearStoredSession,
  readStoredSession,
  renewFailureSignsOut,
  restorePlan,
  writeStoredSession,
  type SessionBucket,
  type StoredSession,
} from "./sessionStore";

function bucket(initial: Record<string, string> = {}): SessionBucket & { dump: () => Record<string, string> } {
  const data = { ...initial };
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value;
    },
    removeItem: (key) => {
      delete data[key];
    },
    dump: () => ({ ...data }),
  };
}

const now = 1_700_000_000_000;

describe("portal session restoration", () => {
  it("keeps a valid session across a restart of the same store", () => {
    const persistent = bucket();
    const session: StoredSession = { token: "access-1", expiresAt: now + 60_000 };
    writeStoredSession(persistent, session);
    expect(JSON.parse(persistent.dump()[PORTAL_SESSION_KEY])).toEqual(session);
    expect(persistent.dump()[PORTAL_SESSION_KEY]).not.toContain("password");
    const restored = readStoredSession(persistent, bucket());
    expect(restored).toEqual(session);
    expect(restorePlan(restored, now)).toBe("use");
  });

  it("refreshes inside the API grace and signs out after it", () => {
    const inside: StoredSession = { token: "access-2", expiresAt: now - 30_000 };
    expect(restorePlan(inside, now)).toBe("refresh");
    const outside: StoredSession = { token: "access-3", expiresAt: now - RENEWAL_GRACE_MS - 1 };
    expect(restorePlan(outside, now)).toBe("sign-out");
    expect(restorePlan(null, now)).toBe("sign-out");
  });

  it("moves a tab session into persistent storage and drops the tab copy", () => {
    const persistent = bucket();
    const legacy = bucket({
      [PORTAL_SESSION_KEY]: JSON.stringify({ token: "from-tab", expiresAt: now + 5_000 }),
    });
    expect(readStoredSession(persistent, legacy)).toEqual({ token: "from-tab", expiresAt: now + 5_000 });
    expect(persistent.dump()[PORTAL_SESSION_KEY]).toContain("from-tab");
    expect(legacy.dump()[PORTAL_SESSION_KEY]).toBeUndefined();
  });

  it("drops a stored password and clears both stores on logout", () => {
    const poisoned = bucket({
      [PORTAL_SESSION_KEY]: JSON.stringify({ token: "access-4", expiresAt: now + 1, password: "secret" }),
    });
    expect(readStoredSession(poisoned, bucket())).toBeNull();
    expect(poisoned.dump()[PORTAL_SESSION_KEY]).toBeUndefined();
    const persistent = bucket();
    const legacy = bucket();
    writeStoredSession(persistent, { token: "access-5", expiresAt: now + 1 });
    writeStoredSession(legacy, { token: "old", expiresAt: now + 1 });
    clearStoredSession(persistent, legacy);
    expect(persistent.dump()[PORTAL_SESSION_KEY]).toBeUndefined();
    expect(legacy.dump()[PORTAL_SESSION_KEY]).toBeUndefined();
  });

  it("signs out only when the server rejects the session", () => {
    expect(renewFailureSignsOut(401)).toBe(true);
    expect(renewFailureSignsOut(0)).toBe(false);
    expect(renewFailureSignsOut(500)).toBe(false);
    expect(renewFailureSignsOut(403)).toBe(false);
  });
});
