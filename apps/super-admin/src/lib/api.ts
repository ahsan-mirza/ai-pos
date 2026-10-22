function apiBase(): string {
  const raw = (import.meta.env.VITE_CONSOLE_API_BASE_URL ?? "").trim().replace(/\/$/, "");
  if (raw === "" || raw === "same-origin") {
    return typeof window === "undefined" ? "" : window.location.origin;
  }
  return raw;
}
const PREFIX = "/api/v1/super-admin";
const STORAGE_KEY = "qios.console.session";

export class ConsoleError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: Record<string, unknown> | null;

  constructor(message: string, status: number, code: string | null, details: Record<string, unknown> | null = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let token: string | null = sessionStorage.getItem(STORAGE_KEY);
let onSignedOut: (() => void) | null = null;

/** The session lives for this browser tab only (sessionStorage), never in localStorage. */
export function setToken(next: string | null): void {
  token = next;
  if (next) sessionStorage.setItem(STORAGE_KEY, next);
  else sessionStorage.removeItem(STORAGE_KEY);
}

export function hasToken(): boolean {
  return token !== null;
}

export function onSignOut(handler: (() => void) | null): void {
  onSignedOut = handler;
}

export interface Page<T> {
  rows: T[];
  total: number;
}

async function exchange<T>(method: string, path: string, body?: unknown): Promise<{ data: T; headers: Headers }> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${PREFIX}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ConsoleError(`Cannot reach the API at ${apiBase() || "(VITE_CONSOLE_API_BASE_URL unset)"}.`, 0, "api_unreachable");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    let code: string | null = null;
    let details: Record<string, unknown> | null = null;
    try {
      const parsed = (await response.json()) as { error?: { message?: string; code?: string; details?: Record<string, unknown> } };
      message = parsed.error?.message ?? message;
      code = parsed.error?.code ?? null;
      details = parsed.error?.details ?? null;
    } catch {
      // Not JSON.
    }
    if (response.status === 401 && path !== "/auth/login") {
      setToken(null);
      onSignedOut?.();
    }
    throw new ConsoleError(message, response.status, code, details);
  }
  return { data: (await response.json()) as T, headers: response.headers };
}

export const api = {
  get: async <T>(path: string) => (await exchange<T>("GET", path)).data,
  post: async <T>(path: string, body: unknown) => (await exchange<T>("POST", path, body)).data,
  put: async <T>(path: string, body: unknown) => (await exchange<T>("PUT", path, body)).data,
  patch: async <T>(path: string, body: unknown) => (await exchange<T>("PATCH", path, body)).data,
  page: async <T>(path: string): Promise<Page<T>> => {
    const { data, headers } = await exchange<T[]>("GET", path);
    const total = Number(headers.get("X-Total-Count"));
    return { rows: data, total: Number.isFinite(total) && headers.has("X-Total-Count") ? total : data.length };
  },
};

export function errorText(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}
