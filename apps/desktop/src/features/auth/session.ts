import { Permission, type TokenResponse } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { ApiUnavailableError, loginPin, unlockCashier } from "../../lib/api";
import { currentSession, inTauri, lockSession, pinLogin, unlockSelectedCashier, type CashierSession } from "../../lib/tauri";
import { rememberBrowserPin, unlockFromBrowserCache, type PinStore } from "./browserPin";
import { NO_CACHED_PIN } from "../sync/connectivity";

export type { CashierSession };

/** Same window the register already uses for a cached offline unlock. */
export const REGISTER_SESSION_SECS = 24 * 60 * 60;
const BROWSER_SESSION_KEY = "axiz.pos.cashier";
/** Lives in memory for this window. A refresh must ask for the PIN again before it can sync preferences. */
let accessToken: string | null = null;
if (import.meta.hot) {
  const kept = import.meta.hot.data.accessToken;
  if (typeof kept === "string" && kept !== "") accessToken = kept;
  import.meta.hot.dispose((data) => {
    data.accessToken = accessToken;
  });
}

/**
 * A stored cashier name is not a sign-in. Without the access token, retail calls
 * authenticate as the terminal and user-only routes refuse them.
 */
export function browserCashier(session: CashierSession | null, token: string | null): CashierSession | null {
  if (session === null || token === null || token === "") return null;
  return session;
}

export function currentAccessToken(): string | null {
  return accessToken;
}

/**
 * A refresh may restore this cashier's profile. The PIN and access token are never written here.
 * A profile for another store, or one older than the offline window, is discarded.
 * The profile alone does not sign the cashier in; `browserCashier` still requires the access token.
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

function pinStore(): PinStore | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage;
}

function cacheFailure(reason: "missing" | "invalid" | "locked" | "disabled"): Error {
  if (reason === "locked") return new Error("Too many failed attempts on this register. Try again in a few minutes.");
  if (reason === "disabled") return new Error("This account cannot unlock a register.");
  if (reason === "invalid") return new Error("Invalid username or credentials.");
  return new Error(NO_CACHED_PIN);
}

/**
 * The server is asked first. When it cannot be reached, the PIN is checked against the verifier
 * synced for this register. That path does not create an access token.
 */
async function onlineThenCached(
  pin: string,
  online: () => Promise<TokenResponse>,
  match: { userId?: string; username?: string },
): Promise<CashierSession> {
  try {
    const response = await online();
    const session = sessionFrom(response);
    const store = pinStore();
    if (store) {
      try {
        await rememberBrowserPin(session, pin, store);
      } catch {
        // A failed local cache must not block a server unlock.
      }
    }
    accessToken = response.access_token;
    return acceptUnlock(session);
  } catch (caught) {
    if (!(caught instanceof ApiUnavailableError)) throw caught;
    const store = pinStore();
    if (store === null) throw new Error(NO_CACHED_PIN);
    const local = await unlockFromBrowserCache({ ...match, pin, now: Math.floor(Date.now() / 1000) }, store);
    if (!local.ok) throw cacheFailure(local.reason);
    accessToken = null;
    return acceptUnlock(local.session);
  }
}

/** Tauri verifies online first, then against the local Argon2 cache. The browser uses the same order. */
export async function unlock(username: string, pin: string): Promise<CashierSession> {
  const normalized = username.trim().toLowerCase();
  if (inTauri()) {
    accessToken = null;
    return acceptUnlock(await pinLogin(normalized, pin));
  }
  return onlineThenCached(pin, () => loginPin(normalized, pin), { username: normalized });
}

/** A chosen profile. The PIN is still checked; selecting a card does not unlock the register. */
export async function unlockSelected(userId: string, pin: string): Promise<CashierSession> {
  if (inTauri()) {
    accessToken = null;
    return acceptUnlock(await unlockSelectedCashier(userId, pin));
  }
  return onlineThenCached(pin, () => unlockCashier(userId, pin), { userId });
}

export async function lock(): Promise<void> {
  accessToken = null;
  forgetBrowser();
  if (inTauri()) await lockSession();
}

/** Online permission refresh for the browser preview. A failure keeps the permissions from the last unlock. */
export async function refreshBrowserPermissions(): Promise<string[] | null> {
  if (inTauri()) return null;
  const token = currentAccessToken();
  if (!token) return null;
  try {
    const response = await fetch(`${env.apiBaseUrl}/api/v1/auth/me`, {
      headers: { ...previewHeaders(), Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { permissions?: unknown };
    if (!Array.isArray(body.permissions)) return null;
    return body.permissions.filter((item): item is string => typeof item === "string");
  } catch {
    return null;
  }
}

export async function restore(): Promise<CashierSession | null> {
  if (inTauri()) return currentSession();
  const accepted = acceptStoredSession(
    typeof localStorage === "undefined" ? null : localStorage.getItem(BROWSER_SESSION_KEY),
    Math.floor(Date.now() / 1000),
    env.storeId,
  );
  const signedIn = browserCashier(accepted, currentAccessToken());
  if (signedIn === null) forgetBrowser();
  return signedIn;
}
