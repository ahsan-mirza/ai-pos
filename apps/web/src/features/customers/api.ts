import type {
  CreditRisk,
  Customer,
  CustomerStatement,
  CustomerUpdate,
  CustomerWrite,
  LedgerAdjustment,
  PaymentCreate,
  PaymentResult,
  Sale,
} from "@ai-pos/shared-types";
import { apiBlob, apiGet, apiPatch, apiPost } from "../../lib/api";

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  }
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

export const customersApi = {
  list: (params: { q?: string | null; customer_type?: string | null; include_inactive?: boolean }) =>
    apiGet<Customer[]>(`/api/v1/customers${query({ limit: 500, ...params })}`),
  get: (id: string) => apiGet<Customer>(`/api/v1/customers/${id}`),
  create: (body: CustomerWrite) => apiPost<Customer>("/api/v1/customers", body),
  update: (id: string, body: CustomerUpdate) => apiPatch<Customer>(`/api/v1/customers/${id}`, body),
  statement: (id: string) => apiGet<CustomerStatement>(`/api/v1/customers/${id}/statement`),
  sales: (id: string) => apiGet<Sale[]>(`/api/v1/customers/${id}/sales`),
  receivePayment: (id: string, body: PaymentCreate) =>
    apiPost<PaymentResult>(`/api/v1/customers/${id}/payments`, body),
  adjust: (id: string, body: LedgerAdjustment) => apiPost<Customer>(`/api/v1/customers/${id}/adjustments`, body),
  creditHold: (id: string, body: { hold: boolean; reason: string }) =>
    apiPost<Customer>(`/api/v1/customers/${id}/credit-hold`, body),
  /** No ids: every active wholesale account with a balance. */
  sendStatements: (customerIds?: string[]) =>
    apiPost<{ queued: number; skipped: number }>("/api/v1/customers/statements/send", { customer_ids: customerIds ?? null }),
  statementPdf: (id: string) => apiBlob(`/api/v1/customers/${id}/statement.pdf`),
  risk: (id: string) => apiGet<CreditRisk>(`/api/v1/customers/${id}/risk`),
};

/** "1,250.50" → 125050. Null when the text is not a plain amount with up to two decimals. */
export function toCents(value: string): number | null {
  const trimmed = value.trim().replace(/,/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

export function centsText(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function shortDate(value: string | null): string {
  if (value === null) return "—";
  return new Date(value).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}
