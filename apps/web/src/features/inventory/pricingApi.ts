import type {
  BulkPriceResult,
  BulkPriceUpdate,
  PricingMatrix,
  PricingRow,
  ProductPricingWrite,
} from "@ai-pos/shared-types";
import { apiGet, apiPut } from "../../lib/api";

export const pricingApi = {
  matrix: (params: { category_id?: string | null; brand?: string | null; q?: string | null }) => {
    const search = new URLSearchParams({ limit: "1000" });
    for (const [key, value] of Object.entries(params)) {
      if (value) search.set(key, value);
    }
    return apiGet<PricingMatrix>(`/api/v1/pricing/matrix?${search.toString()}`);
  },
  updateProduct: (id: string, body: ProductPricingWrite) => apiPut<PricingRow>(`/api/v1/pricing/products/${id}`, body),
  bulk: (body: BulkPriceUpdate) => apiPut<BulkPriceResult>("/api/v1/pricing/bulk", body),
};
