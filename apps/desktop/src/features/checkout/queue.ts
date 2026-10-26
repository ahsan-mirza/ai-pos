import {
  SyncEntityType,
  SyncOperation,
  productSyncPayload,
  type PaymentMethod,
  type QuoteUpsert,
  type SaleItemUpsert,
  type SaleTender,
  type SaleUpsert,
  type SyncEvent,
  type TaxPolicy,
} from "@ai-pos/shared-types";
import { lineCharge, manualDiscountCents, type CartLine, type CartState } from "./cart";
import { activeStore, businessTax, customerTax } from "./currency";

export interface CreditApproval {
  approvedById: string;
  note: string;
}

export interface ChargeRequest {
  cart: CartState;
  paymentMethod: PaymentMethod;
  tenders: SaleTender[];
  cashierId: string;
  creditApproval: CreditApproval | null;
  /** This register's offline invoice number; null lets the API number the sale. */
  invoiceNumber?: string | null;
  shiftId?: string | null;
  /** Points spent through the loyalty tender. */
  loyaltyPoints?: number | null;
  /** The coupon the cashier entered, for coupon promotions. */
  couponCode?: string | null;
  /** Settling a restaurant tab: which order and lines, the service charge inside the total, and the tip on top. */
  restaurant?: {
    orderId: string | null;
    orderItemIds: string[];
    serviceChargeCents: number;
    serviceChargeTaxCents: number;
    tipCents: number;
  } | null;
}

function manualDiscountFields(line: CartLine): Partial<SaleItemUpsert> {
  const cents = manualDiscountCents(line);
  if (cents <= 0 || !line.discount) return {};
  return {
    manual_discount_cents: cents,
    discount_reason: line.discount.reason,
    discount_override: line.discount.approvedById
      ? { approved_by_id: line.discount.approvedById, note: line.discount.note }
      : null,
  };
}

export function saleItems(lines: CartLine[], policy: TaxPolicy = businessTax()): SaleItemUpsert[] {
  return lines.map((line) => {
    const tax = lineCharge(line, policy);
    const discount = line.promotion?.discountCents ?? 0;
    return {
      id: crypto.randomUUID(),
      product_id: line.product.id,
      quantity: line.quantity,
      unit_price_cents: line.unitPriceCents,
      tax_cents: tax.tax_cents,
      line_total_cents: tax.line_total_cents,
      serial_value: line.serialValue,
      serial_kind: line.serialKind,
      unit_type: line.unitType,
      list_price_cents: line.listPriceCents,
      price_override:
        line.override !== null ? { approved_by_id: line.override.approvedById, note: line.override.note } : null,
      description: line.description ?? null,
      below_floor_override:
        line.floorOverride != null
          ? { approved_by_id: line.floorOverride.approvedById, note: line.floorOverride.note }
          : null,
      discount_cents: discount,
      promotion_id: discount > 0 ? (line.promotion?.id ?? null) : null,
      ...manualDiscountFields(line),
      ...(line.giftCardCode ? { gift_card_code: line.giftCardCode } : {}),
      ...(line.ageCheck
        ? {
            age_check: {
              confirmed: true,
              override_by_id: line.ageCheck.overrideById ?? null,
              reason: line.ageCheck.reason ?? null,
            },
          }
        : {}),
      ...(line.modifiers?.length ? { modifiers: line.modifiers } : {}),
      ...(line.components?.length ? { components: line.components } : {}),
    };
  });
}

/** subtotal is net of VAT; total is what the customer pays. */
export function totals(items: SaleItemUpsert[]): { subtotal: number; tax: number; total: number } {
  const total = items.reduce((sum, item) => sum + item.line_total_cents, 0);
  const tax = items.reduce((sum, item) => sum + item.tax_cents, 0);
  return { subtotal: total - tax, tax, total };
}

export function buildChargeEvents(request: ChargeRequest): SyncEvent[] {
  const { cart } = request;
  const occurredAt = new Date().toISOString();
  const store = activeStore();
  const events: SyncEvent[] = [
    {
      idempotency_key: crypto.randomUUID(),
      entity_type: SyncEntityType.Store,
      operation: SyncOperation.Upsert,
      payload: { ...store },
      occurred_at: occurredAt,
    },
  ];

  // Products the register got from the API already exist there; only seed rows need creating.
  const seen = new Set<string>();
  for (const line of cart.lines) {
    if (seen.has(line.product.id) || line.product.origin === "api") continue;
    seen.add(line.product.id);
    events.push({
      idempotency_key: crypto.randomUUID(),
      entity_type: SyncEntityType.Product,
      operation: SyncOperation.Upsert,
      payload: { ...productSyncPayload(line.product), currency: store.currency },
      occurred_at: occurredAt,
    });
  }

  const items = saleItems(cart.lines, customerTax(cart.customer));
  const { subtotal, tax, total } = totals(items);
  const restaurant = request.restaurant ?? null;
  const service = restaurant?.serviceChargeCents ?? 0;
  const serviceTax = restaurant?.serviceChargeTaxCents ?? 0;
  const saleId = crypto.randomUUID();
  const sale: SaleUpsert = {
    id: saleId,
    store_id: store.id,
    cashier_id: request.cashierId,
    currency: store.currency,
    payment_method: request.paymentMethod,
    subtotal_cents: subtotal + service,
    tax_cents: tax + serviceTax,
    total_cents: total + service + serviceTax,
    ...(restaurant
      ? {
          order_id: restaurant.orderId,
          order_item_ids: restaurant.orderItemIds,
          service_charge_cents: service,
          service_charge_tax_cents: serviceTax,
          tip_cents: restaurant.tipCents,
        }
      : {}),
    client_sale_id: saleId,
    items,
    sale_type: cart.mode,
    customer_id: cart.customer?.id ?? null,
    tenders: request.tenders,
    credit_override:
      request.creditApproval !== null
        ? { approved_by_id: request.creditApproval.approvedById, note: request.creditApproval.note }
        : null,
    sold_at: occurredAt,
    invoice_number: request.invoiceNumber ?? null,
    shift_id: request.shiftId ?? null,
    loyalty_points_redeemed: request.loyaltyPoints || null,
    coupon_code: request.couponCode?.trim() || null,
    ...(cart.associate && cart.associate.id !== request.cashierId ? { sales_associate_id: cart.associate.id } : {}),
  };
  events.push({
    idempotency_key: crypto.randomUUID(),
    entity_type: SyncEntityType.Sale,
    operation: SyncOperation.Upsert,
    payload: sale as unknown as Record<string, unknown>,
    occurred_at: occurredAt,
  });
  return events;
}

export function buildQuote(cart: CartState, cashierId: string, validDays: number): QuoteUpsert {
  const store = activeStore();
  const items = saleItems(cart.lines, customerTax(cart.customer));
  const { subtotal, tax, total } = totals(items);
  return {
    id: crypto.randomUUID(),
    store_id: store.id,
    cashier_id: cashierId,
    currency: store.currency,
    sale_type: cart.mode,
    customer_id: cart.customer?.id ?? null,
    valid_days: validDays,
    subtotal_cents: subtotal,
    tax_cents: tax,
    total_cents: total,
    items,
  };
}
