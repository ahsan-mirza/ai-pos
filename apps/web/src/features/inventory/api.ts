import type {
  CatalogAttributes,
  Availability,
  Brand,
  BrandWrite,
  Category,
  CategoryWrite,
  LevelUpdate,
  ManualAdjustment,
  ManualAdjustmentResult,
  Product,
  ProductCreate,
  ProductModel,
  ProductModelUpdate,
  ProductModelWrite,
  ProductUpdate,
  PurchaseOrder,
  PurchaseOrderCreate,
  ReceiveRequest,
  SerialSearchResult,
  SerialTrace,
  StockMovement,
  StockRow,
  StockSummary,
  StockTransfer,
  StockView,
  Store,
  StoreSerial,
  StoreUpdate,
  TransferCreate,
  TransferShip,
  LabelLayout,
  MatrixBulk,
  MatrixBulkResult,
  MatrixPreview,
  MatrixWrite,
  VariantMatrix,
} from "@ai-pos/shared-types";
import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost } from "../../lib/api";
import { openPdf } from "../../lib/pdf";

export interface PageRequest {
  offset: number;
  limit: number;
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

export interface StockFilters {
  store_id?: string | null;
  category_id?: string | null;
  sub_category_id?: string | null;
  brand_id?: string | null;
  product_model_id?: string | null;
  status?: string | null;
  q?: string | null;
  season?: string | null;
  collection?: string | null;
  gender?: string | null;
  view?: StockView;
}

export const inventoryApi = {
  stock: (filters: StockFilters) => apiGet<StockSummary>(`/api/v1/inventory/stock${query({ ...filters })}`),
  updateLevel: (productId: string, storeId: string, body: LevelUpdate) =>
    apiPatch<StockRow>(`/api/v1/inventory/levels/${productId}/${storeId}`, body),
  adjust: (body: ManualAdjustment) => apiPost<ManualAdjustmentResult>("/api/v1/inventory/adjust", body),
  storeSerials: (productId: string, storeId: string) =>
    apiGet<StoreSerial[]>(`/api/v1/inventory/serials${query({ product_id: productId, store_id: storeId })}`),
  movements: (params: { product_id?: string; store_id?: string | null; limit?: number }) =>
    apiGet<StockMovement[]>(`/api/v1/inventory/movements${query(params)}`),
  availability: (params: { product_id?: string; serial?: string }) =>
    apiGet<Availability>(`/api/v1/inventory/availability${query(params)}`),
  trace: (value: string) => apiGet<SerialTrace>(`/api/v1/inventory/serials/trace${query({ value })}`),
  searchSerials: (params: { query: string; status?: string; limit?: number }) =>
    apiGet<SerialSearchResult>(`/api/v1/serials/search${query({ status: "any", limit: 25, ...params })}`),
  createProduct: (body: ProductCreate) => apiPost<Product>("/api/v1/inventory/products", body),
  updateProduct: (id: string, body: ProductUpdate) => apiPatch<Product>(`/api/v1/products/${id}`, body),
  products: (params: { store_id?: string | null; limit?: number; q?: string }) =>
    params.q
      ? apiGet<{ product: Product }[]>(`/api/v1/products/search${query({ q: params.q, limit: params.limit ?? 50, store_id: params.store_id })}`).then(
          (hits) => hits.map((hit) => hit.product),
        )
      : apiGet<Product[]>(`/api/v1/products${query({ limit: params.limit ?? 100, store_id: params.store_id })}`),

  purchaseOrders: (params: { status?: string | null; store_id?: string | null }, page: PageRequest) =>
    apiGetPage<PurchaseOrder>(`/api/v1/inventory/purchase-orders${query(params)}`, page),
  createPurchaseOrder: (body: PurchaseOrderCreate) => apiPost<PurchaseOrder>("/api/v1/inventory/purchase-orders", body),
  placePurchaseOrder: (id: string) => apiPost<PurchaseOrder>(`/api/v1/inventory/purchase-orders/${id}/order`, {}),
  cancelPurchaseOrder: (id: string) => apiPost<PurchaseOrder>(`/api/v1/inventory/purchase-orders/${id}/cancel`, {}),
  receivePurchaseOrder: (id: string, body: ReceiveRequest) =>
    apiPost<PurchaseOrder>(`/api/v1/inventory/purchase-orders/${id}/receive`, body),

  transfers: (params: { status?: string | null; store_id?: string | null }, page: PageRequest) =>
    apiGetPage<StockTransfer>(`/api/v1/inventory/transfers${query(params)}`, page),
  createTransfer: (body: TransferCreate) => apiPost<StockTransfer>("/api/v1/inventory/transfers", body),
  shipTransfer: (id: string, body: TransferShip) => apiPost<StockTransfer>(`/api/v1/inventory/transfers/${id}/ship`, body),
  receiveTransfer: (id: string) => apiPost<StockTransfer>(`/api/v1/inventory/transfers/${id}/receive`, {}),
  cancelTransfer: (id: string) => apiPost<StockTransfer>(`/api/v1/inventory/transfers/${id}/cancel`, {}),
};

export const categoriesApi = {
  list: () => apiGet<Category[]>("/api/v1/categories"),
  create: (body: CategoryWrite) => apiPost<Category>("/api/v1/categories", body),
  update: (id: string, body: Partial<CategoryWrite>) => apiPatch<Category>(`/api/v1/categories/${id}`, body),
  remove: (id: string) => apiDelete(`/api/v1/categories/${id}`),
  createSub: (categoryId: string, body: CategoryWrite) =>
    apiPost<Category>(`/api/v1/categories/${categoryId}/sub-categories`, body),
  updateSub: (id: string, body: Partial<CategoryWrite>) =>
    apiPatch<Category>(`/api/v1/categories/sub-categories/${id}`, body),
  removeSub: (id: string) => apiDelete(`/api/v1/categories/sub-categories/${id}`),
};

export const brandsApi = {
  list: (params: { sub_category_id?: string | null } = {}) => apiGet<Brand[]>(`/api/v1/brands${query(params)}`),
  create: (body: BrandWrite) => apiPost<Brand>("/api/v1/brands", body),
  update: (id: string, body: Partial<CategoryWrite>) => apiPatch<Brand>(`/api/v1/brands/${id}`, body),
  remove: (id: string) => apiDelete(`/api/v1/brands/${id}`),
  link: (id: string, subCategoryId: string) =>
    apiPost<Brand>(`/api/v1/brands/${id}/sub-categories/${subCategoryId}`, {}),
  unlink: (id: string, subCategoryId: string) => apiDelete(`/api/v1/brands/${id}/sub-categories/${subCategoryId}`),
};

export const modelsApi = {
  list: (params: { sub_category_id?: string | null; brand_id?: string | null } = {}) =>
    apiGet<ProductModel[]>(`/api/v1/product-models${query(params)}`),
  create: (body: ProductModelWrite) => apiPost<ProductModel>("/api/v1/product-models", body),
  update: (id: string, body: ProductModelUpdate) => apiPatch<ProductModel>(`/api/v1/product-models/${id}`, body),
  remove: (id: string) => apiDelete(`/api/v1/product-models/${id}`),
  variants: (modelId: string) => apiGet<Product[]>(`/api/v1/products${query({ product_model_id: modelId, limit: 500 })}`),
  matrix: (modelId: string, storeId?: string | null) =>
    apiGet<VariantMatrix>(`/api/v1/product-models/${modelId}/matrix${query({ store_id: storeId ?? null })}`),
  previewMatrix: (modelId: string, body: MatrixWrite) =>
    apiPost<MatrixPreview>(`/api/v1/product-models/${modelId}/matrix/preview`, body),
  generateMatrix: (modelId: string, body: MatrixWrite) =>
    apiPost<VariantMatrix>(`/api/v1/product-models/${modelId}/matrix`, body),
  bulkMatrix: (modelId: string, body: MatrixBulk) =>
    apiPost<MatrixBulkResult>(`/api/v1/product-models/${modelId}/matrix/bulk`, body),
  attributes: () => apiGet<CatalogAttributes>("/api/v1/catalog/attributes"),
};

export const labelsApi = {
  products: (
    items: { product_id: string; copies: number }[],
    layout: LabelLayout,
    showPrice = true,
    options: { showName?: boolean; showVariant?: boolean; showCurrency?: boolean } = {},
  ) =>
    openPdf("/api/v1/labels", {
      items,
      layout,
      show_price: showPrice,
      show_name: options.showName ?? true,
      show_variant: options.showVariant ?? true,
      show_currency: options.showCurrency ?? true,
    }),
  model: (modelId: string, layout: LabelLayout) => openPdf(`/api/v1/labels/models/${modelId}?layout=${layout}`),
  batch: (batchId: string, layout: LabelLayout) => openPdf(`/api/v1/labels/batches/${batchId}?layout=${layout}`),
};

export const storesApi = {
  list: () => apiGet<Store[]>("/api/v1/stores?limit=200"),
  update: (id: string, body: StoreUpdate) => apiPatch<Store>(`/api/v1/stores/${id}`, body),
};

export function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
