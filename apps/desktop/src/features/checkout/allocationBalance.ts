import type { ProductUpsert } from "@ai-pos/shared-types";

export interface AllocationBalance {
  product_id: string;
  remaining: number;
}

type StockProduct = ProductUpsert & { allocation_remaining?: number | null };

function stockControlled(product: ProductUpsert): boolean {
  return !(
    product.is_service ||
    product.is_open_price ||
    product.has_recipe ||
    product.is_stock_tracked === false ||
    product.item_type === "MADE_TO_ORDER"
  );
}

/**
 * Offline stock sales use the verified terminal remainder.
 * A missing row is `null`, which the cart refuses. Branch on-hand is left untouched.
 * Online selling does not attach the field.
 */
export function withTerminalAllocation<T extends ProductUpsert>(
  product: T,
  balances: ReadonlyMap<string, number> | null,
  offline: boolean,
  fault = false,
): T & { allocation_remaining?: number | null; allocation_status?: string } {
  if (!offline || !stockControlled(product)) return product;
  if (fault) return { ...product, allocation_remaining: null, allocation_status: "failed" };
  if (balances === null) return product;
  const remaining = balances.has(product.id) ? balances.get(product.id)! : null;
  const allocation_status = remaining == null ? "missing" : remaining <= 0 ? "exhausted" : "active";
  return { ...product, allocation_remaining: remaining, allocation_status };
}

export function allocationMap(rows: AllocationBalance[]): Map<string, number> {
  return new Map(rows.map((row) => [row.product_id, row.remaining]));
}

export function allocationLabel(product: StockProduct & { allocation_status?: string }): string | null {
  if (!("allocation_remaining" in product) && product.allocation_status !== "failed") return null;
  if (product.allocation_status === "failed") return "This register: allocation verification failed";
  if (product.allocation_remaining == null) return "This register: allocation not configured";
  if (product.allocation_remaining <= 0) return "This register: allocation exhausted";
  return `This register: ${product.allocation_remaining} available`;
}
