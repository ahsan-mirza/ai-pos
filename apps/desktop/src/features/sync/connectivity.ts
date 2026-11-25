/** How the register talks about the server. Local SQLite does not depend on this probe. */

export const OFFLINE_NOTICE =
  "You're working offline. Local POS operations remain available. Pending changes will synchronize when a connection is restored.";

/** Shown when the PIN cannot be checked locally because this cashier has never unlocked here online. */
export const NO_CACHED_PIN =
  "The server is unreachable and this cashier has not unlocked this register online yet.";

/** The unlock keypad must not ask the cashier to start a localhost API. */
export function unlockFailureMessage(caught: unknown): string {
  const message = caught instanceof Error ? caught.message : String(caught);
  if (
    message.includes("Cannot reach the API") ||
    message.includes("backend is running") ||
    message.includes("localhost:8000")
  ) {
    return NO_CACHED_PIN;
  }
  return message;
}

export type LinkState = "online" | "offline" | "reconnecting" | "not_activated";

export type EndpointKind = "unactivated" | "https" | "development" | "insecure" | "invalid";

export function endpointKind(url: string, release: boolean): EndpointKind {
  const value = url.trim();
  if (value === "" || value.includes("not-activated")) return "unactivated";
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return "invalid";
  }
  const host = parsed.hostname.toLowerCase();
  const loopback = host === "localhost" || host === "127.0.0.1" || host === "::1";
  if (parsed.protocol === "https:") return "https";
  if (parsed.protocol === "http:" && loopback && !release) return "development";
  if (parsed.protocol === "http:" && loopback && release) return "insecure";
  if (parsed.protocol === "http:") return "insecure";
  return "invalid";
}

/** A configured address is never rewritten. An insecure remote is not called. */
export function mayProbe(kind: EndpointKind): boolean {
  return kind === "https" || kind === "development";
}

export function linkState(input: { reachable: boolean; syncing: boolean; activated: boolean }): LinkState {
  if (!input.activated) return "not_activated";
  if (input.syncing && !input.reachable) return "reconnecting";
  return input.reachable ? "online" : "offline";
}

export function linkMessage(state: LinkState, kind: EndpointKind): string {
  if (state === "not_activated") {
    return "This register is not activated. Local setup can continue. No remote server is assumed.";
  }
  if (kind === "insecure") {
    return "The configured server is not HTTPS, so AxizPOS will not send the register's data to it. Local POS operations remain available.";
  }
  if (kind === "invalid") {
    return "The configured server address is not a valid URL. Local POS operations remain available.";
  }
  if (state === "online") return "The register can reach its configured server. A submitted change is synchronized only after the server accepts it.";
  if (state === "reconnecting") return "Reconnecting. Local POS operations remain available. Pending changes stay queued until the server accepts them.";
  return OFFLINE_NOTICE;
}
