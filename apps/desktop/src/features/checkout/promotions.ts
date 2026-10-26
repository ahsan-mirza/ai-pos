import { Capability, activeRules, applyPromotions, type Promotion, type PromotionKind } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { hasCapability } from "../../lib/capabilities";
import { inTauri } from "../../lib/tauri";
import type { CartLine, CartState } from "./cart";

const CACHE_KEY = "ai-pos.promotions";

function cached(): Promotion[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as Promotion[]) : [];
  } catch {
    return [];
  }
}

/** Live promotions when online; the last list fetched when offline, so offline sales still get them. */
export async function loadPromotions(): Promise<Promotion[]> {
  if (!hasCapability(Capability.Promotions)) {
    localStorage.removeItem(CACHE_KEY);
    return [];
  }
  try {
    let fresh: Promotion[] | null = null;
    if (inTauri()) {
      const core = await import("@tauri-apps/api/core");
      fresh = await core.invoke<Promotion[] | null>("active_promotions");
    } else {
      const response = await fetch(`${env.apiBaseUrl}/api/v1/promotions/active?store_id=${env.storeId}`, { headers: previewHeaders() });
      fresh = response.ok ? ((await response.json()) as Promotion[]) : null;
    }
    if (Array.isArray(fresh)) {
      localStorage.setItem(CACHE_KEY, JSON.stringify(fresh));
      return fresh;
    }
  } catch {
    // Offline: fall through to the cache.
  }
  return cached();
}

export interface IssuedVoucher {
  code: string;
  status: string;
  promotion_id: string;
  promotion_name: string;
  kind: PromotionKind;
  amount_cents: number | null;
  percent_bps: number | null;
  min_spend_cents: number;
  product_ids: string[];
  category_ids: string[];
  expires_at: string | null;
}

function enteredVoucher(vouchers: IssuedVoucher[], coupon: string | null): Promotion | null {
  const code = coupon?.trim().toUpperCase();
  const voucher = code ? vouchers.find((row) => row.status === "issued" && row.code === code) : undefined;
  if (!voucher) return null;
  return {
    id: voucher.promotion_id,
    name: voucher.promotion_name,
    description: "",
    kind: voucher.kind,
    product_ids: voucher.product_ids,
    category_ids: voucher.category_ids,
    percent_bps: voucher.percent_bps,
    amount_cents: voucher.amount_cents,
    min_spend_cents: voucher.min_spend_cents,
    customer_issued: false,
    coupon_code: voucher.code,
    is_active: true,
    starts_at: null,
    ends_at: voucher.expires_at,
    store_ids: [],
    max_uses: null,
    uses_count: 0,
    discount_given_cents: 0,
  };
}

/** Retail carts get the best promotions. A typed customer voucher also applies on a wholesale cart. */
export function withPromotions(
  state: Pick<CartState, "mode" | "lines">,
  promotions: Promotion[],
  coupon: string | null,
  vouchers: IssuedVoucher[] = [],
  at: Date = new Date(),
): CartLine[] {
  const cleared = state.lines.map((line) => (line.promotion ? { ...line, promotion: null } : line));
  const personal = enteredVoucher(vouchers, coupon);
  const pool = state.mode === "RETAIL" ? [...promotions, ...(personal ? [personal] : [])] : personal ? [personal] : [];
  if (pool.length === 0) return cleared;
  const rules = activeRules(pool, at, env.storeId, coupon);
  if (rules.length === 0) return cleared;
  const eligible = cleared.filter(
    (line) => !line.product.is_open_price && !line.product.is_service && !line.product.sold_by_weight && line.override === null,
  );
  const awards = applyPromotions(
    eligible.map((line) => ({
      line_id: line.lineId,
      product_id: line.product.id,
      category_id: line.product.category_id ?? null,
      unit_price_cents: line.unitPriceCents,
      quantity: line.quantity,
    })),
    rules,
  );
  const names = new Map(pool.map((promo) => [promo.id, promo.name]));
  const byLine = new Map(awards.map((award) => [award.line_id, award]));
  return cleared.map((line) => {
    const award = byLine.get(line.lineId);
    return award
      ? { ...line, promotion: { id: award.promotion_id, name: names.get(award.promotion_id) ?? "Promotion", discountCents: award.discount_cents } }
      : line;
  });
}

/** Whether a typed coupon matches one of the loaded coupon promotions. */
export function couponKnown(promotions: Promotion[], coupon: string): Promotion | null {
  const code = coupon.trim().toUpperCase();
  return promotions.find((promo) => promo.coupon_code !== null && promo.coupon_code === code) ?? null;
}
