import { env } from "../config/env";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: unknown;

  constructor(message: string, status: number, code: string | null = null, details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** fetch() only throws when no response arrived: the server is down, the address is wrong, or CORS blocked it. */
function unreachable(): ApiRequestError {
  return new ApiRequestError(
    `Cannot reach the API at ${env.apiBaseUrl}. Check that the backend is running and that this site is allowed by its CORS settings.`,
    0,
    "api_unreachable",
  );
}

let accessToken: string | null = null;

/** Every call names its tenant; the API routes it to that tenant's database. */
function baseHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "X-Client-Device": "web" };
  if (env.tenantDomain !== null) headers["X-Tenant-Domain"] = env.tenantDomain;
  return headers;
}
let onUnauthorized: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

async function parseError(response: Response): Promise<ApiRequestError> {
  try {
    const body = (await response.json()) as {
      error?: { message?: string; code?: string; details?: unknown };
    };
    if (body.error?.message) {
      return new ApiRequestError(
        body.error.message,
        response.status,
        body.error.code ?? null,
        body.error.details ?? null,
      );
    }
  } catch {
    // Non-JSON error body.
  }
  return new ApiRequestError(`Request failed (${response.status}).`, response.status);
}

async function request<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  return (await exchange<T>(method, path, body, auth)).data;
}

async function exchange<T>(
  method: string,
  path: string,
  body?: unknown,
  auth = true,
): Promise<{ data: T; headers: Headers }> {
  const headers = baseHeaders();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken !== null) headers.Authorization = `Bearer ${accessToken}`;
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw unreachable();
  }
  if (!response.ok) {
    const error = await parseError(response);
    if (auth && response.status === 401) onUnauthorized?.();
    throw error;
  }
  if (response.status === 204) return { data: undefined as T, headers: response.headers };
  return { data: (await response.json()) as T, headers: response.headers };
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>("GET", path);
}

export interface ApiPage<T> {
  rows: T[];
  /** Every record matching the filters, from the X-Total-Count header. */
  total: number;
}

/** GET one page of a list endpoint that takes `offset` + `limit` and reports X-Total-Count. */
export async function apiGetPage<T>(path: string, page: { offset: number; limit: number }): Promise<ApiPage<T>> {
  const separator = path.includes("?") ? "&" : "?";
  const { data, headers } = await exchange<T[]>(
    "GET",
    `${path}${separator}offset=${page.offset}&limit=${page.limit}`,
  );
  const total = Number(headers.get("X-Total-Count"));
  return { rows: data, total: Number.isFinite(total) && headers.has("X-Total-Count") ? total : data.length };
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>("POST", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>("PATCH", path, body);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>("PUT", path, body);
}

export function apiDelete(path: string): Promise<void> {
  return request<void>("DELETE", path);
}

/** Authenticated binary download, for PDFs. A body sends a POST (e.g. a list of labels to print). */
export async function apiBlob(path: string, body?: unknown): Promise<Blob> {
  const headers = baseHeaders();
  if (accessToken !== null) headers.Authorization = `Bearer ${accessToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      headers,
      method: body === undefined ? "GET" : "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw unreachable();
  }
  if (!response.ok) {
    const error = await parseError(response);
    if (response.status === 401) onUnauthorized?.();
    throw error;
  }
  return response.blob();
}

/** Authenticated multipart upload; the browser sets the boundary header itself. */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const headers = baseHeaders();
  if (accessToken !== null) headers.Authorization = `Bearer ${accessToken}`;
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, { method: "POST", headers, body: form });
  } catch {
    throw unreachable();
  }
  if (!response.ok) {
    const error = await parseError(response);
    if (response.status === 401) onUnauthorized?.();
    throw error;
  }
  return (await response.json()) as T;
}

export function apiPublicPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>("POST", path, body, false);
}

/** A call made as an activated device (the kitchen display), with its terminal token instead of a session. */
export async function apiTerminal<T>(method: "GET" | "POST", path: string, token: string, body?: unknown): Promise<T> {
  const headers = baseHeaders();
  headers["X-Terminal-Token"] = token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw unreachable();
  }
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

/** Unauthenticated call to the tenant-free signup API on the bare domain; never sends a tenant or session. */
export async function apiSignup<T>(
  method: "GET" | "POST",
  path: string,
  options: { body?: unknown; token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = { "X-Client-Device": "web" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers["X-Signup-Token"] = options.token;
  let response: Response;
  try {
    response = await fetch(`${env.signupApiBaseUrl}/api/v1/signup${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw unreachable();
  }
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}
