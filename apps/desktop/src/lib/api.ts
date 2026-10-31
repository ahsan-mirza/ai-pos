import type {
  Availability,
  BusinessSettings,
  ProductCosting,
  Recipe,
  Customer,
  Product,
  ProductSearchHit,
  ProductUpsert,
  Quote,
  QuoteUpsert,
  Receipt,
  ReceiptProfile,
  SyncEvent,
  SyncPushResponse,
  TokenResponse,
} from "@ai-pos/shared-types";
import { env, previewHeaders } from "../config/env";

export class ApiRejectedError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export class ApiUnavailableError extends Error {}

function apiKey(): string {
  if (env.apiKey === null) {
    throw new ApiUnavailableError("VITE_API_KEY is not set, so the browser preview cannot reach the API.");
  }
  return env.apiKey;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    if (body.error?.message) return body.error.message;
  } catch {
    // Fall through to the status text.
  }
  return `Request failed (${response.status}).`;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...previewHeaders(), "X-Terminal-Token": apiKey(), ...init.headers },
    });
  } catch (error) {
    if (error instanceof ApiUnavailableError) throw error;
    throw new ApiUnavailableError(`Cannot reach the API at ${env.apiBaseUrl}. Check that the backend is running.`);
  }
  if (response.ok) return response;
  const message = await errorMessage(response);
  if ([401, 403, 409, 413, 422, 423].includes(response.status)) {
    throw new ApiRejectedError(message, response.status);
  }
  throw new ApiUnavailableError(message);
}

export async function pushBatch(events: SyncEvent[]): Promise<SyncPushResponse> {
  const response = await request("/api/v1/sync/push", {
    method: "POST",
    body: JSON.stringify({ device_id: env.deviceId, events }),
  });
  return (await response.json()) as SyncPushResponse;
}

export async function loginPin(username: string, pin: string): Promise<TokenResponse> {
  const response = await request("/api/v1/auth/login-pin", {
    method: "POST",
    body: JSON.stringify({ username, pin }),
  });
  return (await response.json()) as TokenResponse;
}

export interface CashierCard {
  id: string;
  display_name: string;
  initials: string;
  role_label: string;
  avatar_url: string | null;
}

/** Cashiers the activated terminal may offer. The server decides the branch. */
export async function listCashiers(): Promise<CashierCard[]> {
  const response = await request("/api/v1/auth/cashiers");
  return (await response.json()) as CashierCard[];
}

export async function unlockCashier(userId: string, pin: string): Promise<TokenResponse> {
  const response = await request("/api/v1/auth/unlock", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, pin }),
  });
  return (await response.json()) as TokenResponse;
}

/** Catalog row with this branch's stock. Category ids ride along so charge batches keep the product's category. */
function toUpsert(row: Product): ProductUpsert {
  return {
    id: row.id,
    store_id: row.store_id ?? env.storeId,
    sku: row.sku,
    barcode: row.barcode,
    name: row.name,
    model_number: row.model_number ?? null,
    brand: row.brand ?? null,
    category: row.category,
    category_id: row.category_id ?? null,
    sub_category_id: row.sub_category_id ?? null,
    price_cents: row.price_cents,
    currency: row.currency,
    is_serialized: row.is_serialized,
    stock_quantity: row.stock_quantity - (row.quantity_reserved ?? 0),
    min_order_quantity: row.min_order_quantity ?? 1,
    sellable_units: row.sellable_units ?? ["PIECE"],
    unit_options: row.unit_options ?? [],
    prices: row.prices ?? [],
    tax_category: row.tax_category ?? "STANDARD",
    price_includes_tax: row.price_includes_tax === true,
    is_open_price: row.is_open_price ?? false,
    is_service: row.is_service ?? false,
    sold_by_weight: row.sold_by_weight ?? false,
    plu_code: row.plu_code ?? null,
    tare_grams: row.tare_grams ?? 0,
    minimum_age: row.minimum_age ?? null,
    nearest_expiry: row.nearest_expiry ?? null,
    has_recipe: row.has_recipe ?? false,
    is_ingredient: row.is_ingredient ?? false,
    item_type: row.item_type,
    is_stock_tracked: row.is_stock_tracked ?? true,
    price_lists: row.price_lists ?? [],
    image_url: row.image_url ?? null,
    thumb_url: row.thumb_url ?? null,
    product_model_id: row.product_model_id ?? null,
    model_name: row.model_name ?? null,
    variant_attributes: row.variant_attributes ?? {},
    specifications: row.specifications ?? {},
    is_active: row.is_active ?? true,
    price_source: row.price_source,
    variant_swatches: row.variant_swatches ?? {},
    origin: "api",
  };
}

export async function catalogRevision(): Promise<{ updated_at: string | null; count: number }> {
  const response = await request("/api/v1/products/revision");
  return (await response.json()) as { updated_at: string | null; count: number };
}

const CATALOG_PAGE = 1000;

/** The whole catalog, page by page (GET /products?after=), so large supermarket catalogs are complete. */
export async function listProducts(): Promise<ProductUpsert[]> {
  const products: ProductUpsert[] = [];
  let after: string | null = null;
  for (;;) {
    const params = new URLSearchParams({ limit: String(CATALOG_PAGE), store_id: env.storeId });
    if (after !== null) params.set("after", after);
    const response = await request(`/api/v1/products?${params.toString()}`);
    const page = (await response.json()) as Product[];
    products.push(...page.map(toUpsert));
    if (page.length < CATALOG_PAGE) return products;
    after = page[page.length - 1]!.id;
  }
}

export async function productCost(productId: string, storeId: string): Promise<ProductCosting | null> {
  try {
    const params = new URLSearchParams({ product_id: productId, store_id: storeId });
    const response = await request(`/api/v1/inventory/adjust/cost?${params.toString()}`);
    return (await response.json()) as ProductCosting;
  } catch (error) {
    if (error instanceof ApiRejectedError || error instanceof ApiUnavailableError) return null;
    throw error;
  }
}

export async function productRecipe(productId: string): Promise<Recipe | null> {
  try {
    const response = await request(`/api/v1/recipes/${productId}`);
    return (await response.json()) as Recipe;
  } catch (error) {
    if (error instanceof ApiRejectedError || error instanceof ApiUnavailableError) return null;
    throw error;
  }
}

export async function branchAvailability(params: { productId?: string; serial?: string }): Promise<Availability> {
  const search = new URLSearchParams();
  if (params.productId) search.set("product_id", params.productId);
  if (params.serial) search.set("serial", params.serial);
  const response = await request(`/api/v1/inventory/availability?${search.toString()}`);
  return (await response.json()) as Availability;
}

export async function searchProductsRemote(query: string, limit = 50): Promise<ProductSearchHit<ProductUpsert>[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit), store_id: env.storeId });
  const response = await request(`/api/v1/products/search?${params.toString()}`);
  const hits = (await response.json()) as ProductSearchHit[];
  return hits.map((hit) => ({ ...hit, product: toUpsert(hit.product) }));
}

export async function getBusinessSettings(): Promise<BusinessSettings> {
  const response = await request("/api/v1/settings");
  return (await response.json()) as BusinessSettings;
}

export async function getReceiptProfile(storeId: string): Promise<ReceiptProfile> {
  const response = await request(`/api/v1/settings/receipt?store_id=${encodeURIComponent(storeId)}`);
  return (await response.json()) as ReceiptProfile;
}

export async function lookupReceipt(code: string): Promise<Receipt> {
  const response = await request(`/api/v1/returns/receipts/${encodeURIComponent(code)}`);
  return (await response.json()) as Receipt;
}

export interface CustomerPurchase {
  sold_at: string;
  name: string;
  size: string | null;
  color: string | null;
  quantity: number;
}

export interface IssuedCoupon {
  code: string;
  status: string;
  reason: string;
  expires_at: string | null;
  promotion_id: string;
  promotion_name: string;
  kind: "PERCENT_OFF" | "BUY_X_GET_Y" | "MIX_MATCH" | "BUNDLE" | "AMOUNT_OFF";
  amount_cents: number | null;
  percent_bps: number | null;
  min_spend_cents: number;
  product_ids: string[];
  category_ids: string[];
}

export async function customerCoupons(customerId: string): Promise<IssuedCoupon[]> {
  const response = await request(`/api/v1/customers/${customerId}/coupons`);
  return (await response.json()) as IssuedCoupon[];
}

export async function customerHistory(customerId: string): Promise<CustomerPurchase[]> {
  const response = await request(`/api/v1/customers/${customerId}/history?limit=5`);
  return (await response.json()) as CustomerPurchase[];
}

export async function listCustomersRemote(): Promise<Customer[]> {
  const response = await request("/api/v1/customers/sync");
  return (await response.json()) as Customer[];
}

export interface RemoteSerial {
  id: string;
  product_id: string;
  kind: "imei" | "serial";
  value: string;
}

export async function registerSerialsRemote(productId: string): Promise<RemoteSerial[]> {
  const params = new URLSearchParams({ store_id: env.storeId, product_id: productId });
  const response = await request(`/api/v1/inventory/register-serials?${params.toString()}`);
  return (await response.json()) as RemoteSerial[];
}

export async function createQuoteRemote(payload: QuoteUpsert): Promise<Quote> {
  const response = await request("/api/v1/quotes", { method: "POST", body: JSON.stringify(payload) });
  return (await response.json()) as Quote;
}

/** Browser preview: fetch the PDF with the API key and open it from a blob URL. */
export interface RemotePeripheral {
  id: string;
  kind: "kds" | "table_apps" | "customer_display" | "card_terminal";
  label: string;
  name: string;
  light: "green" | "red" | "gray" | "amber";
  status: string;
  connection: string;
  last_seen_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  address: string | null;
  pending: number | null;
  connected: number | null;
  configured: number | null;
}

export async function peripheralSnapshot(): Promise<RemotePeripheral[]> {
  const response = await request("/api/v1/peripherals");
  const body = (await response.json()) as { items: RemotePeripheral[] };
  return body.items;
}

export async function checkCardTerminal(): Promise<{ ok: boolean; message: string }> {
  const response = await request("/api/v1/peripherals/card-terminal/check", { method: "POST" });
  return (await response.json()) as { ok: boolean; message: string };
}

export async function openQuotePdfRemote(quoteId: string): Promise<void> {
  const response = await request(`/api/v1/quotes/${encodeURIComponent(quoteId)}/pdf`);
  const url = URL.createObjectURL(await response.blob());
  window.open(url, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
