import { isDemoBusinessCode, PORTAL_SESSION_STORAGE_KEY, type DemoMarker } from "@ai-pos/shared-types";

/**
 * The portal session kept on this device.
 * The API has no separate refresh-token cookie. It reissues the bearer access token
 * from POST /api/v1/auth/refresh while that token is still accepted, including the
 * 120 second grace in app/core/deps.py. Passwords are never written here.
 */

export const PORTAL_SESSION_KEY = PORTAL_SESSION_STORAGE_KEY;
/** Keep this aligned with RENEWAL_GRACE_SECONDS in the API. */
export const RENEWAL_GRACE_MS = 120_000;

export interface StoredSession {
  token: string;
  expiresAt: number;
  /** Set only when this browser entered through the public demo exchange. */
  demo?: DemoMarker;
}

export interface SessionBucket {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** `use` is still inside its lifetime. `refresh` is inside the API grace. A demo past that grace is opened again. Anything else signs in again. */
export type RestorePlan = "use" | "refresh" | "reenter" | "sign-out";

export function restorePlan(session: StoredSession | null, now: number): RestorePlan {
  if (session === null) return "sign-out";
  if (session.expiresAt > now) return "use";
  if (now - session.expiresAt <= RENEWAL_GRACE_MS) return "refresh";
  if (session.demo) return "reenter";
  return "sign-out";
}

/** The server rejected this session. Network and server errors must not sign the user out. */
export function renewFailureSignsOut(status: number): boolean {
  return status === 401;
}

function parseSession(raw: string | null): StoredSession | null {
  if (raw === null || raw === "") return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSession> & { password?: unknown };
    if (typeof parsed.token !== "string" || parsed.token === "") return null;
    if (typeof parsed.expiresAt !== "number" || !Number.isFinite(parsed.expiresAt)) return null;
    if ("password" in parsed) return null;
    const demo = parseDemo(parsed.demo);
    return demo === null ? { token: parsed.token, expiresAt: parsed.expiresAt } : { token: parsed.token, expiresAt: parsed.expiresAt, demo };
  } catch {
    return null;
  }
}

function readKey(bucket: SessionBucket): string | null {
  try {
    return bucket.getItem(PORTAL_SESSION_KEY);
  } catch {
    return null;
  }
}

function removeKey(bucket: SessionBucket): void {
  try {
    bucket.removeItem(PORTAL_SESSION_KEY);
  } catch {
    // Private mode or a blocked storage area. The in-memory session still clears.
  }
}

export function readStoredSession(persistent: SessionBucket, legacy?: SessionBucket | null): StoredSession | null {
  const raw = readKey(persistent);
  const current = parseSession(raw);
  if (current) {
    if (legacy) removeKey(legacy);
    return current;
  }
  if (raw !== null) removeKey(persistent);
  if (!legacy) return null;
  const previousRaw = readKey(legacy);
  const previous = parseSession(previousRaw);
  if (previous === null) {
    if (previousRaw !== null) removeKey(legacy);
    return null;
  }
  try {
    writeStoredSession(persistent, previous);
  } catch {
    // This tab can still use the legacy value. The next successful sign-in writes the persistent copy.
  }
  removeKey(legacy);
  return previous;
}

function parseDemo(value: unknown): DemoMarker | null {
  if (value === undefined || value === null || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  if (typeof row.businessCode !== "string" || !isDemoBusinessCode(row.businessCode)) return null;
  if (typeof row.businessName !== "string" || row.businessName.trim() === "") return null;
  return { businessCode: row.businessCode, businessName: row.businessName };
}

export function writeStoredSession(persistent: SessionBucket, session: StoredSession): void {
  const body = JSON.parse(JSON.stringify({ token: session.token, expiresAt: session.expiresAt })) as StoredSession;
  if (session.demo) body.demo = { businessCode: session.demo.businessCode, businessName: session.demo.businessName };
  persistent.setItem(PORTAL_SESSION_KEY, JSON.stringify(body));
}

export function clearStoredSession(persistent: SessionBucket, legacy?: SessionBucket | null): void {
  removeKey(persistent);
  if (legacy) removeKey(legacy);
}
