import {
  comboDelta,
  effectiveTier,
  formatWeight,
  enteredIncludesTax,
  lineTax,
  modifierDelta,
  weighedLineCents,
  type ComboChoice,
  type ModifierChoice,
  rateFor,
  resolveUnitPrice,
  resolveWithLists,
  unitFactor,
  type PriceSource,
  type PriceTier,
  type ProductUpsert,
  type SaleType,
  type TaxPolicy,
  type UnitType,
} from "@ai-pos/shared-types";
import type { RegisterCustomer } from "../../lib/tauri";
import { cachedPricing, entriesFor } from "./customerPricing";

/** The service product gift cards are sold as (app.services.gift_card_service.GIFT_CARD_SKU). */
export const GIFT_CARD_SKU = "SRV-GIFT-CARD";

export interface PriceOverride {
  approvedById: string;
  approverName: string;
  note: string;
  unitPriceCents: number;
}

/** quantity and prices are per piece; unitType is the pack the cashier is counting in. */
export interface CartLine {
  lineId: string;
  product: ProductUpsert;
  quantity: number;
  unitType: UnitType;
  serialValue: string | null;
  serialKind: "imei" | "serial" | null;
  /** Lines added together from the bulk IMEI modal share a group and render as one row. */
  groupId: string | null;
  listPriceCents: number;
  unitPriceCents: number;
  priceSource: PriceSource;
  tier: PriceTier;
  moqShortfall: number;
  override: PriceOverride | null;
  /** Set once a restricted product has been age-checked for this line. */
  ageCheck?: { confirmed: true; overrideById?: string; reason?: string } | null;
  /** Open-price lines: what was sold, typed by the cashier. */
  description?: string | null;
  /** Manager approval for a price below the margin floor. */
  floorOverride?: PriceOverride | null;
  /** Set by withPromotions: the promotion discounting this line and by how much (before VAT). */
  promotion?: { id: string; name: string; discountCents: number } | null;
  /** Menu modifiers; list and unit prices include their deltas. Lines with modifiers never merge. */
  modifiers?: ModifierChoice[];
  /** Preparation note for the kitchen. It does not change the price. */
  instruction?: string;
  /** Meal components; list and unit prices include their surcharges. Meal lines never merge. */
  components?: ComboChoice[];
  /** The restaurant tab line this cart line pays for, when settling an order. */
  orderItemId?: string;
  /** Cashier discount after any promotion: a percentage (basis points) or a fixed amount, with its reason. */
  discount?: ManualDiscount | null;
  /** A gift card sold on this line: the code the register generated. */
  giftCardCode?: string | null;
}

export interface ManualDiscount {
  mode: "percent" | "amount";
  /** Basis points for "percent", cents for "amount". */
  value: number;
  reason: string;
  reasonLabel: string;
  approvedById: string | null;
  approverName: string | null;
  note: string;
}

/** unit x quantity; weighed lines count grams at a per-kilogram price. */
export function lineGross(line: Pick<CartLine, "product" | "quantity" | "unitPriceCents">, unitCents = line.unitPriceCents): number {
  return line.product.sold_by_weight ? weighedLineCents(line.quantity, unitCents) : unitCents * line.quantity;
}

/** The cashier discount on a line in cents, after the promotion; never more than what is left of the line. */
export function manualDiscountCents(line: CartLine): number {
  const discount = line.discount ?? null;
  if (discount === null) return 0;
  const before = lineGross(line) - (line.promotion?.discountCents ?? 0);
  if (before <= 0) return 0;
  const cents = discount.mode === "percent" ? Math.floor((before * discount.value) / 10_000) : discount.value;
  return Math.max(0, Math.min(cents, before));
}

/** VAT and total for a line, after any promotion and cashier discount. */
export function lineCharge(line: CartLine, policy: TaxPolicy) {
  const rate = rateFor(policy, line.product.tax_category);
  const discount = (line.promotion?.discountCents ?? 0) + manualDiscountCents(line);
  const inclusive = enteredIncludesTax(line.product);
  return discount > 0 || line.product.sold_by_weight
    ? lineTax(lineGross(line) - discount, 1, rate, inclusive)
    : lineTax(line.unitPriceCents, line.quantity, rate, inclusive);
}

export interface CartState {
  mode: SaleType;
  customer: RegisterCustomer | null;
  lines: CartLine[];
  /** "Served by": the stylist credited with the sale when it is not the cashier. */
  associate?: SalesAssociate | null;
}

export interface SalesAssociate {
  id: string;
  name: string;
}

export type CartAction =
  | { type: "set_mode"; mode: SaleType }
  | { type: "set_associate"; associate: SalesAssociate | null }
  | { type: "attach_customer"; customer: RegisterCustomer | null }
  | {
      type: "add_product";
      product: ProductUpsert;
      unitType?: UnitType;
      quantity?: number;
      modifiers?: ModifierChoice[];
      components?: ComboChoice[];
      instruction?: string;
    }
  | { type: "set_customization"; lineId: string; modifiers: ModifierChoice[]; quantity: number; instruction?: string }
  | { type: "duplicate_line"; lineId: string }
  /** Settling a restaurant tab: the cart becomes the tab's unpaid lines, one cart line per tab line. */
  | {
      type: "load_order";
      lines: {
        product: ProductUpsert;
        quantity: number;
        modifiers: ModifierChoice[];
        components?: ComboChoice[];
        orderItemId: string;
        instruction?: string;
      }[];
    }
  /** One weighing (scale reading or label) of a sold-by-weight product: its own line, in grams. */
  | { type: "add_weighed"; product: ProductUpsert; grams: number }
  | {
      type: "add_serials";
      product: ProductUpsert;
      serials: { value: string; kind: "imei" | "serial" }[];
    }
  | { type: "set_packs"; lineId: string; packs: number }
  | { type: "set_unit"; lineId: string; unitType: UnitType }
  | { type: "remove_line"; lineId: string }
  | { type: "remove_group"; groupId: string }
  | { type: "override_price"; lineIds: string[]; override: PriceOverride }
  | { type: "clear_override"; lineIds: string[] }
  | { type: "add_open_price"; product: ProductUpsert; unitPriceCents: number; description: string; quantity: number }
  | { type: "approve_floor"; lineIds: string[]; override: PriceOverride }
  /** One discount per line (a cart discount is spread over its lines by the caller). */
  | { type: "set_discounts"; discounts: { lineId: string; discount: ManualDiscount }[] }
  | { type: "clear_discounts"; lineIds: string[] }
  | { type: "add_gift_card"; product: ProductUpsert; amountCents: number; code: string }
  | { type: "restore"; state: CartState }
  /** Re-resolve prices, e.g. once the attached customer's contract prices have been fetched. */
  | { type: "refresh_prices" }
  | {
      type: "confirm_age";
      lineIds: string[];
      check: { confirmed: true; overrideById?: string; reason?: string };
    }
  | { type: "clear" };

export interface CartResult {
  state: CartState;
  /** Why the action was refused; the state is unchanged when set. */
  error: string | null;
  notice: string | null;
}

export const emptyCart: CartState = { mode: "RETAIL", customer: null, lines: [] };

export function cartTier(state: Pick<CartState, "mode" | "customer">): PriceTier {
  const tier = effectiveTier(state.mode, state.customer?.price_tier ?? null);
  // A wholesale customer without a tier of their own takes their group's default (from the cached pricing).
  if (state.mode === "WHOLESALE" && tier === "RETAIL") return cachedPricing(state.customer?.id)?.tier ?? tier;
  return tier;
}

export function unitsFor(product: ProductUpsert): UnitType[] {
  if (product.is_serialized) return ["PIECE"];
  const units = product.sellable_units?.length ? product.sellable_units : (["PIECE"] as UnitType[]);
  return units.includes("PIECE") ? units : (["PIECE", ...units] as UnitType[]);
}

function piecesOf(lines: CartLine[], productId: string): number {
  return lines.reduce((sum, line) => (line.product.id === productId ? sum + line.quantity : sum), 0);
}

/** Re-resolves every line from the product's tiers and the per-product total pieces in the cart. */
export function reprice(state: CartState): CartState {
  const tier = cartTier(state);
  const pricing = cachedPricing(state.customer?.id);
  const lines = state.lines.map((line) => {
    if (line.product.is_open_price || line.giftCardCode) return line;
    const pieces = piecesOf(state.lines, line.product.id);
    const base = resolveUnitPrice(line.product.price_cents, line.product.prices, tier, pieces);
    const resolved = resolveWithLists(
      line.product.price_cents,
      line.product.prices,
      tier,
      pieces,
      entriesFor(line.product.id, line.product.price_lists, pricing),
      {
        customer_id: state.customer?.id ?? null,
        group_id: pricing?.group_id ?? state.customer?.group_id ?? null,
        store_id: line.product.store_id,
      },
    );
    const listed = resolved.price_cents + modifierDelta(line.modifiers) + comboDelta(line.components);
    return {
      ...line,
      listPriceCents: listed,
      unitPriceCents: line.override?.unitPriceCents ?? listed,
      priceSource: resolved.source,
      tier: resolved.tier,
      moqShortfall: base.moq_shortfall,
    };
  });
  return { ...state, lines };
}

function newLine(product: ProductUpsert, quantity: number, unitType: UnitType, extra: Partial<CartLine> = {}): CartLine {
  return {
    lineId: crypto.randomUUID(),
    product,
    quantity,
    unitType,
    serialValue: null,
    serialKind: null,
    groupId: null,
    listPriceCents: product.price_cents,
    unitPriceCents: product.price_cents,
    priceSource: "retail",
    tier: "RETAIL",
    moqShortfall: 0,
    override: null,
    ...extra,
  };
}

function stockError(lines: CartLine[], product: ProductUpsert, pieces: number): string | null {
  if (
    product.is_serialized ||
    product.is_service ||
    product.is_open_price ||
    product.has_recipe ||
    product.is_stock_tracked === false ||
    product.item_type === "MADE_TO_ORDER"
  )
    return null;
  const others = piecesOf(lines, product.id);
  if (others + pieces > product.stock_quantity) {
    const held = product.sold_by_weight ? formatWeight(product.stock_quantity) : String(product.stock_quantity);
    return `Only ${held} ${product.name} in stock.`;
  }
  return null;
}

function ok(state: CartState, notice: string | null = null): CartResult {
  return { state: reprice(state), error: null, notice };
}

function refuse(state: CartState, error: string): CartResult {
  return { state, error, notice: null };
}

export function applyCart(state: CartState, action: CartAction): CartResult {
  switch (action.type) {
    case "set_mode":
      return ok({ ...state, mode: action.mode });
    case "set_associate":
      return ok({ ...state, associate: action.associate });
    case "attach_customer": {
      const customer = action.customer;
      if (customer === null) return ok({ ...state, customer: null });
      const mode: SaleType = customer.customer_type === "WHOLESALE" ? "WHOLESALE" : state.mode;
      return ok({ ...state, customer, mode });
    }
    case "load_order": {
      if (action.lines.length === 0) return refuse(state, "Nothing left to pay on this order.");
      const lines = action.lines.map((line) =>
        newLine(line.product, line.quantity, "PIECE", {
          modifiers: line.modifiers,
          components: line.components?.length ? line.components : undefined,
          orderItemId: line.orderItemId,
          instruction: line.instruction?.trim().slice(0, 160) || undefined,
        }),
      );
      return ok({ ...emptyCart, mode: "RETAIL", lines }, `${lines.length} order line${lines.length === 1 ? "" : "s"} ready to pay.`);
    }
    case "add_weighed": {
      const { product, grams } = action;
      if (!product.sold_by_weight) return refuse(state, `${product.name} is not sold by weight.`);
      if (!Number.isInteger(grams) || grams <= 0) return refuse(state, "Put the item on the scale first.");
      if (grams > 1_000_000) return refuse(state, "That weight is too large for one line.");
      const error = stockError(state.lines, product, grams);
      if (error) return refuse(state, error);
      return ok({ ...state, lines: [...state.lines, newLine(product, grams, "PIECE")] }, `${formatWeight(grams)} ${product.name} added.`);
    }
    case "add_product": {
      const { product } = action;
      if (product.sku === GIFT_CARD_SKU) return refuse(state, "Use Sell gift card to load a card.");
      if (product.is_serialized) return refuse(state, "Serialized products are added with their IMEIs.");
      if (product.sold_by_weight) return refuse(state, `Weigh the ${product.name} or scan its scale label.`);
      const packs = action.quantity ?? 1;
      if (!Number.isInteger(packs) || packs < 1) return refuse(state, "Quantity must be at least 1.");
      const modifiers = action.modifiers?.length ? action.modifiers : undefined;
      const components = action.components?.length ? action.components : undefined;
      const instruction = action.instruction?.trim().slice(0, 160) || undefined;
      if (modifiers || components || instruction) {
        const error = stockError(state.lines, product, packs);
        if (error) return refuse(state, error);
        const line = newLine(product, packs, "PIECE", { modifiers, components, instruction });
        return ok({ ...state, lines: [...state.lines, line] }, `${product.name} added.`);
      }
      const existing = state.lines.find(
        (line) =>
          line.product.id === product.id &&
          line.serialValue === null &&
          !line.modifiers?.length &&
          !line.components?.length &&
          !line.instruction,
      );
      const unitType = action.unitType ?? existing?.unitType ?? "PIECE";
      const step = unitFactor(product, unitType);
      const adding = step * packs;
      const error = stockError(state.lines, product, adding);
      if (error) return refuse(state, error);
      const lines = existing
        ? state.lines.map((line) => (line.lineId === existing.lineId ? { ...line, quantity: line.quantity + adding } : line))
        : [...state.lines, newLine(product, adding, unitType)];
      return ok({ ...state, lines }, `${product.name} added.`);
    }
    case "add_serials": {
      const taken = new Set(state.lines.map((line) => line.serialValue).filter(Boolean));
      const fresh = action.serials.filter((serial) => !taken.has(serial.value));
      if (fresh.length === 0) return refuse(state, "Those IMEIs are already in this sale.");
      const groupId = fresh.length > 1 ? crypto.randomUUID() : null;
      const added = fresh.map((serial) =>
        newLine(action.product, 1, "PIECE", { serialValue: serial.value, serialKind: serial.kind, groupId }),
      );
      const skipped = action.serials.length - fresh.length;
      const notice =
        fresh.length === 1
          ? `${action.product.name} added.`
          : `${fresh.length} × ${action.product.name} added${skipped ? ` (${skipped} already in the sale)` : ""}.`;
      return ok({ ...state, lines: [...state.lines, ...added] }, notice);
    }
    case "set_packs": {
      const line = state.lines.find((item) => item.lineId === action.lineId);
      if (!line || line.serialValue !== null) return refuse(state, "That line cannot change quantity.");
      if (line.product.sold_by_weight) return refuse(state, "Weigh the item again to change the amount.");
      if (!Number.isInteger(action.packs) || action.packs < 1) return refuse(state, "Quantity must be at least 1.");
      const pieces = action.packs * unitFactor(line.product, line.unitType);
      const others = state.lines.filter((item) => item.lineId !== line.lineId);
      const error = stockError(others, line.product, pieces);
      if (error) return refuse(state, error);
      return ok({ ...state, lines: state.lines.map((item) => (item.lineId === line.lineId ? { ...item, quantity: pieces } : item)) });
    }
    case "set_unit": {
      const line = state.lines.find((item) => item.lineId === action.lineId);
      if (!line || line.serialValue !== null) return refuse(state, "That line is sold by the piece.");
      if (!unitsFor(line.product).includes(action.unitType)) {
        return refuse(state, `${line.product.name} is not sold that way.`);
      }
      const factor = unitFactor(line.product, action.unitType);
      const pieces = Math.max(1, Math.ceil(line.quantity / factor)) * factor;
      const others = state.lines.filter((item) => item.lineId !== line.lineId);
      const error = stockError(others, line.product, pieces);
      if (error) return refuse(state, error);
      return ok({
        ...state,
        lines: state.lines.map((item) =>
          item.lineId === line.lineId ? { ...item, unitType: action.unitType, quantity: pieces } : item,
        ),
      });
    }
    case "set_customization": {
      const line = state.lines.find((item) => item.lineId === action.lineId);
      if (!line) return refuse(state, "That item is no longer in the order.");
      if (line.orderItemId) return refuse(state, "This item is already with the kitchen.");
      if (!Number.isInteger(action.quantity) || action.quantity < 1) return refuse(state, "Quantity must be at least 1.");
      const others = state.lines.filter((item) => item.lineId !== line.lineId);
      const error = stockError(others, line.product, action.quantity);
      if (error) return refuse(state, error);
      const instruction = action.instruction?.trim().slice(0, 160) || undefined;
      const modifiers = action.modifiers.length ? action.modifiers : undefined;
      const lines = state.lines.map((item) =>
        item.lineId === line.lineId ? { ...item, quantity: action.quantity, modifiers, instruction } : item,
      );
      return ok({ ...state, lines }, `${line.product.name} updated.`);
    }
    case "duplicate_line": {
      const line = state.lines.find((item) => item.lineId === action.lineId);
      if (!line) return refuse(state, "That item is no longer in the order.");
      if (line.serialValue || line.orderItemId) return refuse(state, "This item cannot be copied.");
      const error = stockError(state.lines, line.product, line.quantity);
      if (error) return refuse(state, error);
      const copy = { ...line, lineId: crypto.randomUUID(), orderItemId: undefined };
      return ok({ ...state, lines: [...state.lines, copy] }, `${line.product.name} copied.`);
    }
    case "remove_line":
      return ok({ ...state, lines: state.lines.filter((line) => line.lineId !== action.lineId) });
    case "remove_group":
      return ok({ ...state, lines: state.lines.filter((line) => line.groupId !== action.groupId) });
    case "override_price": {
      const ids = new Set(action.lineIds);
      return ok(
        { ...state, lines: state.lines.map((line) => (ids.has(line.lineId) ? { ...line, override: action.override } : line)) },
        `Price changed to ${(action.override.unitPriceCents / 100).toFixed(2)} with ${action.override.approverName}'s approval.`,
      );
    }
    case "clear_override": {
      const ids = new Set(action.lineIds);
      return ok({
        ...state,
        lines: state.lines.map((line) => (ids.has(line.lineId) ? { ...line, override: null, floorOverride: null } : line)),
      });
    }
    case "add_open_price": {
      const description = action.description.trim();
      if (!action.product.is_open_price) return refuse(state, `${action.product.name} has a fixed price.`);
      if (!Number.isInteger(action.quantity) || action.quantity < 1) return refuse(state, "Quantity must be at least 1.");
      if (!Number.isInteger(action.unitPriceCents) || action.unitPriceCents <= 0) return refuse(state, "Enter the price.");
      const line = newLine(action.product, action.quantity, "PIECE", {
        ...(description ? { description } : {}),
        listPriceCents: action.unitPriceCents,
        unitPriceCents: action.unitPriceCents,
      });
      const label = description || action.product.name;
      return ok({ ...state, lines: [...state.lines, line] }, `${label} added.`);
    }
    case "approve_floor": {
      const ids = new Set(action.lineIds);
      return ok(
        { ...state, lines: state.lines.map((line) => (ids.has(line.lineId) ? { ...line, floorOverride: action.override } : line)) },
        `Below-floor price approved by ${action.override.approverName}.`,
      );
    }
    case "set_discounts": {
      const byLine = new Map(action.discounts.map((entry) => [entry.lineId, entry.discount]));
      const blocked = state.lines.find(
        (line) => byLine.has(line.lineId) && (line.giftCardCode || line.product.sold_by_weight || line.orderItemId),
      );
      if (blocked) return refuse(state, `${blocked.product.name} cannot be discounted at the till.`);
      return ok(
        { ...state, lines: state.lines.map((line) => (byLine.has(line.lineId) ? { ...line, discount: byLine.get(line.lineId) } : line)) },
        "Discount applied.",
      );
    }
    case "clear_discounts": {
      const ids = new Set(action.lineIds);
      return ok({ ...state, lines: state.lines.map((line) => (ids.has(line.lineId) ? { ...line, discount: null } : line)) });
    }
    case "add_gift_card": {
      if (!Number.isInteger(action.amountCents) || action.amountCents <= 0) return refuse(state, "Enter the card amount.");
      const line = newLine(action.product, 1, "PIECE", {
        giftCardCode: action.code,
        listPriceCents: action.amountCents,
        unitPriceCents: action.amountCents,
        description: `Gift card ${action.code}`,
      });
      return ok({ ...state, lines: [...state.lines, line] }, `Gift card ${action.code} added.`);
    }
    case "restore":
      return ok({ ...action.state });
    case "refresh_prices":
      return ok(state);
    case "confirm_age": {
      const ids = new Set(action.lineIds);
      return ok({
        ...state,
        lines: state.lines.map((line) => (ids.has(line.lineId) ? { ...line, ageCheck: action.check } : line)),
      });
    }
    case "clear":
      return ok({ ...emptyCart });
  }
}

export interface CartTotals {
  /** Net of VAT. */
  subtotal: number;
  tax: number;
  /** Tax extracted from prices that already include it. */
  inclusiveTax: number;
  /** Tax added on top of tax-exclusive prices. */
  exclusiveTax: number;
  total: number;
  /** What the same cart would cost at plain retail (in catalog prices), so wholesale savings can be shown. */
  retailSubtotal: number;
  /** The same cart in charged prices, comparable with retailSubtotal. */
  chargedSubtotal: number;
  pieces: number;
}

export function cartTotals(lines: CartLine[], policy: TaxPolicy): CartTotals {
  let total = 0;
  let tax = 0;
  let inclusiveTax = 0;
  let exclusiveTax = 0;
  let retailSubtotal = 0;
  let chargedSubtotal = 0;
  let pieces = 0;
  for (const line of lines) {
    const result = lineCharge(line, policy);
    total += result.line_total_cents;
    tax += result.tax_cents;
    if (enteredIncludesTax(line.product)) inclusiveTax += result.tax_cents;
    else exclusiveTax += result.tax_cents;
    chargedSubtotal += lineGross(line) - (line.promotion?.discountCents ?? 0) - manualDiscountCents(line);
    retailSubtotal += lineGross(
      line,
      line.product.is_open_price || line.giftCardCode ? line.unitPriceCents : line.product.price_cents,
    );
    pieces += line.product.sold_by_weight ? 1 : line.quantity;
  }
  return { subtotal: total - tax, tax, inclusiveTax, exclusiveTax, total, retailSubtotal, chargedSubtotal, pieces };
}

/** Cart rows as displayed: bulk IMEI groups collapse into one row. */
export interface CartRow {
  key: string;
  lines: CartLine[];
  product: ProductUpsert;
  groupId: string | null;
}

export function cartRows(lines: CartLine[]): CartRow[] {
  const rows: CartRow[] = [];
  const groups = new Map<string, CartRow>();
  for (const line of lines) {
    if (line.groupId === null) {
      rows.push({ key: line.lineId, lines: [line], product: line.product, groupId: null });
      continue;
    }
    const existing = groups.get(line.groupId);
    if (existing) {
      existing.lines.push(line);
      continue;
    }
    const row: CartRow = { key: line.groupId, lines: [line], product: line.product, groupId: line.groupId };
    groups.set(line.groupId, row);
    rows.push(row);
  }
  return rows;
}
