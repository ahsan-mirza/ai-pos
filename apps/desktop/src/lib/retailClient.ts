import type { GiftCardProduct, StoreCreditVoucher } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../config/env";
import { inTauri } from "./tauri";

/** A refused or failed retail request; status 0 means the API could not be reached. */
export class RetailRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }

  get offline(): boolean {
    return this.status === 0;
  }
}

/** A live request through the shell's retail passthrough (whitelisted paths), or fetch in the browser preview. */
export async function retailCall<T>(method: "GET" | "POST" | "PATCH" | "PUT", path: string, body?: unknown): Promise<T> {
  if (inTauri()) {
    const core = await import("@tauri-apps/api/core");
    try {
      return await core.invoke<T>("retail_request", { method, path, body: body ?? null });
    } catch (caught) {
      const raw = String(caught);
      try {
        const parsed = JSON.parse(raw) as { status: number; code: string; message: string };
        throw new RetailRequestError(parsed.status, parsed.code, parsed.message);
      } catch (inner) {
        if (inner instanceof RetailRequestError) throw inner;
        throw new RetailRequestError(0, "offline", raw);
      }
    }
  }
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...previewHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new RetailRequestError(0, "offline", "The server is unreachable.");
  }
  const value = (await response.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
  if (!response.ok) {
    throw new RetailRequestError(response.status, value?.error?.code ?? "rejected", value?.error?.message ?? "Request failed.");
  }
  return value as T;
}

const GIFT_PRODUCT_KEY = "ai-pos.gift-card-product";

export const giftCardsApi = {
  /** The gift card service product and rules; cached so a card can be sold offline once it was fetched. */
  async product(): Promise<GiftCardProduct> {
    try {
      const product = await retailCall<GiftCardProduct>("GET", "/api/v1/gift-cards/product");
      localStorage.setItem(GIFT_PRODUCT_KEY, JSON.stringify(product));
      return product;
    } catch (caught) {
      const cached = localStorage.getItem(GIFT_PRODUCT_KEY);
      if (cached !== null && caught instanceof RetailRequestError && caught.offline) {
        return JSON.parse(cached) as GiftCardProduct;
      }
      throw caught;
    }
  },
  lookup: (code: string) => retailCall<StoreCreditVoucher>("GET", `/api/v1/gift-cards/${encodeURIComponent(code)}`),
};

export interface RegisterStaff {
  id: string;
  full_name: string;
  role_name: string;
}

const STAFF_KEY = "ai-pos.register-staff";

export const staffApi = {
  /** Staff who can be named as "Served by"; the last list is kept so the picker works offline. */
  async list(storeId: string): Promise<RegisterStaff[]> {
    try {
      const staff = await retailCall<RegisterStaff[]>(
        "GET",
        `/api/v1/users/register-staff?store_id=${encodeURIComponent(storeId)}`,
      );
      localStorage.setItem(STAFF_KEY, JSON.stringify(staff));
      return staff;
    } catch (caught) {
      const cached = localStorage.getItem(STAFF_KEY);
      if (cached !== null) return JSON.parse(cached) as RegisterStaff[];
      throw caught;
    }
  },
};

const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/** A new gift card code, GC-XXXX-XXXX-XXXX, drawn on the register so a card can be sold offline. */
export function newGiftCardCode(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  const raw = Array.from(bytes, (byte) => CODE_ALPHABET[byte % CODE_ALPHABET.length]).join("");
  return `GC-${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8)}`;
}

/** Accepts what a cashier types or scans ("gc ab12 cd34 ef56") and returns GC-XXXX-XXXX-XXXX. */
export function normalizeGiftCard(raw: string): string {
  const compact = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const body = compact.startsWith("GC") ? compact.slice(2) : compact;
  if (body.length !== 12) return raw.trim().toUpperCase();
  return `GC-${body.slice(0, 4)}-${body.slice(4, 8)}-${body.slice(8)}`;
}
