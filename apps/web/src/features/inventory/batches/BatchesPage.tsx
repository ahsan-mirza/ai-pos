import {
  BATCH_STATUS_LABELS,
  BatchStatus,
  IMPORT_SOURCE_LABELS,
  Permission,
  formatMoney,
  type BatchDetail,
  type BatchPage,
  type BatchRow,
  type RollbackResult,
  type Supplier,
} from "@ai-pos/shared-types";
import {
  CircleDollarSign,
  FileSpreadsheet,
  FileText,
  Layers,
  PackagePlus,
  Search,
  TrendingUp,
  Upload,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { StoreSwitcher } from "../../../components/layout/StoreSwitcher";
import { DataTable, usePagination, type DataTableColumn } from "../../../components/ui/DataTable";
import { ErrorNote } from "../../../components/ui/Field";
import { Select } from "../../../components/ui/Select";
import { useAuth } from "../../../lib/auth";
import { useCurrency } from "../../../lib/currency";
import { useStoreScope } from "../../../lib/storeScope";
import { message } from "../api";
import { batchesApi, importApi } from "../import/api";
import { ImportWizardModal } from "../import/ImportWizardModal";
import { BatchDrawer } from "./BatchDrawer";
import { BatchStatusBadge, SoldMeter, formatDay, formatTime } from "./BatchParts";

function Kpi({
  label,
  value,
  hint,
  icon: Icon,
  tone = "plain",
  loading,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  tone?: "plain" | "good" | "bad";
  loading: boolean;
}) {
  return (
    <div className="min-w-0 bg-white px-4 py-4 lg:px-6">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium text-charcoal/55">{label}</span>
        <Icon size={16} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-charcoal/30" />
      </div>
      {loading ? (
        <div className="mt-2.5 h-7 w-28 animate-pulse rounded-md bg-charcoal/[0.06]" />
      ) : (
        <div
          className={`mt-1.5 truncate text-[22px] font-semibold tabular-nums tracking-tight ${
            tone === "good" ? "text-emerald-600" : tone === "bad" ? "text-red-600" : ""
          }`}
        >
          {value}
        </div>
      )}
      {hint ? <div className="mt-0.5 truncate text-xs text-charcoal/45">{hint}</div> : null}
    </div>
  );
}

function SourceIcon({ row }: { row: BatchRow }) {
  const Icon = row.import_source === "PDF_INVOICE" ? FileText : FileSpreadsheet;
  return <Icon size={13} className="shrink-0 text-charcoal/35" aria-hidden="true" />;
}

export function BatchesPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const canImport = can(Permission.PortalInventoryManage);
  const { storeId, stores } = useStoreScope();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState<BatchStatus | "">("");
  const [supplierId, setSupplierId] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const pager = usePagination({ resetKeys: [storeId, status, supplierId, debounced] });
  const [page, setPage] = useState<BatchPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [wizard, setWizard] = useState(false);
  const [closing, setClosing] = useState(false);
  const closeTimer = useRef<number | undefined>(undefined);
  const selectedId = params.get("batch");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    importApi
      .suppliers()
      .then(setSuppliers)
      .catch(() => setSuppliers([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPage(
        await batchesApi.list({
          store_id: storeId ?? undefined,
          status: status || undefined,
          supplier_id: supplierId || undefined,
          q: debounced.trim() || undefined,
          offset: pager.offset,
          limit: pager.pageSize,
        }),
      );
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load purchase batches."));
    } finally {
      setLoading(false);
    }
  }, [storeId, status, supplierId, debounced, pager.offset, pager.pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  const select = (id: string | null) => {
    window.clearTimeout(closeTimer.current);
    setClosing(false);
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (id) next.set("batch", id);
        else next.delete("batch");
        return next;
      },
      { replace: true },
    );
  };

  const closeDrawer = useCallback(() => {
    setClosing(true);
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      setClosing(false);
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("batch");
          return next;
        },
        { replace: true },
      );
    }, 200);
  }, [setParams]);

  const onRolledBack = (result: RollbackResult) => {
    setNotice(
      result.status === "DELETED"
        ? `${result.batch_number} was deleted and ${result.units_removed} units were removed from stock.`
        : `${result.batch_number} was reversed. ${result.units_removed} units were pulled back; sold records are locked.`,
    );
    if (result.status === "DELETED") closeDrawer();
    void load();
  };

  const onCommitted = (batch: BatchDetail) => {
    setNotice(`${batch.batch_number} committed: ${batch.total_items_count} units at ${batch.store_code}.`);
    void load();
  };

  const open = selectedId !== null && !closing;
  const totals = page?.totals;
  const firstLoad = loading && page === null;
  const hide = open ? "lg:hidden 2xl:table-cell" : "";
  const scopeStore = stores.find((store) => store.id === storeId);
  const filtered = status !== "" || supplierId !== "" || debounced.trim() !== "";
  const profit = totals?.realized_profit_cents ?? 0;

  const columns: DataTableColumn<BatchRow>[] = [
    {
      id: "batch",
      header: "Batch",
      cell: (row) => {
        const active = row.id === selectedId && !closing;
        return (
          <>
            <button
              type="button"
              onClick={() => (active ? closeDrawer() : select(row.id))}
              aria-expanded={active}
              className={`block whitespace-nowrap rounded font-mono text-[13px] font-semibold outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                active ? "text-accent" : "group-hover:text-accent"
              } ${row.status === "REVERSED" ? "line-through decoration-charcoal/30" : ""}`}
            >
              {row.batch_number}
            </button>
            <span className="mt-0.5 flex items-center gap-1.5 text-xs text-charcoal/50">
              <SourceIcon row={row} />
              <span className="max-w-[220px] truncate">
                {row.supplier_name ?? row.file_name ?? IMPORT_SOURCE_LABELS[row.import_source]}
              </span>
              {open ? (
                <span className="hidden whitespace-nowrap lg:inline 2xl:hidden">
                  · {row.store_code} · {formatDay(row.created_at)}
                </span>
              ) : null}
            </span>
          </>
        );
      },
    },
    {
      id: "store",
      header: "Store",
      className: hide,
      cell: (row) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <span className="rounded bg-charcoal/[0.06] px-1.5 py-0.5 font-mono text-[11px] font-semibold text-charcoal/75">
            {row.store_code}
          </span>
          <span className="max-w-[160px] truncate text-charcoal/60">{row.store_name}</span>
        </span>
      ),
    },
    {
      id: "imported",
      header: "Imported",
      className: `whitespace-nowrap ${hide}`,
      cell: (row) => (
        <>
          {formatDay(row.created_at)}
          <span className="block text-xs text-charcoal/45">{formatTime(row.created_at)}</span>
        </>
      ),
    },
    {
      id: "items",
      header: "Items",
      align: "right",
      cell: (row) => (
        <>
          <span className="font-semibold">{row.total_items_count.toLocaleString()}</span>
          <span className="block text-xs text-charcoal/45">
            {row.line_count} line{row.line_count === 1 ? "" : "s"}
          </span>
        </>
      ),
    },
    {
      id: "cost",
      header: "Total cost",
      align: "right",
      className: "whitespace-nowrap font-semibold",
      cell: (row) => formatMoney(row.total_cost_amount, row.currency),
    },
    {
      id: "fifo",
      header: "FIFO sell-through",
      className: hide,
      cell: (row) => (
        <SoldMeter
          percent={row.sold_percent}
          reversed={row.status === "REVERSED"}
          label={`${row.units_sold} of ${row.total_items_count} units sold`}
        />
      ),
    },
    {
      id: "profit",
      header: "Profit",
      align: "right",
      className: `whitespace-nowrap font-semibold ${hide}`,
      cell: (row) => (
        <span
          className={
            row.realized_profit_cents < 0 ? "text-red-600" : row.realized_profit_cents > 0 ? "text-emerald-600" : ""
          }
        >
          {row.units_sold ? formatMoney(row.realized_profit_cents, row.currency) : "—"}
        </span>
      ),
    },
    { id: "status", header: "Status", cell: (row) => <BatchStatusBadge status={row.status} /> },
  ];

  return (
    <div className="lg:flex lg:h-full lg:min-h-0">
      <section aria-label="Purchase batches" className="flex min-w-0 flex-1 flex-col lg:min-h-0">
        <div
          className={`grid shrink-0 gap-px border-b border-line bg-line ${
            open ? "grid-cols-2 2xl:grid-cols-4" : "grid-cols-2 xl:grid-cols-4"
          }`}
        >
          <Kpi
            label="Total batches"
            icon={Layers}
            loading={firstLoad}
            value={(totals?.batches ?? 0).toLocaleString()}
            hint={filtered ? "Matching the filters" : scopeStore ? `At ${scopeStore.code}` : "All stores"}
          />
          <Kpi
            label="Units imported"
            icon={PackagePlus}
            loading={firstLoad}
            value={(totals?.units ?? 0).toLocaleString()}
            hint={totals ? `${formatMoney(totals.cost_cents, currency)} at cost` : undefined}
          />
          <Kpi
            label="Stock value on hand"
            icon={Warehouse}
            loading={firstLoad}
            value={formatMoney(totals?.remaining_cost_cents ?? 0, currency)}
            hint="Remaining units at batch cost"
          />
          <Kpi
            label="Realized profit"
            icon={profit < 0 ? CircleDollarSign : TrendingUp}
            loading={firstLoad}
            tone={profit > 0 ? "good" : profit < 0 ? "bad" : "plain"}
            value={formatMoney(profit, currency)}
            hint="Sales minus FIFO cost"
          />
        </div>

        <div className="shrink-0 border-b border-line bg-white px-4 py-3 lg:px-6">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="mr-auto min-w-0">
              <h1 className="flex items-center gap-2 text-[15px] font-semibold">
                Purchase batches
                {page ? (
                  <span className="rounded-md bg-charcoal/[0.06] px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-charcoal/60">
                    {page.total.toLocaleString()}
                  </span>
                ) : null}
              </h1>
              <p className="mt-0.5 hidden text-xs text-charcoal/50 sm:block">
                Every import is a cost-tracked batch. Sales draw from the oldest batch first (FIFO).
              </p>
            </div>
            {canImport ? (
              <button
                type="button"
                onClick={() => setWizard(true)}
                className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-accent px-3.5 text-[13px] font-semibold text-white shadow-sm shadow-accent/25 outline-none transition-colors hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2"
              >
                <Upload size={15} aria-hidden="true" /> Import purchases
              </button>
            ) : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="relative min-w-[200px] flex-1 sm:max-w-xs">
              <span className="sr-only">Search batches</span>
              <Search
                size={15}
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-charcoal/40"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Batch number or file name"
                className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] transition-colors placeholder:text-charcoal/40 hover:border-gray-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
            </label>
            <StoreSwitcher className="!w-full sm:!w-[220px] md:hidden" />
            <Select
              aria-label="Status"
              size="sm"
              className="!w-[calc(50%-0.25rem)] sm:!w-[170px]"
              value={status}
              options={[
                { value: "", label: "All statuses" },
                ...Object.values(BatchStatus).map((value) => ({ value, label: BATCH_STATUS_LABELS[value] })),
              ]}
              onChange={(next) => setStatus(next as BatchStatus | "")}
            />
            <Select
              aria-label="Supplier"
              size="sm"
              className="!w-[calc(50%-0.25rem)] sm:!w-[190px]"
              value={supplierId}
              options={[
                { value: "", label: "All suppliers" },
                ...suppliers.map((supplier) => ({ value: supplier.id, label: supplier.name })),
              ]}
              onChange={setSupplierId}
            />
            {filtered ? (
              <button
                type="button"
                onClick={() => {
                  setStatus("");
                  setSupplierId("");
                  setQuery("");
                }}
                className="inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-[13px] font-medium text-charcoal/60 hover:bg-charcoal/[0.05] hover:text-charcoal"
              >
                <X size={14} aria-hidden="true" /> Clear
              </button>
            ) : null}
          </div>

          {notice ? (
            <p
              role="status"
              className="mt-3 flex items-start justify-between gap-3 rounded-lg border border-line bg-[#f8fafc] px-3 py-2 text-[13px] text-charcoal/80"
            >
              {notice}
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setNotice(null)}
                className="shrink-0 text-charcoal/40 hover:text-charcoal"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </p>
          ) : null}
          {error ? (
            <div className="[&>p]:mt-3 [&>p]:rounded-lg [&>p]:py-2 [&>p]:text-[13px]">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>

        <DataTable
          aria-label="Purchase batches"
          variant="flush"
          stickyHeader
          className="lg:min-h-0 lg:flex-1"
          minWidth={open ? undefined : "880px"}
          columns={columns}
          data={page?.rows ?? []}
          getRowId={(row) => row.id}
          isLoading={firstLoad}
          isFetching={loading && page !== null}
          onRowClick={(row) => (row.id === selectedId && !closing ? closeDrawer() : select(row.id))}
          isRowActive={(row) => row.id === selectedId && !closing}
          rowClassName={(row) => `group ${row.status === "REVERSED" ? "text-charcoal/55" : ""}`}
          emptyState={{
            icon: Layers,
            title: filtered ? "No batches match these filters" : "No purchase batches yet",
            description: filtered
              ? "Try a different status, supplier or search."
              : "Import an Excel, CSV or PDF invoice to create the first cost-tracked batch.",
          }}
          pagination={{
            mode: "server",
            currentPage: pager.page,
            pageSize: pager.pageSize,
            totalRecords: page?.total ?? 0,
            onPageChange: pager.setPage,
            onPageSizeChange: pager.setPageSize,
          }}
        />
      </section>

      {selectedId ? (
        <BatchDrawer
          key={selectedId}
          batchId={selectedId}
          closing={closing}
          onClose={closeDrawer}
          onChanged={() => void load()}
          onRolledBack={onRolledBack}
        />
      ) : null}

      {wizard ? (
        <ImportWizardModal
          onClose={() => setWizard(false)}
          onCommitted={onCommitted}
          onViewBatch={(batch) => {
            setWizard(false);
            select(batch.id);
          }}
        />
      ) : null}
    </div>
  );
}
