import type {
  AuditActionType,
  AuditFacets,
  AuditLogDetail,
  AuditLogPage,
  AuditLogQuery,
  AuditSummary,
  Store,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, apiBlob, apiGet } from "../../lib/api";

export const PAGE_SIZE = 50;

export type RangePreset = "today" | "7d" | "30d" | "90d" | "custom";

export interface AuditFilterState {
  range: RangePreset;
  customFrom: string;
  customTo: string;
  userId: string;
  storeId: string;
  actionType: AuditActionType | "";
  sensitiveOnly: boolean;
  search: string;
}

export const initialFilters: AuditFilterState = {
  range: "7d",
  customFrom: "",
  customTo: "",
  userId: "",
  storeId: "",
  actionType: "",
  sensitiveOnly: false,
  search: "",
};

const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
const addDays = (date: Date, days: number) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
const parseDay = (value: string) => {
  const [year, month, day] = value.split("-").map(Number);
  return year && month && day ? new Date(year, month - 1, day) : null;
};

/** Local-day bounds for the range picker; `to` is exclusive (the midnight after the last day). */
export function rangeBounds(filters: AuditFilterState): { from?: Date; to?: Date } {
  const today = startOfDay(new Date());
  switch (filters.range) {
    case "today":
      return { from: today };
    case "7d":
      return { from: addDays(today, -6) };
    case "30d":
      return { from: addDays(today, -29) };
    case "90d":
      return { from: addDays(today, -89) };
    case "custom": {
      const from = parseDay(filters.customFrom) ?? undefined;
      const last = parseDay(filters.customTo);
      return { from, to: last ? addDays(last, 1) : undefined };
    }
  }
}

export function toQuery(filters: AuditFilterState): AuditLogQuery {
  const { from, to } = rangeBounds(filters);
  return {
    from: from?.toISOString(),
    to: to?.toISOString(),
    user_id: filters.userId || undefined,
    store_id: filters.storeId || undefined,
    action_type: filters.actionType ? [filters.actionType] : undefined,
    q: filters.search.trim() || undefined,
    sensitive_only: filters.sensitiveOnly || undefined,
  };
}

export function queryString(query: AuditLogQuery, extra: Record<string, string | number> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
    else params.set(key, String(value));
  }
  for (const [key, value] of Object.entries(extra)) params.set(key, String(value));
  const text = params.toString();
  return text ? `?${text}` : "";
}

type Load<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "error"; message: string };

const messageOf = (error: unknown) =>
  error instanceof ApiRequestError ? error.message : "Something went wrong while loading the audit trail.";

function useLoad<T>(path: string | null, version: number): Load<T> {
  const [result, setResult] = useState<Load<T>>({ state: "loading" });
  useEffect(() => {
    if (path === null) return;
    let live = true;
    setResult((current) => (current.state === "ready" ? current : { state: "loading" }));
    apiGet<T>(path)
      .then((data) => live && setResult({ state: "ready", data }))
      .catch((error: unknown) => live && setResult({ state: "error", message: messageOf(error) }));
    return () => {
      live = false;
    };
  }, [path, version]);
  return result;
}

export function useAuditTrail(query: AuditLogQuery, offset: number, limit: number = PAGE_SIZE) {
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((value) => value + 1), []);
  const midnight = startOfDay(new Date()).toISOString();
  const page = useLoad<AuditLogPage>(
    `/api/v1/audit-logs${queryString(query, { limit, offset })}`,
    version,
  );
  const summary = useLoad<AuditSummary>(`/api/v1/audit-logs/summary${queryString({}, { since: midnight })}`, version);
  const facets = useLoad<AuditFacets>("/api/v1/audit-logs/facets", version);
  const stores = useLoad<Store[]>("/api/v1/stores?limit=200", 0);
  return { page, summary, facets, stores, reload };
}

export function useAuditEntry(id: string | null) {
  return useLoad<AuditLogDetail>(id === null ? null : `/api/v1/audit-logs/${id}`, 0);
}

export async function downloadExport(query: AuditLogQuery, format: "csv" | "pdf"): Promise<void> {
  const blob = await apiBlob(`/api/v1/audit-logs/export${queryString(query, { format })}`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  link.href = url;
  link.download = `audit-trail-${stamp}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
