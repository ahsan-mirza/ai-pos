import { Permission, formatMoney } from "@ai-pos/shared-types";
import { AxizDatePicker, AxizTabs, useLocale } from "@ai-pos/ui";
import { useEffect, useMemo, useState } from "react";
import { BarSeries } from "../../components/charts/Charts";
import { env } from "../../config/env";
import { apiGet, getAccessToken } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { PortalSaleReturn } from "../returns/PortalSaleReturn";

type Preset = "Today" | "Yesterday" | "Last 7 days" | "Last 30 days" | "This month" | "Last month" | "Custom";
type Tab = "overview" | "products" | "staff" | "categories" | "payments" | "trends" | "transactions";

interface Summary {
  window: { start: string; end: string; timezone: string; currency: string };
  gross_sales_cents: number;
  discount_cents: number;
  tax_cents: number;
  charged_cents: number;
  refund_cents: number;
  net_sales_cents: number;
  transactions: number;
  items_sold: number;
  average_transaction_cents: number;
  average_items_per_transaction_bps: number;
  voided: number;
  compare: { net_sales_cents: number; transactions: number; net_change_bps: number | null };
}

interface ProductRow {
  product_id: string;
  name: string;
  sku: string;
  category: string;
  quantity: number;
  gross_cents: number;
  discount_cents: number;
  net_cents: number;
  transactions: number;
  contribution_bps: number;
  cost_cents?: number | null;
}

interface StaffRow {
  cashier_id: string | null;
  name: string;
  transactions: number;
  items_sold: number;
  gross_cents: number;
  discount_cents: number;
  net_cents: number;
  average_cents: number;
}

interface CategoryRow {
  category: string;
  quantity: number;
  net_cents: number;
  transactions: number;
  contribution_bps: number;
}

interface PaymentRow {
  method: string;
  amount_cents: number;
  transactions: number;
}

interface TrendRow {
  bucket: string;
  charged_cents: number;
  transactions: number;
}

interface ReceiptRow {
  id: string;
  invoice_number: string | null;
  created_at: string;
  cashier: string;
  items: number;
  gross_cents: number;
  discount_cents: number;
  net_cents: number;
  payment_method: string;
  status: string;
}

const PRESETS: Preset[] = ["Today", "Yesterday", "Last 7 days", "Last 30 days", "This month", "Last month", "Custom"];
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "products", label: "Products" },
  { id: "staff", label: "Staff" },
  { id: "categories", label: "Categories" },
  { id: "payments", label: "Payments" },
  { id: "trends", label: "Trends" },
  { id: "transactions", label: "Transactions" },
];

function utcDay(year: number, month: number, day: number): Date {
  return new Date(Date.UTC(year, month, day));
}

function period(preset: Preset, from: string, to: string): { start: Date; end: Date } | string {
  const now = new Date();
  const today = utcDay(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  if (preset === "Today") return { start: today, end: now };
  if (preset === "Yesterday") {
    const start = new Date(today);
    start.setUTCDate(start.getUTCDate() - 1);
    return { start, end: today };
  }
  if (preset === "Last 7 days" || preset === "Last 30 days") {
    const start = new Date(today);
    start.setUTCDate(start.getUTCDate() - (preset === "Last 7 days" ? 6 : 29));
    return { start, end: now };
  }
  if (preset === "This month") return { start: utcDay(now.getUTCFullYear(), now.getUTCMonth(), 1), end: now };
  if (preset === "Last month") {
    return {
      start: utcDay(now.getUTCFullYear(), now.getUTCMonth() - 1, 1),
      end: utcDay(now.getUTCFullYear(), now.getUTCMonth(), 1),
    };
  }
  if (from === "" || to === "") return "Choose a start date and an end date.";
  const start = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "Enter valid dates.";
  end.setUTCDate(end.getUTCDate() + 1);
  if (end <= start) return "The end date must be on or after the start date.";
  return { start, end };
}

function changeLabel(bps: number | null): string | null {
  if (bps === null) return null;
  const value = bps / 100;
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}% vs previous period`;
}

export function SalesInsightsPage() {
  const { t } = useLocale();
  const [preset, setPreset] = useState<Preset>("Today");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [applied, setApplied] = useState(0);
  const [tab, setTab] = useState<Tab>("overview");
  const [cashier, setCashier] = useState("");
  const [category, setCategory] = useState("");
  const [method, setMethod] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [receipt, setReceipt] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [staff, setStaff] = useState<StaffRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [trends, setTrends] = useState<TrendRow[]>([]);
  const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<ProductRow | null>(null);
  const [selectedStaff, setSelectedStaff] = useState<StaffRow | null>(null);
  const [returning, setReturning] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const bump = () => setRevision((value) => value + 1);
    window.addEventListener("portal-sale-return", bump);
    return () => window.removeEventListener("portal-sale-return", bump);
  }, []);
  const { user, can } = useAuth();
  const canReturn = can(Permission.PosRefund);

  const bounds = useMemo(() => period(preset, from, to), [preset, from, to, applied]);
  const rangeError = typeof bounds === "string" ? bounds : null;

  const search = useMemo(() => {
    if (typeof bounds === "string") return "";
    const params = new URLSearchParams();
    params.set("start", bounds.start.toISOString());
    params.set("end", bounds.end.toISOString());
    if (cashier) params.set("cashier_id", cashier);
    if (category.trim()) params.set("category", category.trim());
    if (method) params.set("method", method);
    if (status) params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    return params.toString();
  }, [bounds, cashier, category, method, status, query]);

  useEffect(() => {
    if (search === "") {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const load = async () => {
      const summaryPath = `/api/v1/sales-insights/summary?${search}`;
      const nextSummary = await apiGet<Summary>(summaryPath);
      if (controller.signal.aborted) return;
      setSummary(nextSummary);
      if (tab === "products" || tab === "overview") setProducts(await apiGet<ProductRow[]>(`/api/v1/sales-insights/products?${search}`));
      setStaff(await apiGet<StaffRow[]>(`/api/v1/sales-insights/staff?${search}`));
      if (tab === "categories" || tab === "overview") setCategories(await apiGet<CategoryRow[]>(`/api/v1/sales-insights/categories?${search}`));
      if (tab === "payments" || tab === "overview") setPayments(await apiGet<PaymentRow[]>(`/api/v1/sales-insights/payments?${search}`));
      if (tab === "trends" || tab === "overview") setTrends(await apiGet<TrendRow[]>(`/api/v1/sales-insights/trends?${search}&bucket=day`));
      if (tab === "transactions") {
        const extra = receipt.trim() ? `&receipt=${encodeURIComponent(receipt.trim())}` : "";
        setReceipts(await apiGet<ReceiptRow[]>(`/api/v1/sales-insights/transactions?${search}${extra}`));
      }
    };
    load()
      .catch(() => {
        if (!controller.signal.aborted) setError("Sales could not be loaded.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [search, tab, receipt, applied, revision]);

  const currency = summary?.window.currency ?? "USD";
  const money = (cents: number) => formatMoney(cents, currency);
  const comparison = changeLabel(summary?.compare.net_change_bps ?? null);

  async function exportReport() {
    const report = tab === "staff" ? "staff" : tab === "categories" ? "categories" : tab === "payments" ? "payments" : tab === "transactions" ? "transactions" : "products";
    if (search === "") return;
    setExporting(true);
    setError(null);
    try {
      const headers: Record<string, string> = {};
      const token = getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(`${env.apiBaseUrl}/api/v1/sales-insights/export.csv?report=${report}&${search}`, { headers });
      if (!response.ok) throw new Error("export");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `sales-${report}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("The report file could not be created.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="font-sans text-2xl font-semibold tracking-tight md:text-[28px]">{t("Sales Insights")}</h2>
          <p className="mt-1 text-sm text-charcoal/60">
            {t("Understand your store sales, product performance and staff productivity.")}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-[38px] items-center justify-center rounded-full bg-charcoal px-4 text-sm font-medium text-white disabled:opacity-50"
          disabled={exporting || rangeError !== null}
          onClick={() => void exportReport()}
        >
          {exporting ? t("Preparing file…") : t("Export CSV")}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-2xl border border-line bg-white p-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
          {t("Period")}
          <select className="h-[38px] rounded-xl border border-line bg-white px-3 text-sm" value={preset} onChange={(event) => setPreset(event.target.value as Preset)}>
            {PRESETS.map((item) => (
              <option key={item} value={item}>{t(item)}</option>
            ))}
          </select>
        </label>
        {preset === "Custom" ? (
          <>
            <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
              {t("From")}
              <AxizDatePicker variant="compact" leading aria-label={t("From")} value={from} onChange={(event) => setFrom(event.target.value)} className="h-[38px] w-full rounded-xl border border-line bg-white text-sm" />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
              {t("To")}
              <AxizDatePicker variant="compact" leading aria-label={t("To")} value={to} onChange={(event) => setTo(event.target.value)} className="h-[38px] w-full rounded-xl border border-line bg-white text-sm" />
              {rangeError ? <span className="text-xs font-normal text-red-700">{t(rangeError)}</span> : null}
            </label>
          </>
        ) : null}
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
          {t("Staff")}
          <select className="h-[38px] rounded-xl border border-line bg-white px-3 text-sm" value={cashier} onChange={(event) => setCashier(event.target.value)}>
            <option value="">{t("All staff")}</option>
            {staff.filter((row) => row.cashier_id).map((row) => (
              <option key={row.cashier_id} value={row.cashier_id ?? ""}>{row.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
          {t("Category")}
          <input className="h-[38px] rounded-xl border border-line px-3 text-sm" value={category} onChange={(event) => setCategory(event.target.value)} placeholder={t("All categories")} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
          {t("Payment")}
          <select className="h-[38px] rounded-xl border border-line bg-white px-3 text-sm" value={method} onChange={(event) => setMethod(event.target.value)}>
            <option value="">{t("All methods")}</option>
            {["cash", "card", "transfer", "store_credit", "on_account", "cheque", "qr", "loyalty", "gift_card"].map((item) => (
              <option key={item} value={item}>{item.replaceAll("_", " ")}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70">
          {t("Status")}
          <select className="h-[38px] rounded-xl border border-line bg-white px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">{t("Completed sales")}</option>
            <option value="completed">completed</option>
            <option value="partially_refunded">partially refunded</option>
            <option value="refunded">refunded</option>
            <option value="voided">voided</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-charcoal/70 sm:col-span-2">
          {t("Product")}
          <input className="h-[38px] rounded-xl border border-line px-3 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("Name or SKU")} />
        </label>
        <div className="flex items-end">
          <button type="button" className="inline-flex h-[38px] items-center rounded-full border border-line px-4 text-sm" onClick={() => setApplied((value) => value + 1)}>
            {t("Refresh")}
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-700">{t(error)}</p> : null}
      {summary ? (
        <p className="text-xs text-charcoal/50">
          {t("Reporting period")} {new Date(summary.window.start).toISOString().slice(0, 16).replace("T", " ")} – {new Date(summary.window.end).toISOString().slice(0, 16).replace("T", " ")} {summary.window.timezone}
          {comparison ? ` · ${comparison}` : ` · ${t("No earlier sales to compare.")}`}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Kpi label={t("Total sales")} value={summary ? money(summary.charged_cents) : "—"} hint={t("Amount charged on completed receipts, tax included.")} loading={loading} />
        <Kpi label={t("Net sales")} value={summary ? money(summary.net_sales_cents) : "—"} hint={t("Charged sales minus refunds recorded in this period.")} loading={loading} />
        <Kpi label={t("Transactions")} value={summary ? String(summary.transactions) : "—"} hint={t("Completed, partially refunded, and refunded receipts. Voided receipts are excluded.")} loading={loading} />
        <Kpi label={t("Items sold")} value={summary ? String(summary.items_sold) : "—"} hint={t("Quantities on those receipts.")} loading={loading} />
        <Kpi label={t("Average sale")} value={summary ? money(summary.average_transaction_cents) : "—"} hint={t("Charged total divided by the number of receipts.")} loading={loading} />
        <Kpi label={t("Items / sale")} value={summary ? (summary.average_items_per_transaction_bps / 100).toFixed(2) : "—"} hint={t("Items sold divided by receipts.")} loading={loading} />
        <Kpi label={t("Discounts")} value={summary ? money(summary.discount_cents) : "—"} hint={t("Promotion and cashier discounts stored on each line.")} loading={loading} />
        <Kpi label={t("Refunds")} value={summary ? money(summary.refund_cents) : "—"} hint={t("Refunds posted in this period. They are not also removed from the average sale.")} loading={loading} />
      </div>

      <AxizTabs
        ariaLabel={t("Sales insights")}
        activeTab={tab}
        onChange={(id) => setTab(id as Tab)}
        tabs={TABS.map((item) => ({ id: item.id, label: t(item.label) }))}
      />

      {loading && summary === null ? <div className="h-40 animate-pulse rounded-2xl bg-charcoal/5" /> : null}

      {tab === "overview" && summary ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border border-line bg-white p-4">
            <h3 className="text-sm font-medium text-charcoal/70">{t("Daily charged sales")}</h3>
            {trends.length > 0 ? <BarSeries values={trends.map((row) => row.charged_cents)} /> : <p className="mt-4 text-sm text-charcoal/50">{t("No completed sales in this period.")}</p>}
          </article>
          <article className="rounded-2xl border border-line bg-white p-4">
            <h3 className="text-sm font-medium text-charcoal/70">{t("Also in this period")}</h3>
            <ul className="mt-3 space-y-2 text-sm">
              <li>{t("Gross sales")} {money(summary.gross_sales_cents)}</li>
              <li>{t("Tax collected")} {money(summary.tax_cents)}</li>
              <li>{t("Voided receipts")} {summary.voided}</li>
            </ul>
          </article>
        </div>
      ) : null}

      {tab === "products" ? (
        <Table
          empty={t("No products were sold in this period.")}
          headers={[t("Product"), t("SKU"), t("Category"), t("Qty"), t("Gross"), t("Discounts"), t("Net"), t("Receipts")]}
          rows={products.map((row) => [
            row.name, row.sku, row.category, String(row.quantity), money(row.gross_cents), money(row.discount_cents), money(row.net_cents), String(row.transactions),
          ])}
          onRow={(index) => setSelectedProduct(products[index] ?? null)}
        />
      ) : null}
      {tab === "staff" ? (
        <Table
          empty={t("No staff sales in this period.")}
          headers={[t("Staff"), t("Receipts"), t("Items"), t("Gross"), t("Discounts"), t("Net"), t("Average")]}
          rows={staff.map((row) => [row.name, String(row.transactions), String(row.items_sold), money(row.gross_cents), money(row.discount_cents), money(row.net_cents), money(row.average_cents)])}
          onRow={(index) => setSelectedStaff(staff[index] ?? null)}
        />
      ) : null}
      {tab === "categories" ? (
        <Table
          empty={t("No category sales in this period.")}
          headers={[t("Category"), t("Qty"), t("Net"), t("Receipts"), t("Share")]}
          rows={categories.map((row) => [row.category, String(row.quantity), money(row.net_cents), String(row.transactions), `${(row.contribution_bps / 100).toFixed(1)}%`])}
        />
      ) : null}
      {tab === "payments" ? (
        <Table
          empty={t("No payments in this period.")}
          headers={[t("Method"), t("Amount"), t("Receipts")]}
          rows={payments.map((row) => [row.method, money(row.amount_cents), String(row.transactions)])}
        />
      ) : null}
      {tab === "trends" ? (
        <article className="rounded-2xl border border-line bg-white p-4">
          {trends.length > 0 ? <BarSeries values={trends.map((row) => row.charged_cents)} /> : <p className="text-sm text-charcoal/50">{t("No completed sales in this period.")}</p>}
          <ul className="mt-3 space-y-1 text-sm">
            {trends.map((row) => (
              <li key={row.bucket} className="flex justify-between gap-3"><span>{row.bucket}</span><span className="tabular-nums">{money(row.charged_cents)} · {row.transactions}</span></li>
            ))}
          </ul>
        </article>
      ) : null}
      {tab === "transactions" ? (
        <div className="space-y-3">
          <label className="flex max-w-sm flex-col gap-1 text-xs font-medium text-charcoal/70">
            {t("Receipt")}
            <input className="h-[38px] rounded-xl border border-line px-3 text-sm" value={receipt} onChange={(event) => setReceipt(event.target.value)} placeholder={t("Receipt number")} />
          </label>
          <Table
            empty={t("No receipts in this period.")}
            headers={[t("Receipt"), t("When"), t("Cashier"), t("Items"), t("Gross"), t("Discount"), t("Net"), t("Payment"), t("Status"), ""]}
            rows={receipts.map((row) => [
              row.invoice_number ?? row.id.slice(0, 8),
              row.created_at.slice(0, 16).replace("T", " "),
              row.cashier,
              String(row.items),
              money(row.gross_cents),
              money(row.discount_cents),
              money(row.net_cents),
              row.payment_method,
              row.status,
              canReturn && row.invoice_number && (row.status === "completed" || row.status === "partially_refunded") ? row.invoice_number : "",
            ])}
            actionLabel="Return"
            onAction={(invoice) => setReturning(invoice)}
          />
        </div>
      ) : null}

      {selectedProduct ? (
        <aside className="rounded-2xl border border-line bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-medium">{selectedProduct.name}</h3>
              <p className="text-sm text-charcoal/60">{selectedProduct.sku} · {selectedProduct.category}</p>
            </div>
            <button type="button" className="text-sm" onClick={() => setSelectedProduct(null)}>{t("Close")}</button>
          </div>
          <p className="mt-3 text-sm">{t("Sold")} {selectedProduct.quantity} · {money(selectedProduct.net_cents)} · {selectedProduct.transactions} {t("receipts")}</p>
          {selectedProduct.cost_cents != null ? <p className="mt-1 text-sm">{t("Recorded cost")} {money(selectedProduct.cost_cents)}</p> : null}
        </aside>
      ) : null}
      {returning && user ? (
        <PortalSaleReturn
          user={user}
          invoice={returning}
          onClose={() => setReturning(null)}
          onReturned={() => setRevision((value) => value + 1)}
        />
      ) : null}
      {selectedStaff ? (
        <aside className="rounded-2xl border border-line bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-medium">{selectedStaff.name}</h3>
            <button type="button" className="text-sm" onClick={() => setSelectedStaff(null)}>{t("Close")}</button>
          </div>
          <p className="mt-3 text-sm">{selectedStaff.transactions} {t("receipts")} · {money(selectedStaff.net_cents)} · {t("average")} {money(selectedStaff.average_cents)}</p>
        </aside>
      ) : null}
    </section>
  );
}

function Kpi({ label, value, hint, loading }: { label: string; value: string; hint: string; loading: boolean }) {
  return (
    <article className="rounded-2xl border border-line bg-white p-3" title={hint}>
      <p className="text-xs text-charcoal/60">{label}</p>
      <p className={`mt-2 truncate font-sans text-lg font-semibold tabular-nums ${loading ? "opacity-40" : ""}`}>{value}</p>
    </article>
  );
}

function Table({
  headers,
  rows,
  empty,
  onRow,
  actionLabel,
  onAction,
}: {
  headers: string[];
  rows: string[][];
  empty: string;
  onRow?: (index: number) => void;
  actionLabel?: string;
  onAction?: (value: string) => void;
}) {
  if (rows.length === 0) return <p className="text-sm text-charcoal/50">{empty}</p>;
  const actionIndex = onAction ? headers.length - 1 : -1;
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-white">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs text-charcoal/60">
          <tr>{headers.map((header) => <th key={header || "action"} className="px-3 py-2 font-medium">{header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row[0]}-${index}`} className={onRow ? "cursor-pointer hover:bg-charcoal/5" : undefined} onClick={() => onRow?.(index)}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="whitespace-nowrap px-3 py-2 tabular-nums">
                  {cellIndex === actionIndex && cell !== "" && onAction && actionLabel ? (
                    <button
                      type="button"
                      className="rounded-full border border-line px-3 py-1 text-xs font-semibold"
                      onClick={(event) => {
                        event.stopPropagation();
                        onAction(cell);
                      }}
                    >
                      {actionLabel}
                    </button>
                  ) : cellIndex === actionIndex ? null : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
