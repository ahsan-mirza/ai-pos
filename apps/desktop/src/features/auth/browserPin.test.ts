import { Permission } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import type { CashierSession } from "../../lib/tauri";
import { rememberBrowserPin, unlockFromBrowserCache, type PinStore } from "./browserPin";

class MemoryStore implements PinStore {
  private values = new Map<string, string>();
  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

function session(): CashierSession {
  return {
    user: {
      id: "cashier-1",
      username: "ahsan",
      full_name: "Ahsan",
      store_id: "store-a",
      role_name: "Super Admin",
      permissions: [Permission.PosAccess],
      max_discount_bps: null,
      addon_modules: [],
      addon_synced_at: 1,
      avatar_url: null,
    },
    mode: "online",
    unlocked_at: 10,
  };
}

describe("browser PIN cache", () => {
  it("unlocks offline after an online unlock and does not keep the PIN or a token", async () => {
    const store = new MemoryStore();
    await rememberBrowserPin(session(), "1234", store, 1_000);
    const raw = store.getItem("axiz.pos.pin-cache") ?? "";
    expect(raw).not.toContain("1234");
    expect(raw).not.toContain("access_token");

    const opened = await unlockFromBrowserCache({ userId: "cashier-1", pin: "1234", now: 20 }, store);
    expect(opened.ok).toBe(true);
    if (opened.ok) {
      expect(opened.session.mode).toBe("offline");
      expect(opened.session.user.full_name).toBe("Ahsan");
    }
    const wrong = await unlockFromBrowserCache({ username: "ahsan", pin: "0000", now: 21 }, store);
    expect(wrong).toEqual({ ok: false, reason: "invalid" });
    const missing = await unlockFromBrowserCache({ userId: "other", pin: "1234", now: 22 }, store);
    expect(missing).toEqual({ ok: false, reason: "missing" });
  });

  it("locks the cached cashier after five wrong PINs", async () => {
    const store = new MemoryStore();
    await rememberBrowserPin(session(), "1234", store, 1_000);
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const result = await unlockFromBrowserCache({ userId: "cashier-1", pin: "9999", now: 30 }, store);
      expect(result.ok).toBe(false);
    }
    const locked = await unlockFromBrowserCache({ userId: "cashier-1", pin: "1234", now: 31 }, store);
    expect(locked).toEqual({ ok: false, reason: "locked" });
  });
});