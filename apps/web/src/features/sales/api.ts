import type { Quote, QuoteConvert, QuoteList, QuotePaymentInput, QuoteStatus } from "@ai-pos/shared-types";
import { apiBlob, apiGet, apiPost } from "../../lib/api";

export const quotesApi = {
  addPayment: (id: string, body: QuotePaymentInput) => apiPost<Quote>(`/api/v1/quotes/${id}/payments`, body),
  list: (status: QuoteStatus | null, page: { offset: number; limit: number }) =>
    apiGet<QuoteList>(
      `/api/v1/quotes?offset=${page.offset}&limit=${page.limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`,
    ),
  convert: (id: string, body: QuoteConvert) => apiPost<Quote>(`/api/v1/quotes/${id}/convert`, body),
  cancel: (id: string) => apiPost<Quote>(`/api/v1/quotes/${id}/cancel`, {}),
  /** Opens the proforma PDF in a new tab. */
  openPdf: async (id: string) => {
    const tab = window.open("", "_blank");
    const blob = await apiBlob(`/api/v1/quotes/${id}/pdf`);
    const url = URL.createObjectURL(blob);
    if (tab) tab.location.href = url;
    else window.open(url, "_blank");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
