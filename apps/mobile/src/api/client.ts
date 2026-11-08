import Constants from "expo-constants";
import { Platform } from "react-native";
import { env } from "@/config/env";
import { ApiRequestError, parseErrorBody } from "./errors";

function androidEmulator(): boolean {
  if (Platform.OS !== "android") return false;
  const constants = Platform.constants as { Fingerprint?: string; Model?: string; Brand?: string };
  const hint = `${constants.Fingerprint ?? ""} ${constants.Model ?? ""} ${constants.Brand ?? ""}`.toLowerCase();
  return hint.includes("generic") || hint.includes("emulator") || hint.includes("sdk_gphone") || hint.includes("google_sdk");
}

/** A phone cannot call 127.0.0.1. In dev, use the Metro host, which is this computer. */
export function reachableApiBaseUrl(): string {
  const configured = env.apiBaseUrl;
  if (!__DEV__) return configured;
  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    return configured;
  }
  if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") return configured;
  const packagerHost = Constants.expoConfig?.hostUri?.split(":")[0];
  if (packagerHost && packagerHost !== "localhost" && packagerHost !== "127.0.0.1") {
    url.hostname = packagerHost;
  } else if (Platform.OS === "android" && androidEmulator()) {
    url.hostname = "10.0.2.2";
  } else {
    return configured;
  }
  return url.toString().replace(/\/$/, "");
}

export interface ApiPage<T> {
  rows: T[];
  total: number;
  payload: unknown;
  stale: boolean;
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

let accessToken: string | null = null;
let tenantDomain: string | null = null;
let onUnauthorized: (() => void) | null = null;
let renewer: (() => Promise<boolean>) | null = null;
let renewal: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setTenantDomain(domain: string | null): void {
  tenantDomain = domain;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function setSessionRenewer(next: (() => Promise<boolean>) | null): void {
  renewal = null;
  renewer = next;
}

function requestSessionRenewal(): Promise<boolean> {
  if (renewer === null) return Promise.resolve(false);
  if (renewal === null) {
    const flight = renewer().catch(() => false);
    renewal = flight.finally(() => {
      if (renewal === flight) renewal = null;
    });
  }
  return renewal;
}

function headers(body: unknown, extra?: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = { "X-Client-Device": "mobile", ...extra };
  if (tenantDomain) result["X-Tenant-Domain"] = tenantDomain;
  if (body !== undefined && !(body instanceof FormData)) result["Content-Type"] = "application/json";
  if (accessToken) result.Authorization = `Bearer ${accessToken}`;
  return result;
}

async function exchange(
  method: Method,
  path: string,
  body: unknown,
  auth: boolean,
  renew: boolean,
  signal?: AbortSignal,
): Promise<{ data: unknown; headers: Headers; status: number }> {
  let response: Response;
  try {
    response = await fetch(`${reachableApiBaseUrl()}${path}`, {
      method,
      headers: headers(body),
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
      signal,
    });
  } catch {
    throw new ApiRequestError(
      `Cannot reach the API at ${reachableApiBaseUrl()}.`,
      0,
      "api_unreachable",
    );
  }
  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    const error = parseErrorBody(response.status, parsed);
    if (auth && response.status === 401 && renew) {
      const renewed = await requestSessionRenewal();
      if (renewed) return exchange(method, path, body, auth, false, signal);
      onUnauthorized?.();
    } else if (auth && response.status === 401) {
      onUnauthorized?.();
    }
    throw error;
  }
  if (response.status === 204) return { data: undefined, headers: response.headers, status: 204 };
  const text = await response.text();
  const data = text === "" ? undefined : (JSON.parse(text) as unknown);
  return { data, headers: response.headers, status: response.status };
}

export function apiSend<T>(method: Method, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return exchange(method, path, body, true, true, signal).then((result) => result.data as T);
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiSend<T>("GET", path, undefined, signal);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiSend<T>("POST", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiSend<T>("PATCH", path, body);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiSend<T>("PUT", path, body);
}

export function apiDelete(path: string): Promise<void> {
  return apiSend<void>("DELETE", path);
}

export function apiPublicPost<T>(path: string, body: unknown): Promise<T> {
  return exchange("POST", path, body, false, false).then((result) => result.data as T);
}

/** Reissues the bearer token. Must not trigger another renewal. */
export function apiRefresh<T>(path: string): Promise<T> {
  return exchange("POST", path, {}, true, false).then((result) => result.data as T);
}

export async function apiGetRaw(path: string, signal?: AbortSignal): Promise<{ data: unknown; total: number | null }> {
  const result = await exchange("GET", path, undefined, true, true, signal);
  const header = result.headers.get("X-Total-Count");
  const total = header === null ? null : Number(header);
  return { data: result.data, total: total !== null && Number.isFinite(total) ? total : null };
}

export async function apiBlob(path: string): Promise<ArrayBuffer> {
  const result = await fetch(`${env.apiBaseUrl}${path}`, { headers: headers(undefined) });
  if (!result.ok) {
    throw new ApiRequestError(`Request failed (${result.status}).`, result.status);
  }
  return result.arrayBuffer();
}
