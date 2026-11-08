import { formatMoney } from "@ai-pos/shared-types";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Image, View } from "react-native";
import { apiGetRaw } from "@/api/client";
import { readCache, writeCache } from "@/api/cache";
import { isOfflineError } from "@/api/errors";
import { ListCard, SummaryCard } from "@/components/cards/Cards";
import { Avatar } from "@/components/feedback/Feedback";
import { SearchInput, SelectField, DateField } from "@/components/inputs/Fields";
import { VirtualizedList } from "@/components/lists/VirtualizedList";
import { Button } from "@/components/buttons/Button";
import { StatusBadge } from "@/components/feedback/Feedback";
import { useNetwork } from "@/hooks/useNetwork";
import { useI18n } from "@/i18n/I18nProvider";
import { collectRows, defaultRange, labelize, recordId, recordSubtitle, recordTitle, unwrapProductHits, type CollectedRows } from "@/modules/records";
import type { PortalModule } from "@/modules/catalog";
import { useTenant } from "@/tenant/TenantProvider";

const PAGE = 40;

const STOCK_STATUS = ["", "ok", "low", "out", "over", "unavailable"] as const;

type Page = CollectedRows & { stale: boolean; savedAt: string | null };

function buildPath(
  module: PortalModule,
  offset: number,
  search: string,
  range: { from: string; to: string },
  currency: string,
  status: string,
): string {
  const base = module.path ?? "";
  const [path, existing] = base.split("?");
  const params = new URLSearchParams(existing ?? "");
  if (module.paginated) {
    params.set("offset", String(offset));
    params.set("limit", String(PAGE));
  } else if (!params.has("limit")) {
    params.set("limit", "100");
  }
  if (search.trim() !== "") params.set("q", search.trim());
  if (module.statusFilter && status !== "") params.set("status", status);
  if (module.dated) {
    params.set("from", range.from);
    params.set("to", range.to);
  }
  if (base?.includes("analytics/summary") || base?.includes("deep-analytics")) params.set("currency", currency);
  const query = params.toString();
  return query === "" ? (path ?? base) : `${path}?${query}`;
}

function productLookupPath(search: string, storeId: string | null): string {
  const params = new URLSearchParams({ q: search.trim(), limit: String(PAGE) });
  if (storeId) params.set("store_id", storeId);
  return `/api/v1/products/search?${params.toString()}`;
}

function moneyField(row: Record<string, unknown>, currency: string, locale: string): string | undefined {
  for (const key of ["total_cents", "price_cents", "amount_cents", "balance_cents", "current_balance_cents", "net_revenue_cents", "total_cost_cents"]) {
    const value = row[key];
    if (typeof value === "number") return formatMoney(value, currency, locale);
  }
  return undefined;
}

function savedLabel(savedAt: string | null, locale: string, cached: string): string {
  if (!savedAt) return cached;
  const date = new Date(savedAt);
  if (Number.isNaN(date.getTime())) return cached;
  return `${cached} · ${date.toLocaleString(locale === "ar" ? "ar" : "en")}`;
}

export function RecordBrowser(props: { module: PortalModule; onOpen: (id: string, row: Record<string, unknown>) => void; headerExtra?: ReactNode }) {
  const { text, t, locale } = useI18n();
  const tenant = useTenant();
  const network = useNetwork();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [range, setRange] = useState(defaultRange);
  const [submitted, setSubmitted] = useState({ search: "", range, status: "" });
  const wasOffline = useRef(false);
  const query = useInfiniteQuery({
    queryKey: ["records", props.module.id, submitted, tenant.currency, tenant.storeId],
    initialPageParam: 0,
    queryFn: async ({ pageParam, signal }) => {
      const lookup = props.module.lookup === "product" && submitted.search.trim() !== "";
      const path = lookup
        ? productLookupPath(submitted.search, tenant.storeId)
        : buildPath(props.module, pageParam, submitted.search, submitted.range, tenant.currency, submitted.status);
      try {
        const raw = await apiGetRaw(path, signal);
        const collected = lookup ? unwrapProductHits(raw.data) : collectRows(raw.data, raw.total);
        const page: Page = { ...collected, stale: false, savedAt: new Date().toISOString() };
        if (props.module.offline === "cache") await writeCache(`${props.module.id}:${path}`, collected);
        return page;
      } catch (error) {
        if (props.module.offline === "cache" && isOfflineError(error)) {
          const cached = await readCache<CollectedRows>(`${props.module.id}:${path}`);
          if (cached) return { ...cached.value, stale: true, savedAt: cached.savedAt || null } satisfies Page;
        }
        throw error;
      }
    },
    getNextPageParam: (last, _pages, lastParam) => {
      if (!props.module.paginated) return undefined;
      if (props.module.lookup === "product" && submitted.search.trim() !== "") return undefined;
      const next = lastParam + last.rows.length;
      if (last.rows.length < PAGE) return undefined;
      if (last.total !== null && next >= last.total) return undefined;
      return next;
    },
  });
  useEffect(() => {
    if (!network.online) {
      wasOffline.current = true;
      return;
    }
    if (wasOffline.current) {
      wasOffline.current = false;
      void query.refetch();
    }
  }, [network.online, query.refetch]);
  const pages = query.data?.pages ?? [];
  const rows = pages.flatMap((page) => page.rows);
  const stale = pages.some((page) => page.stale) || !network.online;
  const savedAt = pages.find((page) => page.savedAt)?.savedAt ?? null;
  const summary = pages[0]?.summary;
  const localeTag = locale === "ar" ? "ar" : "en";
  const summaryLines = summary
    ? Object.entries(summary)
        .filter((entry): entry is [string, string | number | boolean] => ["string", "number", "boolean"].includes(typeof entry[1]))
        .slice(0, 4)
        .map(([key, value]) => ({
          label: labelize(key),
          value: key.endsWith("_cents") && typeof value === "number" ? formatMoney(value, tenant.currency, localeTag) : String(value),
        }))
    : [];
  return (
    <VirtualizedList
      data={rows}
      keyExtractor={(item, index) => recordId(item, index)}
      loading={query.isLoading}
      loadingMore={query.isFetchingNextPage}
      refreshing={query.isRefetching && !query.isLoading}
      onRefresh={() => void query.refetch()}
      onEndReached={() => {
        if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage();
      }}
      error={query.isError ? (query.error instanceof Error ? query.error.message : t("retry")) : null}
      onRetry={() => void query.refetch()}
      header={
        <View style={{ gap: 12 }}>
          <SearchInput value={search} onChangeText={setSearch} placeholder={t("search")} accessibilityLabel={t("search")} />
          {props.module.dated ? (
            <View style={{ gap: 8 }}>
              <DateField label={t("from")} value={range.from} onChange={(from) => setRange((current) => ({ ...current, from }))} />
              <DateField label={t("to")} value={range.to} onChange={(to) => setRange((current) => ({ ...current, to }))} />
            </View>
          ) : null}
          {props.module.statusFilter ? (
            <SelectField
              label={t("filter")}
              value={status}
              onChange={setStatus}
              options={STOCK_STATUS.map((value) => ({ value, label: value === "" ? t("allStatuses") : value }))}
            />
          ) : null}
          <Button label={t("apply")} accessibilityLabel={t("apply")} onPress={() => setSubmitted({ search, range, status })} />
          {props.headerExtra}
          {stale && rows.length > 0 ? <StatusBadge tone="warning" label={savedLabel(savedAt, locale, pages.some((page) => page.stale) ? t("cached") : t("offline"))} /> : null}
          {summaryLines.length > 0 ? <SummaryCard title={text(props.module.title)} lines={summaryLines} /> : null}
        </View>
      }
      renderItem={(item) => {
        const title = recordTitle(item);
        const statusLabel = typeof item.status === "string" ? item.status : typeof item.is_active === "boolean" ? (item.is_active ? "Active" : "Inactive") : undefined;
        const extras: string[] = [];
        if (item.sold_by_weight === true) extras.push(t("weighed"));
        if (typeof item.plu_code === "string" && item.plu_code !== "") extras.push(`${t("plu")} ${item.plu_code}`);
        const subtitle = [recordSubtitle(item, title), ...extras].filter((part) => part !== "").join(" · ");
        const thumb = typeof item.thumb_url === "string" && item.thumb_url.startsWith("http") ? item.thumb_url : null;
        const leading = props.module.id === "customers" ? <Avatar name={title} /> : thumb ? <Image source={{ uri: thumb }} style={{ width: 44, height: 44, borderRadius: 10 }} accessibilityIgnoresInvertColors /> : undefined;
        return (
          <ListCard
            title={title}
            subtitle={subtitle}
            amount={moneyField(item, tenant.currency, localeTag)}
            status={statusLabel}
            leading={leading}
            onPress={() => props.onOpen(recordId(item, 0), item)}
          />
        );
      }}
    />
  );
}
