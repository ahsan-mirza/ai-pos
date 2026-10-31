import { Permission } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { acceptStoredSession, REGISTER_SESSION_SECS, type CashierSession } from "./session";

const STORE = "store-a";

function stored(overrides: Partial<CashierSession> = {}): string {
  const session: CashierSession = {
    user: {
      id: "cashier-1",
      username: "ahsan",
      full_name: "Ahsan",
      store_id: STORE,
      role_name: "Cashier",
      permissions: [Permission.PosAccess],
      max_discount_bps: null,
      addon_modules: [],
      addon_synced_at: 1_000,
      avatar_url: null,
    },
    mode: "online",
    unlocked_at: 10_000,
    ...overrides,
  };
  return JSON.stringify(session);
}

describe("acceptStoredSession", () => {
  it("restores a cashier inside the offline window", () => {
    const session = acceptStoredSession(stored(), 10_000 + 60, STORE);
    expect(session?.user.username).toBe("ahsan");
  });

  it("drops a session after the window and one for another store", () => {
    expect(acceptStoredSession(stored(), 10_000 + REGISTER_SESSION_SECS + 1, STORE)).toBeNull();
    expect(acceptStoredSession(stored(), 10_500, "store-b")).toBeNull();
  });

  it("drops a profile that can no longer unlock a register", () => {
    const raw = stored();
    const parsed = JSON.parse(raw) as CashierSession;
    parsed.user.permissions = [];
    expect(acceptStoredSession(JSON.stringify(parsed), 10_100, STORE)).toBeNull();
    expect(acceptStoredSession("{", 10_100, STORE)).toBeNull();
  });
});
