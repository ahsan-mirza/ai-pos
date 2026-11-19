import type { TokenResponse } from "./auth.js";

/** Public demo entry. A business code names which shared demo to open. It does not select a tenant and it is not a session. */

export const PORTAL_SESSION_STORAGE_KEY = "ai-pos.portal-session";
export const STORE_CODE_STORAGE_KEY = "ai-pos.store-code";
export const BUSINESS_SETTINGS_STORAGE_KEY = "ai-pos.business-settings";

export interface DemoBusiness {
  code: "restaurant" | "supermarket" | "electronics" | "fashion" | "pharmacy";
  slug: string;
  title: string;
  short: string;
  cta: string;
  image: string;
  features: readonly string[];
}

export const DEMO_BUSINESSES: readonly DemoBusiness[] = [
  {
    code: "restaurant",
    slug: "demo-restaurant",
    title: "Restaurant & Café",
    short: "Restaurant",
    cta: "Explore Restaurant Demo",
    image: "/images/home-2/restaurant.png",
    features: ["Dine-in and takeaway.", "Restaurant tables.", "Kitchen display.", "Modifiers and recipes.", "Delivery operations."],
  },
  {
    code: "supermarket",
    slug: "demo-supermarket",
    title: "Supermarket & Grocery",
    short: "Supermarket",
    cta: "Explore Supermarket Demo",
    image: "/images/home-2/supermarket.png",
    features: ["Barcode billing.", "PLU and weighed items.", "Inventory management.", "Batch and FEFO tracking.", "Loyalty and promotions."],
  },
  {
    code: "electronics",
    slug: "demo-electronics",
    title: "Electronics & Wholesale",
    short: "Electronics",
    cta: "Explore Electronics Demo",
    image: "/images/home-2/electronics.png",
    features: ["Wholesale pricing.", "Serial number tracking.", "Warranty management.", "Customer credit ledger.", "Inventory control."],
  },
  {
    code: "fashion",
    slug: "demo-fashion",
    title: "Fashion & Retail",
    short: "Fashion",
    cta: "Explore Fashion Demo",
    image: "/images/home-2/fashion.png",
    features: ["Size and color variants.", "Product management.", "Inventory tracking.", "Customer loyalty.", "Promotions."],
  },
  {
    code: "pharmacy",
    slug: "demo-pharmacy",
    title: "Pharmacy",
    short: "Pharmacy",
    cta: "Explore Pharmacy Demo",
    image: "/images/home-2/checkout-suite.png",
    features: ["Medicine catalogue.", "Dispensing class.", "Manufacturer lots.", "Expiry dates.", "Loyalty and promotions."],
  },
];

export type DemoBusinessCode = DemoBusiness["code"];

export interface DemoMarker {
  businessCode: DemoBusinessCode;
  businessName: string;
}

export interface DemoExchangeResult {
  access_token: string;
  expires_in: number;
  business_code: DemoBusinessCode;
  business_name: string;
  demo: true;
}

export interface StoredDemoSession {
  token: string;
  expiresAt: number;
  demo: DemoMarker;
}

export type DemoOpenPlan =
  | { kind: "exchange"; href: string; body: { business_code: DemoBusinessCode } }
  | { kind: "navigate"; href: string };

export class DemoOpenError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("demo_open_failed");
    this.status = status;
  }
}

export function isDemoBusinessCode(value: string): value is DemoBusinessCode {
  return DEMO_BUSINESSES.some((business) => business.code === value);
}

export function demoBusiness(code: string): DemoBusiness | null {
  return DEMO_BUSINESSES.find((business) => business.code === code) ?? null;
}

export function demoCodeFromPath(pathname: string): DemoBusinessCode | null {
  const match = /^\/demo\/([a-z]+)\/?$/.exec(pathname);
  if (match === null) return null;
  return isDemoBusinessCode(match[1] ?? "") ? (match[1] as DemoBusinessCode) : null;
}

/** The exchange body carries the public code only. */
export function demoExchangeBody(code: DemoBusinessCode): { business_code: DemoBusinessCode } {
  return { business_code: code };
}

export function friendlyDemoError(status: number, businessShort: string): string {
  if (status === 404) return `${businessShort} demo is temporarily unavailable. Please try again shortly.`;
  if (status === 429) return "Too many attempts. Please wait a moment before trying again.";
  if (status === 0) return "Unable to connect. Please check your internet connection.";
  return "The demo could not be opened. Please try again shortly.";
}

export function claimDemoClick(pending: string | null, code: string): string | null {
  if (pending !== null) return null;
  return code;
}

function decodeBase64Url(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(segment.length / 4) * 4, "=");
  const decode = (globalThis as { atob?: (value: string) => string }).atob;
  if (decode === undefined) return "";
  return decode(padded);
}

interface Address {
  origin: string;
  hostname: string;
  pathname: string;
  search: string;
  hash: string;
  toString: () => string;
}

function address(value: string, base?: string): Address {
  const Url = (globalThis as { URL?: new (input: string, base?: string) => Address }).URL;
  if (Url === undefined) throw new Error("URL is unavailable");
  return new Url(value, base);
}

/** Reads the unsigned `demo` claim. The server still decides whether the token is accepted. */
export function tokenSaysDemo(token: string): boolean {
  const segment = token.split(".")[1];
  if (segment === undefined || segment === "") return false;
  try {
    const json = JSON.parse(decodeBase64Url(segment)) as { demo?: unknown };
    return json.demo === true;
  } catch {
    return false;
  }
}

export function readDemoExchange(body: unknown, requested: DemoBusinessCode): DemoExchangeResult | null {
  if (body === null || typeof body !== "object") return null;
  const row = body as Record<string, unknown>;
  if (row.demo !== true || row.token_type !== "bearer") return null;
  if (typeof row.access_token !== "string" || row.access_token === "") return null;
  if (typeof row.expires_in !== "number" || !Number.isFinite(row.expires_in)) return null;
  if (row.business_code !== requested) return null;
  if (typeof row.business_name !== "string" || row.business_name.trim() === "") return null;
  return {
    access_token: row.access_token,
    expires_in: row.expires_in,
    business_code: requested,
    business_name: row.business_name,
    demo: true,
  };
}

export function storedDemoSession(result: DemoExchangeResult, now: number): StoredDemoSession {
  return {
    token: result.access_token,
    expiresAt: now + result.expires_in * 1000,
    demo: { businessCode: result.business_code, businessName: result.business_name },
  };
}

export function demoMarkerFrom(
  response: { access_token: string; demo?: boolean; business_code?: string; business_name?: string },
  previous: DemoMarker | null,
): DemoMarker | null {
  if (!tokenSaysDemo(response.access_token)) return null;
  if (response.demo === true && response.business_code !== undefined && isDemoBusinessCode(response.business_code)) {
    const name = response.business_name?.trim() ?? "";
    if (name !== "") return { businessCode: response.business_code, businessName: name };
  }
  return previous;
}

/** Same-origin marketing can store the portal session. A different origin must let the portal exchange. */
export function planDemoOpen(siteOrigin: string, portalLoginUrl: string, code: DemoBusinessCode): DemoOpenPlan {
  const portal = address(portalLoginUrl);
  const home = address(portal.origin);
  const marketing = portal.hostname === "axizpos.com" || portal.hostname === "www.axizpos.com";
  home.pathname = marketing ? "/dashboard" : "/";
  home.search = "";
  home.hash = "";
  if (portal.origin === siteOrigin) return { kind: "exchange", href: home.toString(), body: demoExchangeBody(code) };
  return { kind: "navigate", href: address(`/demo/${code}`, portal.origin).toString() };
}

export function portalDemoEntry(portalLoginUrl: string, code: DemoBusinessCode): string {
  const portal = address(portalLoginUrl);
  return address(`/demo/${code}`, portal.origin).toString();
}

export function visibleDemo(session: { token: string; demo?: DemoMarker | null } | null): DemoMarker | null {
  if (session?.demo == null) return null;
  if (!tokenSaysDemo(session.token)) return null;
  return session.demo;
}

interface DemoResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export async function exchangeDemo(
  apiBase: string,
  code: DemoBusinessCode,
  fetchImpl: (input: string, init: { method: string; headers: Record<string, string>; body: string }) => Promise<DemoResponse>,
): Promise<TokenResponse> {
  let response: DemoResponse;
  try {
    response = await fetchImpl(`${apiBase}/api/v1/demo-access/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(demoExchangeBody(code)),
    });
  } catch {
    throw new DemoOpenError(0);
  }
  if (!response.ok) throw new DemoOpenError(response.status);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new DemoOpenError(500);
  }
  const parsed = readDemoExchange(body, code);
  const issued = body as Partial<TokenResponse>;
  if (parsed === null || issued.user == null || (issued.scope !== "portal" && issued.scope !== "pos")) throw new DemoOpenError(500);
  return { ...issued, ...parsed, user: issued.user, scope: issued.scope, token_type: "bearer" };
}
