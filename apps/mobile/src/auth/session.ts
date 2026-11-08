/** Kept aligned with the portal session rules and the API renewal grace (120 seconds). */

export const RENEWAL_GRACE_MS = 120_000;

export interface StoredSession {
  token: string;
  expiresAt: number;
}

export type RestorePlan = "use" | "refresh" | "sign-out";

export function restorePlan(session: StoredSession | null, now: number): RestorePlan {
  if (session === null) return "sign-out";
  if (session.expiresAt > now) return "use";
  if (now - session.expiresAt <= RENEWAL_GRACE_MS) return "refresh";
  return "sign-out";
}

export function renewFailureSignsOut(status: number): boolean {
  return status === 401;
}

export function parseSession(raw: string | null): StoredSession | null {
  if (raw === null || raw === "") return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSession> & { password?: unknown };
    if (typeof parsed.token !== "string" || parsed.token === "") return null;
    if (typeof parsed.expiresAt !== "number" || !Number.isFinite(parsed.expiresAt)) return null;
    if ("password" in parsed) return null;
    return { token: parsed.token, expiresAt: parsed.expiresAt };
  } catch {
    return null;
  }
}
