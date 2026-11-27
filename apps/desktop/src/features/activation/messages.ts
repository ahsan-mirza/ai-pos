/** User-facing activation states. Raw server exceptions are not shown. */

export const SIGNING_UNAVAILABLE =
  "The server cannot currently issue a permanent device entitlement. Contact your administrator.";
export const KEY_MISMATCH =
  "The active signing key does not match a trusted desktop public key. Contact your administrator.";
export const SAME_STORE_PENDING =
  "Existing store detected. Your pending records will remain associated with this store and register.";
export const SYNC_ONE = "1 sale is waiting to sync. Synchronize it before retiring the previous register identity.";
export const DIFFERENT_STORE_PENDING =
  "This device contains transactions belonging to another store. Sync or export them before changing stores.";
export const API_UNAVAILABLE =
  "Your records are محفوظ locally. Reconnect to the original store to synchronize before migration.";
export const SERVER_UNREACHABLE =
  "Cannot reach the server. Check the store code and the internet connection.";
/** Matches the API activation window. Used when an older server omits the clock. */
export const ACTIVATION_WAIT_SECONDS = 600;

export function retrySeconds(text: string): number | null {
  if (!/too many activation attempts/i.test(text)) return null;
  const clock = /try again in (\d+):(\d{2})/i.exec(text);
  if (clock) return Number(clock[1]) * 60 + Number(clock[2]);
  return ACTIVATION_WAIT_SECONDS;
}

export function retryLabel(seconds: number): string {
  const left = Math.max(0, seconds);
  const minutes = Math.floor(left / 60);
  const rest = left % 60;
  return `Too many activation attempts. Try again in ${minutes}:${String(rest).padStart(2, "0")}.`;
}

/** Connection failures stay on screen. The server address does not. */
export function hideServerAddress(text: string): string | null {
  if (
    /could not reach|cannot reach the server/i.test(text) ||
    /\b\d{1,3}(?:\.\d{1,3}){3}\b/.test(text) ||
    /https?:\/\//i.test(text)
  ) {
    return SERVER_UNREACHABLE;
  }
  return null;
}

export function activationNotice(code: string, sales = 0): string {
  if (code === "entitlement_unconfigured") return SIGNING_UNAVAILABLE;
  if (code === "entitlement_key_mismatch") return KEY_MISMATCH;
  if (code === "pending_different_store") return DIFFERENT_STORE_PENDING;
  if (code === "pending_same_store" && sales > 0 && sales !== 1) {
    return `${sales} sales are waiting to sync. Synchronize them before retiring the previous register identity.`;
  }
  if (code === "pending_same_store" && sales === 1) return SYNC_ONE;
  if (code === "pending_same_store") return SAME_STORE_PENDING;
  if (code === "network") return API_UNAVAILABLE;
  return "";
}
