import { Permission } from "@ai-pos/shared-types";
import type { CashierSession } from "../../lib/tauri";

const STORAGE_KEY = "axiz.pos.pin-cache";
const MAX_ATTEMPTS = 5;
const LOCKOUT_SECS = 5 * 60;
const DEFAULT_ITERATIONS = 100_000;

export interface PinStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

interface PinRecord {
  userId: string;
  username: string;
  salt: string;
  hash: string;
  iterations: number;
  failedAttempts: number;
  lockedUntil: number | null;
  profile: CashierSession["user"];
}

export type BrowserPinResult =
  | { ok: true; session: CashierSession }
  | { ok: false; reason: "missing" | "invalid" | "locked" | "disabled" };

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function sameBytes(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) diff |= (left[index] ?? 0) ^ (right[index] ?? 0);
  return diff === 0;
}

async function derive(pin: string, salt: Uint8Array, iterations: number): Promise<Uint8Array> {
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    material,
    256,
  );
  return new Uint8Array(bits);
}

function readAll(store: PinStore): PinRecord[] {
  const raw = store.getItem(STORAGE_KEY);
  if (raw === null || raw === "") return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((row): row is PinRecord => {
      if (row === null || typeof row !== "object") return false;
      const record = row as Partial<PinRecord>;
      return typeof record.userId === "string" && typeof record.username === "string" && typeof record.hash === "string" && typeof record.salt === "string";
    });
  } catch {
    return [];
  }
}

function writeAll(store: PinStore, records: PinRecord[]): void {
  store.setItem(STORAGE_KEY, JSON.stringify(records));
}

function findRecord(records: PinRecord[], match: { userId?: string; username?: string }): PinRecord | undefined {
  if (match.userId) return records.find((record) => record.userId === match.userId);
  const username = match.username?.trim().toLowerCase();
  if (!username) return undefined;
  return records.find((record) => record.username === username);
}

/** Saves a verifier after a server unlock. The PIN itself is not stored, and no access token is stored. */
export async function rememberBrowserPin(
  session: CashierSession,
  pin: string,
  store: PinStore,
  iterations = DEFAULT_ITERATIONS,
): Promise<void> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await derive(pin, salt, iterations);
  const records = readAll(store).filter((record) => record.userId !== session.user.id);
  records.push({
    userId: session.user.id,
    username: session.user.username.trim().toLowerCase(),
    salt: bytesToBase64(salt),
    hash: bytesToBase64(hash),
    iterations,
    failedAttempts: 0,
    lockedUntil: null,
    profile: session.user,
  });
  writeAll(store, records);
}

/**
 * Checks a PIN against the verifier saved at the last online unlock.
 * A match opens an offline session and does not create an access token.
 */
export async function unlockFromBrowserCache(
  match: { userId?: string; username?: string; pin: string; now: number },
  store: PinStore,
): Promise<BrowserPinResult> {
  const records = readAll(store);
  const record = findRecord(records, match);
  if (!record) return { ok: false, reason: "missing" };
  if (record.lockedUntil !== null && record.lockedUntil > match.now) return { ok: false, reason: "locked" };
  const hash = await derive(match.pin, base64ToBytes(record.salt), record.iterations);
  if (!sameBytes(hash, base64ToBytes(record.hash))) {
    const attempts = record.failedAttempts + 1;
    record.failedAttempts = attempts >= MAX_ATTEMPTS ? 0 : attempts;
    record.lockedUntil = attempts >= MAX_ATTEMPTS ? match.now + LOCKOUT_SECS : null;
    writeAll(store, records);
    return { ok: false, reason: "invalid" };
  }
  record.failedAttempts = 0;
  record.lockedUntil = null;
  writeAll(store, records);
  if (!record.profile.permissions.includes(Permission.PosAccess)) return { ok: false, reason: "disabled" };
  return {
    ok: true,
    session: {
      user: record.profile,
      mode: "offline",
      unlocked_at: match.now,
    },
  };
}
