import { Permission, type TokenResponse } from "@ai-pos/shared-types";
import { env } from "../../config/env";
import { loginPin, unlockCashier } from "../../lib/api";
import { currentSession, inTauri, lockSession, pinLogin, unlockSelectedCashier, type CashierSession } from "../../lib/tauri";

export type { CashierSession };

/** Same window the register already uses for a cached offline unlock. */
export const REGISTER_SESSION_SECS = 24 * 60 * 60;
const BROWSER_SESSION_KEY = "axiz.pos.cashier";

/**
 * A refresh may restore this cashier. The PIN and access token are never written here.
 * A profile for another store, or one older than the offline window, is discarded.
 */
export function acceptStoredSession(raw: string | null, now: number, storeId: string): CashierSession | null {
  if (raw === null || raw === "") return null;
  let session: CashierSession;
  try {
    session = JSON.parse(raw) as CashierSession;
  } catch {
    return null;
  }
  if (!session?.user?.id || !Array.isArray(session.user.permissions)) return null;
  if (!session.user.permissions.includes(Permission.PosAccess)) return null;
  if (session.user.store_id != null && session.user.store_id !== storeId) return null;
  if (typeof session.unlocked_at !== "number") return null;
  if (now < session.unlocked_at || now - session.unlocked_at > REGISTER_SESSION_SECS) return null;
  return session;
}

function rememberBrowser(session: CashierSession): void {
  if (inTauri() || typeof localStorage === "undefined") return;
  localStorage.setItem(BROWSER_SESSION_KEY, JSON.stringify(session));
}

function forgetBrowser(): void {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(BROWSER_SESSION_KEY);
}

function sessionFrom(response: TokenResponse): CashierSession {
  return {
    user: {
      id: response.user.id,
      username: response.user.username,
      full_name: response.user.full_name,
      store_id: response.user.store_id,
      role_name: response.user.role.name,
      permissions: response.user.permissions,
      max_discount_bps: response.user.role.max_discount_bps ?? null,
      addon_modules: response.user.addon_modules ?? [],
      addon_synced_at: Math.floor(Date.now() / 1000),
      avatar_url: response.user.avatar_url ?? null,
    },
    mode: "online",
    unlocked_at: Math.floor(Date.now() / 1000),
  };
}

async function acceptUnlock(session: CashierSession): Promise<CashierSession> {
  if (!session.user.permissions.includes(Permission.PosAccess)) {
    await lock();
    throw new Error("This account cannot unlock a register.");
  }
  rememberBrowser(session);
  return session;
}

/** Tauri verifies online first, then against the local Argon2 cache. The browser preview is online only. */
export async function unlock(username: string, pin: string): Promise<CashierSession> {
  const session = inTauri() ? await pinLogin(username, pin) : sessionFrom(await loginPin(username.trim().toLowerCase(), pin));
  return acceptUnlock(session);
}

/** A chosen profile. The PIN is still checked; selecting a card does not unlock the register. */
export async function unlockSelected(userId: string, pin: string): Promise<CashierSession> {
  const session = inTauri()
    ? await unlockSelectedCashier(userId, pin)
    : sessionFrom(await unlockCashier(userId, pin));
  return acceptUnlock(session);
}

export async function lock(): Promise<void> {
  forgetBrowser();
  if (inTauri()) await lockSession();
}

export async function restore(): Promise<CashierSession | null> {
  if (inTauri()) return currentSession();
  const accepted = acceptStoredSession(
    typeof localStorage === "undefined" ? null : localStorage.getItem(BROWSER_SESSION_KEY),
    Math.floor(Date.now() / 1000),
    env.storeId,
  );
  if (accepted === null) forgetBrowser();
  return accepted;
}
