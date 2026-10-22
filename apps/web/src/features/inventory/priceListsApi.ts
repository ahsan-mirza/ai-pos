import type {
  CsvImportResult,
  CustomerGroup,
  CustomerGroupWrite,
  PriceChange,
  PriceChangeWrite,
  PriceList,
  PriceListItemWrite,
  PriceListRow,
  PriceListWrite,
} from "@ai-pos/shared-types";
import { apiBlob, apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { openPdf } from "../../lib/pdf";

const BASE = "/api/v1/price-lists";

export const priceListsApi = {
  list: () => apiGet<PriceListRow[]>(BASE),
  get: (id: string) => apiGet<PriceList>(`${BASE}/${id}`),
  create: (body: PriceListWrite) => apiPost<PriceList>(BASE, body),
  update: (id: string, body: PriceListWrite) => apiPut<PriceList>(`${BASE}/${id}`, body),
  remove: (id: string) => apiDelete(`${BASE}/${id}`),
  putItems: (id: string, items: PriceListItemWrite[]) => apiPut<PriceList>(`${BASE}/${id}/items`, { items }),
  importCsv: (id: string, csv: string, replace: boolean) =>
    apiPost<CsvImportResult>(`${BASE}/${id}/import`, { csv, replace }),
  exportCsv: async (id: string, name: string) => {
    const blob = await apiBlob(`${BASE}/${id}/export.csv`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name.replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "price-list"}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
  },
  groups: () => apiGet<CustomerGroup[]>(`${BASE}/groups`),
  createGroup: (body: CustomerGroupWrite) => apiPost<CustomerGroup>(`${BASE}/groups`, body),
  updateGroup: (id: string, body: CustomerGroupWrite) => apiPut<CustomerGroup>(`${BASE}/groups/${id}`, body),
  changes: () => apiGet<PriceChange[]>(`${BASE}/changes`),
  createChange: (body: PriceChangeWrite) => apiPost<PriceChange>(`${BASE}/changes`, body),
  cancelChange: (id: string) => apiPost<PriceChange>(`${BASE}/changes/${id}/cancel`, {}),
  applyChange: (id: string) => apiPost<PriceChange>(`${BASE}/changes/${id}/apply`, {}),
  changeLabels: (id: string) => openPdf(`${BASE}/changes/${id}/labels.pdf`),
};
