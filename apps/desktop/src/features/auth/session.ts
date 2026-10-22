import { Permission } from "@ai-pos/shared-types";
import { loginPin } from "../../lib/api";
import { currentSession, inTauri, lockSession, pinLogin, type CashierSession } from "../../lib/tauri";

export type { CashierSession };

/** Tauri verifies online first, then against the local Argon2 cache. The browser preview is online only. */
export async function unlock(username: string, pin: string): Promise<CashierSession> {
  const session = inTauri() ? await pinLogin(username, pin) : await browserUnlock(username, pin);
  if (!session.user.permissions.includes(Permission.PosAccess)) {
    await lock();
    throw new Error("This account cannot unlock a register.");
  }
  return session;
}

async function browserUnlock(username: string, pin: string): Promise<CashierSession> {
  const response = await loginPin(username.trim().toLowerCase(), pin);
  return {
    user: {
      id: response.user.id,
      username: response.user.username,
      full_name: response.user.full_name,
      store_id: response.user.store_id,
      role_name: response.user.role.name,
      permissions: response.user.permissions,
      max_discount_bps: response.user.role.max_discount_bps ?? null,
    },
    mode: "online",
    unlocked_at: Math.floor(Date.now() / 1000),
  };
}

export async function lock(): Promise<void> {
  if (inTauri()) await lockSession();
}

export async function restore(): Promise<CashierSession | null> {
  return inTauri() ? currentSession() : null;
}
