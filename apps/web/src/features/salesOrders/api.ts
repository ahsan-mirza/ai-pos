import type {
  BackorderRow,
  FulfillmentBoard,
  SalesOrderEvent,
  DeliverInput,
  DeliveryNote,
  DispatchInput,
  SalesOrder,
  SalesOrderCreate,
  SalesOrderRow,
  SalesOrderUpdate,
} from "@ai-pos/shared-types";
import { apiGet, apiGetPage, apiPatch, apiPost } from "../../lib/api";
import { openPdf } from "../../lib/pdf";

const BASE = "/api/v1/sales-orders";

function query(params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const salesOrdersApi = {
  list: (filters: { status?: string | null; store_id?: string | null; q?: string | null }, page: { offset: number; limit: number }) =>
    apiGetPage<SalesOrderRow>(`${BASE}${query(filters)}`, page),
  get: (id: string) => apiGet<SalesOrder>(`${BASE}/${id}`),
  create: (body: SalesOrderCreate) => apiPost<SalesOrder>(BASE, body),
  update: (id: string, body: SalesOrderUpdate) => apiPatch<SalesOrder>(`${BASE}/${id}`, body),
  confirm: (id: string, creditApprovedById: string | null) =>
    apiPost<SalesOrder>(`${BASE}/${id}/confirm`, { credit_approved_by_id: creditApprovedById }),
  allocate: (id: string) => apiPost<SalesOrder>(`${BASE}/${id}/allocate`, {}),
  pick: (id: string) => apiPost<SalesOrder>(`${BASE}/${id}/pick`, {}),
  dispatch: (id: string, body: DispatchInput) => apiPost<SalesOrder>(`${BASE}/${id}/dispatch`, body),
  cancelLines: (id: string, lines: { order_line_id: string; quantity: number }[], reason: string) =>
    apiPost<SalesOrder>(`${BASE}/${id}/cancel-lines`, { lines, reason }),
  cancel: (id: string, reason: string) => apiPost<SalesOrder>(`${BASE}/${id}/cancel`, { reason }),
  close: (id: string, reason: string) => apiPost<SalesOrder>(`${BASE}/${id}/close`, { reason }),
  fromQuote: (quoteId: string) => apiPost<SalesOrder>(`${BASE}/from-quote/${quoteId}`, {}),
  backorders: (storeId: string | null) =>
    apiGet<BackorderRow[]>(`${BASE}/backorders${storeId ? `?store_id=${storeId}` : ""}`),
  board: (filters: {
    storeId?: string | null;
    status?: string | null;
    q?: string | null;
    dateFrom?: string | null;
    dateTo?: string | null;
    page?: number;
    pageSize?: number;
  }) =>
    apiGet<FulfillmentBoard>(
      `${BASE}/board${query({
        store_id: filters.storeId,
        status: filters.status,
        q: filters.q,
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        page: filters.page ? String(filters.page) : null,
        page_size: filters.pageSize ? String(filters.pageSize) : null,
      })}`,
    ),
  events: (id: string) => apiGet<SalesOrderEvent[]>(`${BASE}/${id}/events`),
  delivery: (noteId: string) => apiGet<DeliveryNote>(`${BASE}/deliveries/${noteId}`),
  deliver: (noteId: string, body: DeliverInput) => apiPost<DeliveryNote>(`${BASE}/deliveries/${noteId}/deliver`, body),
  orderPdf: (id: string) => openPdf(`${BASE}/${id}/pdf`),
  pickListPdf: (pickId: string) => openPdf(`${BASE}/pick-lists/${pickId}/pdf`),
  deliveryPdf: (noteId: string) => openPdf(`${BASE}/deliveries/${noteId}/pdf`),
  invoicePdf: (saleId: string) => openPdf(`/api/v1/sales/${saleId}/invoice.pdf`),
};
