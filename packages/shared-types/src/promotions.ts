/**
 * Promotion engine. Mirrors apps/api/app/services/promotion_engine.py; both are checked against
 * fixtures/promotion-cases.json, so a register and the API always agree on a cart's discounts.
 *
 * Rules: every unit of an eligible line is ranked by price (dearest first, then cart order). The promotion
 * that saves the most is applied first and claims the lines it used; the next best then works on what is left.
 * A line is discounted by at most one promotion.
 */

export type PromotionKind = "PERCENT_OFF" | "BUY_X_GET_Y" | "MIX_MATCH" | "BUNDLE" | "AMOUNT_OFF";

export interface PromotionRule {
  id: string;
  name: string;
  kind: PromotionKind;
  /** Empty product and category lists mean every product (bundles use their components instead). */
  product_ids: string[];
  category_ids: string[];
  /** PERCENT_OFF */
  percent_bps?: number | null;
  /** Optional ceiling on a percent discount, in cents. */
  max_discount_cents?: number | null;
  /** AMOUNT_OFF, in cents. Never more than the eligible subtotal. */
  amount_cents?: number | null;
  /** Issued per customer. Registers do not apply it until that customer's code is entered. */
  customer_issued?: boolean | null;
  segment?: string | null;
  repeat_count?: number | null;
  window_days?: number | null;
  quiet_days?: number | null;
  visit_count?: number | null;
  spend_cents?: number | null;
  notify?: boolean | null;
  /** BUY_X_GET_Y: buy buy_qty, the next get_qty cheapest get get_discount_bps off (10000 = free). */
  buy_qty?: number | null;
  get_qty?: number | null;
  get_discount_bps?: number | null;
  /** MIX_MATCH: any group_qty eligible units for group_price_cents. */
  group_qty?: number | null;
  group_price_cents?: number | null;
  /** BUNDLE: these components together for bundle_price_cents. */
  components?: { product_id: string; quantity: number }[] | null;
  bundle_price_cents?: number | null;
  /** The cart (gross, before discounts) must reach this. */
  min_spend_cents: number;
}

export interface PromotionLine {
  line_id: string;
  product_id: string;
  category_id: string | null;
  unit_price_cents: number;
  quantity: number;
}

export interface PromotionAward {
  line_id: string;
  promotion_id: string;
  discount_cents: number;
}

interface Unit {
  line_id: string;
  price: number;
  order: number;
}

interface Evaluation {
  saving: number;
  discounts: Map<string, number>;
  used: Set<string>;
}

function percentOf(amount: number, bps: number): number {
  return Math.floor((amount * bps + 5000) / 10000);
}

function eligible(rule: PromotionRule, line: PromotionLine): boolean {
  if (rule.kind === "BUNDLE") return (rule.components ?? []).some((part) => part.product_id === line.product_id);
  if (rule.product_ids.length === 0 && rule.category_ids.length === 0) return true;
  return rule.product_ids.includes(line.product_id) || (line.category_id !== null && rule.category_ids.includes(line.category_id));
}

function unitsOf(lines: { line: PromotionLine; order: number }[]): Unit[] {
  const units: Unit[] = [];
  for (const { line, order } of lines) {
    for (let index = 0; index < line.quantity; index += 1) units.push({ line_id: line.line_id, price: line.unit_price_cents, order });
  }
  return units.sort((left, right) => right.price - left.price || left.order - right.order);
}

function spread(group: Unit[], discount: number, discounts: Map<string, number>): void {
  let remaining = discount;
  for (const unit of group) {
    if (remaining <= 0) break;
    const take = Math.min(unit.price, remaining);
    discounts.set(unit.line_id, (discounts.get(unit.line_id) ?? 0) + take);
    remaining -= take;
  }
}

function capTotal(discounts: Map<string, number>, limit: number): void {
  let total = 0;
  for (const value of discounts.values()) total += value;
  if (limit <= 0 || total <= limit) return;
  const items = [...discounts.entries()];
  let running = 0;
  discounts.clear();
  items.forEach(([lineId, amount], index) => {
    const take = index === items.length - 1 ? Math.max(0, limit - running) : Math.floor((amount * limit) / total);
    if (take > 0) discounts.set(lineId, take);
    running += take;
  });
}

function evaluate(rule: PromotionRule, lines: { line: PromotionLine; order: number }[]): Evaluation {
  const discounts = new Map<string, number>();
  const used = new Set<string>();
  const pool = lines.filter((entry) => eligible(rule, entry.line));

  if (rule.kind === "PERCENT_OFF") {
    for (const { line } of pool) {
      const discount = percentOf(line.unit_price_cents * line.quantity, rule.percent_bps ?? 0);
      if (discount > 0) {
        discounts.set(line.line_id, discount);
        used.add(line.line_id);
      }
    }
    if (rule.max_discount_cents) capTotal(discounts, rule.max_discount_cents);
  } else if (rule.kind === "AMOUNT_OFF") {
    const units = unitsOf(pool);
    const gross = units.reduce((sum, unit) => sum + unit.price, 0);
    const discount = Math.min(rule.amount_cents ?? 0, gross);
    if (discount > 0) {
      for (const unit of units) used.add(unit.line_id);
      spread(units, discount, discounts);
    }
  } else if (rule.kind === "BUY_X_GET_Y") {
    const buy = rule.buy_qty ?? 0;
    const get = rule.get_qty ?? 0;
    const size = buy + get;
    const units = unitsOf(pool);
    if (buy > 0 && get > 0) {
      for (let start = 0; start + size <= units.length; start += size) {
        const group = units.slice(start, start + size);
        for (const unit of group) used.add(unit.line_id);
        for (const unit of group.slice(buy)) {
          const discount = percentOf(unit.price, rule.get_discount_bps ?? 10000);
          discounts.set(unit.line_id, (discounts.get(unit.line_id) ?? 0) + discount);
        }
      }
    }
  } else if (rule.kind === "MIX_MATCH") {
    const size = rule.group_qty ?? 0;
    const units = unitsOf(pool);
    if (size > 0) {
      for (let start = 0; start + size <= units.length; start += size) {
        const group = units.slice(start, start + size);
        const discount = group.reduce((sum, unit) => sum + unit.price, 0) - (rule.group_price_cents ?? 0);
        if (discount <= 0) continue;
        for (const unit of group) used.add(unit.line_id);
        spread(group, discount, discounts);
      }
    }
  } else if (rule.kind === "BUNDLE") {
    const parts = (rule.components ?? []).filter((part) => part.quantity > 0);
    const byProduct = new Map<string, Unit[]>();
    for (const part of parts) byProduct.set(part.product_id, unitsOf(pool.filter((entry) => entry.line.product_id === part.product_id)));
    const bundles = parts.length
      ? Math.min(...parts.map((part) => Math.floor((byProduct.get(part.product_id)?.length ?? 0) / part.quantity)))
      : 0;
    for (let bundle = 0; bundle < bundles; bundle += 1) {
      const group: Unit[] = [];
      for (const part of parts) group.push(...(byProduct.get(part.product_id) ?? []).slice(bundle * part.quantity, (bundle + 1) * part.quantity));
      const discount = group.reduce((sum, unit) => sum + unit.price, 0) - (rule.bundle_price_cents ?? 0);
      if (discount <= 0) break;
      group.sort((left, right) => right.price - left.price || left.order - right.order);
      for (const unit of group) used.add(unit.line_id);
      spread(group, discount, discounts);
    }
  }
  let saving = 0;
  for (const value of discounts.values()) saving += value;
  return { saving, discounts, used };
}

/** Discounts for a cart. Pass only rules already active for this store, time and coupon. */
export function applyPromotions(lines: PromotionLine[], rules: PromotionRule[]): PromotionAward[] {
  const cartGross = lines.reduce((sum, line) => sum + line.unit_price_cents * line.quantity, 0);
  let remaining = lines.map((line, order) => ({ line, order })).filter((entry) => entry.line.quantity > 0);
  let candidates = rules
    .filter((rule) => cartGross >= (rule.min_spend_cents ?? 0))
    .sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
  const awards: PromotionAward[] = [];
  for (;;) {
    let best: { rule: PromotionRule; result: Evaluation } | null = null;
    for (const rule of candidates) {
      const result = evaluate(rule, remaining);
      if (result.saving > 0 && (best === null || result.saving > best.result.saving)) best = { rule, result };
    }
    if (best === null) break;
    for (const lineId of best.result.used) {
      const discount = best.result.discounts.get(lineId) ?? 0;
      if (discount > 0) awards.push({ line_id: lineId, promotion_id: best.rule.id, discount_cents: discount });
    }
    const chosen = best;
    remaining = remaining.filter((entry) => !chosen.result.used.has(entry.line.line_id));
    candidates = candidates.filter((rule) => rule.id !== chosen.rule.id);
  }
  const order = new Map(lines.map((line, index) => [line.line_id, index]));
  return awards.sort((left, right) => (order.get(left.line_id) ?? 0) - (order.get(right.line_id) ?? 0));
}

export interface Promotion extends PromotionRule {
  description: string;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  store_ids: string[];
  coupon_code: string | null;
  max_uses: number | null;
  uses_count: number;
  discount_given_cents: number;
  /** Display names for product_ids and bundle components (admin list only). */
  product_names?: Record<string, string>;
}

/** Rules that apply right now at this store, given the coupon the cashier entered (if any). */
export function activeRules(promotions: Promotion[], at: Date, storeId: string, coupon: string | null): PromotionRule[] {
  const code = coupon?.trim().toUpperCase() || null;
  return promotions.filter(
    (promo) =>
      promo.is_active &&
      (promo.starts_at === null || new Date(promo.starts_at) <= at) &&
      (promo.ends_at === null || new Date(promo.ends_at) > at) &&
      (promo.store_ids.length === 0 || promo.store_ids.includes(storeId)) &&
      !promo.customer_issued &&
      (promo.coupon_code === null || promo.coupon_code === code) &&
      (promo.max_uses === null || promo.uses_count < promo.max_uses),
  );
}
