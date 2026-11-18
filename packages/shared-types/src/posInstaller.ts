import { isDemoBusinessCode, type DemoBusinessCode } from "./demoAccess.js";

/** Public version feed. A register and the marketing site both read this without a portal session. */
export const POS_INSTALLER_FEED_PATH = "/api/v1/downloads/latest.json";

/** Public file. The feed's `path` must be this exact value. */
export const POS_INSTALLER_DOWNLOAD_PATH = "/api/download/installer/win";

/** Filename the download endpoint sends in Content-Disposition. */
export const POS_INSTALLER_FILENAME = "AI-POS-Setup-latest.exe";

/** Selected demo business for a later enrollment handoff. The value is a public code, never a credential. */
export const POS_DEMO_BUSINESS_STORAGE_KEY = "ai-pos.pos-demo-business";

/** One-time connection file. The ticket is not placed in the installer URL. */
export const POS_DEMO_HANDOFF_FILENAME = "AxizPOS-Demo.posdemo";

export const POS_DEMO_ENROLL_PATH = "/api/v1/demo-access/pos/enroll";

const VERSION = /^\d+\.\d+\.\d+$/;
const SHA256 = /^[a-f0-9]{64}$/;

export type PosInstallerFailure = "unavailable" | "missing" | "invalid" | "download" | "network" | "browser";

export class PosInstallerError extends Error {
  readonly failure: PosInstallerFailure;

  constructor(failure: PosInstallerFailure) {
    super("pos_installer_failed");
    this.failure = failure;
  }
}

export function posInstallerMessage(failure: PosInstallerFailure): string {
  if (failure === "missing") return "No Windows installer has been published yet. Please try again later.";
  if (failure === "unavailable") return "The installer release is temporarily unavailable. Please try again shortly.";
  if (failure === "invalid") return "The installer release could not be verified. Please try again shortly.";
  if (failure === "download") return "The installer could not be downloaded. Please try again shortly.";
  if (failure === "network") return "Unable to connect. Please check your internet connection.";
  return "This browser could not start the download.";
}

export interface PosInstallerRelease {
  version: string;
  sha256: string;
  downloadUrl: string;
}

interface Address {
  origin: string;
  hostname: string;
  pathname: string;
  search: string;
  hash: string;
  protocol: string;
  toString: () => string;
}

function address(value: string, base?: string): Address {
  const Url = (globalThis as { URL?: new (input: string, base?: string) => Address }).URL;
  if (Url === undefined) throw new Error("URL is unavailable");
  return new Url(value, base);
}

function configuredOrigin(apiBaseUrl: string): Address {
  return address(apiBaseUrl.endsWith("/") ? apiBaseUrl : `${apiBaseUrl}/`);
}

function localHttp(origin: Address): boolean {
  return origin.protocol === "http:" && (origin.hostname === "localhost" || origin.hostname === "127.0.0.1");
}

/** Accepts the public latest.json body and builds a download URL on the configured API origin only. */
export function readPosInstallerRelease(body: unknown, apiBaseUrl: string): PosInstallerRelease | null {
  if (body === null || typeof body !== "object" || apiBaseUrl.trim() === "") return null;
  const row = body as Record<string, unknown>;
  if (typeof row.version !== "string" || !VERSION.test(row.version)) return null;
  if (typeof row.sha256 !== "string" || !SHA256.test(row.sha256.toLowerCase())) return null;
  if (row.notes !== null && row.notes !== undefined && typeof row.notes !== "string") return null;
  if (typeof row.pub_date !== "string" || row.pub_date.trim() === "") return null;
  if (row.path !== POS_INSTALLER_DOWNLOAD_PATH) return null;
  let origin: Address;
  let download: Address;
  try {
    origin = configuredOrigin(apiBaseUrl);
    download = address(POS_INSTALLER_DOWNLOAD_PATH, origin.toString());
  } catch {
    return null;
  }
  if (download.origin !== origin.origin) return null;
  if (download.pathname !== POS_INSTALLER_DOWNLOAD_PATH) return null;
  if (download.search !== "" || download.hash !== "") return null;
  if (origin.protocol !== "https:" && !localHttp(origin)) return null;
  const href = download.toString();
  if (href.includes("access_token") || href.includes("token=") || href.includes("@")) return null;
  return { version: row.version, sha256: row.sha256.toLowerCase(), downloadUrl: href };
}

interface FeedResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export async function loadPosInstallerRelease(
  apiBaseUrl: string,
  fetchImpl: (input: string, init: { method: string; headers: Record<string, string> }) => Promise<FeedResponse>,
): Promise<PosInstallerRelease> {
  const root = apiBaseUrl.replace(/\/$/, "");
  let response: FeedResponse;
  try {
    response = await fetchImpl(`${root}${POS_INSTALLER_FEED_PATH}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new PosInstallerError("network");
  }
  if (response.status === 404) throw new PosInstallerError("missing");
  if (!response.ok) throw new PosInstallerError("unavailable");
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new PosInstallerError("invalid");
  }
  const release = readPosInstallerRelease(body, root);
  if (release === null) throw new PosInstallerError("invalid");
  return release;
}

interface ByteResponse {
  ok: boolean;
  status: number;
  headers: { get: (name: string) => string | null };
  body: { getReader: () => { read: () => Promise<{ done: boolean; value?: Uint8Array }> } } | null;
}

export async function readPosInstallerBytes(
  release: PosInstallerRelease,
  fetchImpl: (input: string, init: { method: string }) => Promise<ByteResponse>,
  onProgress: (received: number, total: number | null) => void,
): Promise<{ bytes: Uint8Array; size: number | null }> {
  let response: ByteResponse;
  try {
    response = await fetchImpl(release.downloadUrl, { method: "GET" });
  } catch {
    throw new PosInstallerError("network");
  }
  if (!response.ok || response.body === null) throw new PosInstallerError("download");
  const rawLength = response.headers.get("content-length");
  const size = rawLength !== null && /^\d+$/.test(rawLength) ? Number(rawLength) : null;
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    let step: { done: boolean; value?: Uint8Array };
    try {
      step = await reader.read();
    } catch {
      throw new PosInstallerError("network");
    }
    if (step.done) break;
    const value = step.value ?? new Uint8Array();
    chunks.push(value);
    received += value.byteLength;
    onProgress(received, size);
  }
  if (size !== null && received !== size) throw new PosInstallerError("invalid");
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { bytes, size };
}

export function installerDigestMatches(actualHex: string, expectedHex: string): boolean {
  const actual = actualHex.toLowerCase();
  return SHA256.test(actual) && actual === expectedHex.toLowerCase();
}

export function formatInstallerSize(bytes: number): string | null {
  if (!Number.isFinite(bytes) || bytes < 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function posDemoHandoffDocument(ticket: string): string {
  const value = ticket.trim();
  if (value.length < 12 || value.length > 180 || /\s/.test(value) || !value.includes(".")) {
    throw new PosInstallerError("invalid");
  }
  return JSON.stringify({ version: 1, enrollment_ticket: value });
}

interface EnrollResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

/** Asks the public enroll endpoint for one ticket and returns the connection-file text. */
export async function requestPosDemoHandoff(
  apiBaseUrl: string,
  businessCode: string,
  fetchImpl: (input: string, init: { method: string; headers: Record<string, string>; body: string }) => Promise<EnrollResponse>,
): Promise<string> {
  if (!isDemoBusinessCode(businessCode)) throw new PosInstallerError("invalid");
  const root = apiBaseUrl.replace(/\/$/, "");
  let response: EnrollResponse;
  try {
    response = await fetchImpl(`${root}${POS_DEMO_ENROLL_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ business_code: businessCode }),
    });
  } catch {
    throw new PosInstallerError("network");
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new PosInstallerError("invalid");
  }
  const ticket =
    body !== null && typeof body === "object" && "enrollment_ticket" in body ? body.enrollment_ticket : null;
  const code = body !== null && typeof body === "object" && "business_code" in body ? body.business_code : null;
  if (!response.ok || typeof ticket !== "string" || code !== businessCode) {
    throw new PosInstallerError(response.status === 404 ? "unavailable" : "invalid");
  }
  return posDemoHandoffDocument(ticket);
}

export function rememberPosDemoBusiness(
  storage: { setItem: (key: string, value: string) => void },
  code: string,
): code is DemoBusinessCode {
  if (!isDemoBusinessCode(code)) return false;
  storage.setItem(POS_DEMO_BUSINESS_STORAGE_KEY, code);
  return true;
}
