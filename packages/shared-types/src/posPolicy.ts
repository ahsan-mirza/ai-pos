/** Till rules for the whole business. Mirrors apps/api/app/schemas/pos_policy.py. */
import type { ReturnConditionRule } from "./returns.js";

export interface PolicyChoice {
  key: string;
  label: string;
}

export interface DiscountPolicy {
  reasons: PolicyChoice[];
  /** Largest discount (basis points of a line) a cashier with pos:discount gives alone when their role sets none. */
  default_limit_bps: number;
}

export interface GiftCardPolicy {
  /** Months a card stays valid; null never expires. */
  expiry_months: number | null;
  min_cents: number;
  max_cents: number;
}

export interface ReturnsPolicySettings {
  preset: "electronics" | "fashion" | "custom";
  window_days: number;
  exchange_window_days: number;
  conditions: ReturnConditionRule[];
  reasons: PolicyChoice[];
}

export interface PosPolicy {
  discounts: DiscountPolicy;
  gift_cards: GiftCardPolicy;
  returns: ReturnsPolicySettings;
}

const BASE_REASONS: PolicyChoice[] = [
  { key: "defective", label: "Defective" },
  { key: "changed_mind", label: "Changed mind" },
  { key: "wrong_item", label: "Wrong item" },
  { key: "damaged_in_transit", label: "Damaged in transit" },
  { key: "not_as_described", label: "Not as described" },
  { key: "other", label: "Other" },
];

export const RETURNS_PRESETS: Record<"electronics" | "fashion", ReturnsPolicySettings> = {
  electronics: {
    preset: "electronics",
    window_days: 30,
    exchange_window_days: 0,
    conditions: [
      { key: "unopened_resealable", label: "Unopened / resealable", restock: true, fee_bps: 0, serial_status: "in_stock" },
      { key: "open_box", label: "Open box", restock: false, fee_bps: 1500, serial_status: "quarantine" },
      { key: "defective_doa", label: "Defective / DOA", restock: false, fee_bps: 0, serial_status: "repair" },
    ],
    reasons: BASE_REASONS,
  },
  fashion: {
    preset: "fashion",
    window_days: 14,
    exchange_window_days: 16,
    conditions: [
      { key: "tags_attached", label: "Tags attached, unworn", restock: true, fee_bps: 0, serial_status: "in_stock" },
      { key: "worn", label: "Worn or washed", restock: false, fee_bps: 0, serial_status: "quarantine" },
      { key: "damaged", label: "Damaged or faulty", restock: false, fee_bps: 0, serial_status: "repair" },
    ],
    reasons: [
      { key: "size_fit", label: "Size or fit" },
      { key: "style", label: "Style or colour" },
      { key: "quality", label: "Quality" },
      ...BASE_REASONS,
    ],
  },
};

export const DEFAULT_POS_POLICY: PosPolicy = {
  discounts: {
    reasons: [
      { key: "staff", label: "Staff discount" },
      { key: "damaged", label: "Damaged or soiled item" },
      { key: "vip", label: "VIP customer" },
      { key: "price_match", label: "Price match" },
      { key: "other", label: "Other" },
    ],
    default_limit_bps: 1000,
  },
  gift_cards: { expiry_months: 36, min_cents: 1000, max_cents: 500_000 },
  returns: RETURNS_PRESETS.electronics,
};

/** Policy with defaults filled in, section by section, as the API resolves it. */
export function resolvePosPolicy(raw: Partial<PosPolicy> | null | undefined): PosPolicy {
  return {
    discounts: raw?.discounts ?? DEFAULT_POS_POLICY.discounts,
    gift_cards: raw?.gift_cards ?? DEFAULT_POS_POLICY.gift_cards,
    returns: raw?.returns ?? DEFAULT_POS_POLICY.returns,
  };
}

/** Discount as basis points of the line before it, rounded up. Mirrors discount_service.share_bps. */
export function discountShareBps(discountCents: number, beforeCents: number): number {
  if (beforeCents <= 0) return 10_000;
  return Math.ceil((discountCents * 10_000) / beforeCents);
}

/** Largest discount a user gives alone. Mirrors discount_service.limit_bps. */
export function discountLimitBps(
  user: { permissions: readonly string[]; max_discount_bps?: number | null } | null | undefined,
  policy: PosPolicy,
): number {
  if (!user || !user.permissions.includes("pos:discount")) return 0;
  return user.max_discount_bps ?? policy.discounts.default_limit_bps;
}

/** A gift card code as registers generate it: GC-XXXX-XXXX-XXXX. */
export const GIFT_CARD_CODE = /^GC-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/;
