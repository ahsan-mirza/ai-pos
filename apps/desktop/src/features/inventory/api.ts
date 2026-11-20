import type { PharmacyProductDetail, Product } from "@ai-pos/shared-types";
import { RetailRequestError, retailCall, retailPage, retailUpload } from "../../lib/retailClient";

export type ProductDetail = Product;

export function inventoryError(error: unknown, fallback: string): string {
  if (error instanceof RetailRequestError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export function isOffline(error: unknown): boolean {
  return error instanceof RetailRequestError && error.offline;
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

export const inventoryApi = {
  stock: (params: Record<string, string | null | undefined>) =>
    retailCall<{ consolidated: boolean; store_id: string | null; rows: StockRow[]; units_on_hand: number; low_count: number; out_count: number }>(
      "GET",
      `/api/v1/inventory/stock${query(params)}`,
    ),
  movements: (params: Record<string, string | number | null | undefined>) =>
    retailCall<MovementRow[]>("GET", `/api/v1/inventory/movements${query(params)}`),
  adjust: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/inventory/adjust", body),
  products: (params: Record<string, string | number | null | undefined>) =>
    retailCall<ProductRow[]>("GET", `/api/v1/products${query(params)}`),
  searchProducts: (q: string, storeId: string | null) =>
    retailCall<{ product: ProductRow }[]>("GET", `/api/v1/products/search${query({ q, limit: 50, store_id: storeId })}`),
  product: (id: string) => retailCall<ProductDetail>("GET", `/api/v1/products/${id}`),
  createProduct: (body: Record<string, unknown>) => retailCall<ProductRow>("POST", "/api/v1/inventory/products", body),
  createPharmacyProduct: (body: Record<string, unknown>) => retailCall<ProductRow>("POST", "/api/v1/pharmacy/products", body),
  updateProduct: (id: string, body: Record<string, unknown>) => retailCall<ProductRow>("PATCH", `/api/v1/products/${id}`, body),
  updatePharmacyProduct: (id: string, body: Record<string, unknown>) =>
    retailCall<ProductRow>("PATCH", `/api/v1/pharmacy/products/${id}`, body),
  deleteProduct: (id: string) => retailCall<unknown>("DELETE", `/api/v1/products/${id}`),
  uploadProductImage: (productId: string, file: File) =>
    retailUpload(`/api/v1/inventory/products/${productId}/images`, file),
  productImages: (productId: string) =>
    retailCall<CatalogueImage[]>("GET", `/api/v1/inventory/products/${productId}/images`),
  updateImage: (imageId: string, body: Record<string, unknown>) =>
    retailCall<CatalogueImage>("PATCH", `/api/v1/inventory/images/${imageId}`, body),
  deleteImage: (imageId: string) => retailCall<unknown>("DELETE", `/api/v1/inventory/images/${imageId}`),
  uploadModelImage: (modelId: string, file: File) => retailUpload(`/api/v1/product-models/${modelId}/images`, file),
  categories: () => retailCall<CategoryRow[]>("GET", "/api/v1/categories"),
  createCategory: (body: Record<string, unknown>) => retailCall<CategoryRow>("POST", "/api/v1/categories", body),
  createSubCategory: (categoryId: string, body: Record<string, unknown>) =>
    retailCall<CategoryRow>("POST", `/api/v1/categories/${categoryId}/sub-categories`, body),
  updateCategory: (id: string, body: Record<string, unknown>) => retailCall<CategoryRow>("PATCH", `/api/v1/categories/${id}`, body),
  deleteCategory: (id: string) => retailCall<unknown>("DELETE", `/api/v1/categories/${id}`),
  brands: () => retailCall<BrandRow[]>("GET", "/api/v1/brands"),
  createBrand: (body: Record<string, unknown>) => retailCall<NamedRow>("POST", "/api/v1/brands", body),
  updateBrand: (id: string, body: Record<string, unknown>) => retailCall<NamedRow>("PATCH", `/api/v1/brands/${id}`, body),
  deleteBrand: (id: string) => retailCall<unknown>("DELETE", `/api/v1/brands/${id}`),
  models: (params: Record<string, string | null | undefined> = {}) =>
    retailCall<ModelRow[]>("GET", `/api/v1/product-models${query(params)}`),
  createModel: (body: Record<string, unknown>) => retailCall<ModelRow>("POST", "/api/v1/product-models", body),
  modelMatrix: (id: string) => retailCall<VariantMatrix>("GET", `/api/v1/product-models/${id}/matrix`),
  generateMatrix: (id: string, body: Record<string, unknown>) =>
    retailCall<unknown>("POST", `/api/v1/product-models/${id}/matrix`, body),
  updateModel: (id: string, body: Record<string, unknown>) => retailCall<ModelRow>("PATCH", `/api/v1/product-models/${id}`, body),
  units: () => retailCall<UnitRow[]>("GET", "/api/v1/units"),
  createUnit: (body: Record<string, unknown>) => retailCall<UnitRow>("POST", "/api/v1/units", body),
  updateUnit: (id: string, body: Record<string, unknown>) => retailCall<UnitRow>("PATCH", `/api/v1/units/${id}`, body),
  pricing: (q: string) => retailCall<{ rows: PricingRow[] }>("GET", `/api/v1/pricing/matrix${query({ q, limit: 200 })}`),
  updatePrice: (productId: string, body: Record<string, unknown>) =>
    retailCall<unknown>("PUT", `/api/v1/pricing/products/${productId}`, body),
  priceLists: () => retailCall<PriceListRow[]>("GET", "/api/v1/price-lists"),
  createPriceList: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/price-lists", body),
  priceChanges: () => retailCall<PriceChangeRow[]>("GET", "/api/v1/price-lists/changes"),
  createPriceChange: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/price-lists/changes", body),
  batches: (params: Record<string, string | number | null | undefined>) =>
    retailCall<{ rows: BatchRow[] }>("GET", `/api/v1/inventory/batches${query({ ...params, limit: 50 })}`),
  batch: (id: string) => retailCall<BatchDetail>("GET", `/api/v1/inventory/batches/${id}`),
  expiring: () => retailCall<ExpiringRow[]>("GET", "/api/v1/inventory/expiring"),
  writeOff: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/inventory/expiry-writeoff", body),
  replenishment: (storeId: string) =>
    retailCall<RunRow | null>("GET", `/api/v1/replenishment/runs/latest?store_id=${encodeURIComponent(storeId)}`),
  runReplenishment: (storeId: string) => retailCall<RunRow>("POST", "/api/v1/replenishment/runs", { store_id: storeId, review_days: 7 }),
  acceptReplenishment: (runId: string, lines: { id: string; quantity: number }[]) =>
    retailCall<unknown>("POST", `/api/v1/replenishment/runs/${runId}/accept`, { lines }),
  counts: (storeId: string | null) => retailCall<CountSummary[]>(`GET`, `/api/v1/inventory/counts${query({ store_id: storeId, limit: 50 })}`),
  createCount: (body: Record<string, unknown>) => retailCall<CountDetail>("POST", "/api/v1/inventory/counts", body),
  count: (id: string) => retailCall<CountDetail>("GET", `/api/v1/inventory/counts/${id}`),
  recordCount: (id: string, entries: { product_id: string; counted_qty: number }[]) =>
    retailCall<CountDetail>("PUT", `/api/v1/inventory/counts/${id}/lines`, { entries }),
  submitCount: (id: string) => retailCall<CountDetail>("POST", `/api/v1/inventory/counts/${id}/submit`, {}),
  reviewCount: (id: string, action: "post" | "cancel") => retailCall<CountDetail>("POST", `/api/v1/inventory/counts/${id}/${action}`, {}),
  purchaseOrders: (storeId: string | null) =>
    retailPage<PurchaseOrder>(`/api/v1/inventory/purchase-orders${query({ store_id: storeId, offset: 0, limit: 50 })}`),
  purchaseOrder: (id: string) => retailCall<PurchaseOrder>("GET", `/api/v1/inventory/purchase-orders/${id}`),
  createPurchaseOrder: (body: Record<string, unknown>) => retailCall<PurchaseOrder>("POST", "/api/v1/inventory/purchase-orders", body),
  updatePurchaseOrder: (id: string, body: Record<string, unknown>) =>
    retailCall<PurchaseOrder>("PUT", `/api/v1/inventory/purchase-orders/${id}`, body),
  placePurchaseOrder: (id: string) => retailCall<PurchaseOrder>("POST", `/api/v1/inventory/purchase-orders/${id}/order`, {}),
  receivePurchaseOrder: (id: string, body: Record<string, unknown>) =>
    retailCall<PurchaseOrder>("POST", `/api/v1/inventory/purchase-orders/${id}/receive`, body),
  cancelPurchaseOrder: (id: string) => retailCall<PurchaseOrder>("POST", `/api/v1/inventory/purchase-orders/${id}/cancel`, {}),
  transfers: (storeId: string | null) =>
    retailPage<Transfer>(`/api/v1/inventory/transfers${query({ store_id: storeId, offset: 0, limit: 50 })}`),
  createTransfer: (body: Record<string, unknown>) => retailCall<Transfer>("POST", "/api/v1/inventory/transfers", body),
  transfer: (id: string) => retailCall<TransferDetail>("GET", `/api/v1/inventory/transfers/${id}`),
  shipTransfer: (id: string) => retailCall<Transfer>("POST", `/api/v1/inventory/transfers/${id}/ship`, { serial_lines: [] }),
  receiveTransfer: (id: string) => retailCall<Transfer>("POST", `/api/v1/inventory/transfers/${id}/receive`, {}),
  cancelTransfer: (id: string) => retailCall<Transfer>("POST", `/api/v1/inventory/transfers/${id}/cancel`, {}),
  stores: () => retailCall<StoreRow[]>("GET", "/api/v1/stores?limit=200"),
  serials: (q: string) => retailCall<SerialSearch>("GET", `/api/v1/serials/search${query({ query: q, status: "any", limit: 25 })}`),
  recipes: () => retailCall<RecipeRow[]>("GET", "/api/v1/recipes"),
  pharmacyProduct: (id: string) => retailCall<PharmacyProductDetail>("GET", `/api/v1/pharmacy/products/${id}`),
  pharmacyProducts: async (q: string) => {
    const rows = await retailCall<(ProductRow & { product_id?: string })[]>("GET", `/api/v1/pharmacy/products${query({ q, limit: 50 })}`);
    return rows.map((row) => ({ ...row, id: row.id || row.product_id || "" }));
  },
  releaseLot: (id: string, reason: string) =>
    retailCall<unknown>("POST", `/api/v1/pharmacy/lots/${id}/release`, { reason, confirm: true }),
  quarantineLot: (id: string, reason: string) => retailCall<unknown>("POST", `/api/v1/pharmacy/lots/${id}/quarantine`, { reason }),
  clearQuarantine: (id: string, reason: string) =>
    retailCall<unknown>("POST", `/api/v1/pharmacy/lots/${id}/clear-quarantine`, { reason, confirm: true }),
  supplierReturn: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/pharmacy/supplier-returns", body),
  recall: (body: Record<string, unknown>) => retailCall<unknown>("POST", "/api/v1/pharmacy/recalls", body),
  lotEvents: (id: string) => retailCall<{ action: string; created_at: string; reason: string | null }[]>("GET", `/api/v1/pharmacy/lots/${id}/events`),
};

export interface StockRow {
  product_id: string;
  sku: string;
  name: string;
  barcode?: string | null;
  brand: string | null;
  model_number: string | null;
  category: string;
  sub_category: string | null;
  store_id: string | null;
  store_name: string | null;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  min_reorder_level: number;
  status: string;
  lot_controlled?: boolean;
  eligible_quantity?: number | null;
}

export interface MovementRow {
  id: string;
  movement_type: string;
  quantity: number;
  quantity_after: number;
  user_name: string | null;
  note: string;
  created_at: string;
  reason_code?: string | null;
}

export interface ProductRow {
  id: string;
  sku: string;
  name: string;
  barcode?: string | null;
  price_cents: number;
  is_active?: boolean;
  category?: string | null;
  category_id?: string | null;
  brand?: string | null;
  stock_quantity?: number;
}

export interface CategoryRow {
  id: string;
  name: string;
  code: string;
  description: string;
  is_active?: boolean;
  product_count: number;
  sub_categories: { id: string; name: string; code: string; is_active?: boolean; product_count: number }[];
}

export interface NamedRow {
  id: string;
  name: string;
  code: string;
  description: string;
  is_active?: boolean;
  product_count?: number;
}

export interface CatalogueImage {
  id: string;
  url: string;
  thumb_url: string;
  position: number;
  is_primary: boolean;
}

export interface BrandRow extends NamedRow {
  sub_category_ids?: string[];
}

export interface VariantMatrix {
  axes: { key: string; values: string[] }[];
  cells: {
    attributes: Record<string, string>;
    product_id: string;
    sku: string;
    barcode: string;
    price_cents: number;
    cost_cents?: number | null;
    on_hand: number;
    is_active?: boolean;
  }[];
}

export interface ModelRow extends NamedRow {
  brand_id: string;
  brand_name: string;
  sub_category_id: string;
}

export interface UnitRow {
  id: string | null;
  code: string;
  name: string;
  short_name: string;
  factor: number;
  is_system: boolean;
  is_active: boolean;
  products: number;
}

export interface PricingRow {
  product_id: string;
  sku: string;
  name: string;
  retail_price_cents: number;
}

export interface PriceListRow {
  id: string;
  name: string;
  scope: string;
  is_active: boolean;
  valid_from: string | null;
  valid_to: string | null;
  status?: string;
}

export interface PriceChangeRow {
  id: string;
  name: string;
  status: string;
  run_at: string;
  note: string;
  created_by_name: string | null;
  lines: { sku: string; name: string; current_retail_cents: number; retail_price_cents: number | null }[];
}

export interface BatchRow {
  id: string;
  batch_number: string;
  store_name: string;
  supplier_name: string | null;
  status: string;
  units_remaining: number;
  units_sold: number;
}

export interface BatchDetail {
  id: string;
  batch_number: string;
  items: {
    id: string;
    product_id: string;
    product_name: string;
    sku: string;
    quantity_remaining: number;
    expiry_date: string | null;
    manufacturer_lot?: string | null;
    lot_status?: string | null;
  }[];
}

export interface ExpiringRow {
  batch_item_id: string;
  product_name: string;
  sku: string;
  store_code: string;
  expiry_date: string;
  days_left: number;
  quantity_remaining: number;
}

export interface RunRow {
  id: string;
  suggestions: {
    id: string;
    product_name: string;
    sku: string;
    on_hand: number;
    suggested_qty: number;
    status: string;
    supplier_name: string | null;
  }[];
}

export interface CountSummary {
  id: string;
  number: string;
  store_name: string;
  status: string;
  category_name: string | null;
}

export interface CountDetail extends CountSummary {
  lines: {
    product_id: string;
    sku: string;
    name: string;
    counted_qty: number | null;
    expected_qty: number | null;
    variance: number | null;
  }[];
  can_review: boolean;
}

export interface PurchaseOrder {
  id: string;
  number: string;
  supplier_name: string;
  status: string;
  destination_store_id: string;
  destination_store_name: string;
  notes: string;
  total_cost_cents: number;
  lines: {
    id: string;
    product_id: string;
    name: string;
    quantity_ordered: number;
    quantity_received: number;
    unit_cost_cents: number;
    lot_controlled?: boolean;
  }[];
}

export interface Transfer {
  id: string;
  number: string;
  status: string;
  source_store_code: string;
  destination_store_code: string;
}

export interface TransferDetail extends Transfer {
  lines: { id: string; sku: string; name: string; quantity: number }[];
}

export interface StoreRow {
  id: string;
  code: string;
  name: string;
}

export interface SerialSearch {
  match: string;
  hint: string | null;
  rows: { id: string; product_name: string | null; sku: string | null; store_code: string; value: string; status: string }[];
}

export interface RecipeRow {
  product_id: string;
  product_name: string;
  lines: { ingredient_name: string; quantity: number; sold_by_weight: boolean }[];
}
