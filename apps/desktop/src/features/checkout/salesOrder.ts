import type { SalesOrder, SalesOrderCreate, SalesOrderLineInput } from "@ai-pos/shared-types";
import { call } from "../orders/ordersClient";
import type { CartState } from "./cart";
import { activeStore } from "./currency";
import { saleItems } from "./queue";

/** A wholesale cart as a sales order: delivered (and invoiced) later, in one or more drops, from the portal. */
export function buildSalesOrder(cart: CartState, cashierId: string): SalesOrderCreate {
  const items = saleItems(cart.lines);
  const grouped = new Map<string, SalesOrderLineInput>();
  let approver: string | null = null;
  for (const item of items) {
    const agreed = item.price_override ? item.unit_price_cents : null;
    if (item.price_override) approver = item.price_override.approved_by_id;
    const key = `${item.product_id}:${agreed ?? "tier"}`;
    const line = grouped.get(key);
    if (line) line.quantity += item.quantity;
    else grouped.set(key, { product_id: item.product_id, quantity: item.quantity, unit_price_cents: agreed });
  }
  return {
    id: crypto.randomUUID(),
    store_id: activeStore().id,
    customer_id: cart.customer?.id ?? "",
    sale_type: cart.mode,
    lines: [...grouped.values()],
    confirm: true,
    price_approved_by_id: approver,
    user_id: cashierId,
    source: "register",
  };
}

export function submitSalesOrder(body: SalesOrderCreate): Promise<SalesOrder> {
  return call<SalesOrder>("POST", "/api/v1/sales-orders", body);
}
