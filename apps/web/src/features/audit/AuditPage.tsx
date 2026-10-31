import { AUDIT_ACTION_LABELS, AuditActionType, type AuditLogRow } from "@ai-pos/shared-types";
import { DateInput, actionHoverClass } from "@ai-pos/ui";
import {
  Activity,
  FileDown,
  FileSpreadsheet,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DataTable, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { filterLabel, FilterSelect } from "../../components/ui/Field";
import { ApiRequestError } from "../../lib/api";
import { AuditDiffDrawer } from "./AuditDiffDrawer";
import { ActionBadge, Avatar, DeviceLabel, formatStamp, shortId } from "./AuditParts";
import {
  PAGE_SIZE,
  downloadExport,
  initialFilters,
  toQuery,
  useAuditTrail,
  type AuditFilterState,
  type RangePreset,
} from "./api";

const rangeOptions: { value: RangePreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "custom", label: "Custom range" },
];

const CLOSE_MS = 200;

function MetricCard({
  tone,
  label,
  value,
  hint,
  icon,
  children,
}: {
  tone: "dark" | "accent" | "light";
  label: string;
  value: number | null;
  hint: string;
  icon: ReactNode;
  children?: ReactNode;
}) {
  const shell = {
    dark: "bg-charcoal text-white",
    accent: "bg-accent text-white",
    light: "border border-line bg-white text-charcoal",
  }[tone];
  const muted = tone === "light" ? "text-charcoal/60" : tone === "accent" ? "text-white/80" : "text-white/60";
  return (
    <article className={`flex min-h-[176px] flex-col justify-between gap-5 rounded-2xl p-6 ${shell}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={`text-sm font-medium ${muted}`}>{label}</p>
          <p className="mt-3 font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums xl:text-[40px]">
            {value === null ? <span className="inline-block h-9 w-20 animate-pulse rounded-xl bg-current opacity-10" /> : value.toLocaleString()}
          </p>
        </div>
        <span
          className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${
            tone === "light" ? "bg-surface text-charcoal" : "bg-white/15 text-white"
          }`}
        >
          {icon}
        </span>
      </div>
      {children ?? <p className={`text-sm ${muted}`}>{hint}</p>}
    </article>
  );
}

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilterState>(initialFilters);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const closeTimer = useRef<number | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setFilters((current) => ({ ...current, search })), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = useMemo(() => toQuery(filters), [filters]);
  const pager = usePagination({ initialPageSize: PAGE_SIZE, resetKeys: [query] });
  const { page, summary, facets, stores, reload } = useAuditTrail(query, pager.offset, pager.pageSize);

  const update = (patch: Partial<AuditFilterState>) => {
    setFilters((current) => ({ ...current, ...patch }));
  };

  const rows = page.state === "ready" ? page.data.rows : [];
  const total = page.state === "ready" ? page.data.total : 0;
  const [selectedRow, setSelectedRow] = useState<AuditLogRow | null>(null);

  const closeDrawer = useCallback(() => {
    setClosing(true);
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      setSelectedId(null);
      setSelectedRow(null);
      setClosing(false);
    }, CLOSE_MS);
  }, []);

  const inspect = (row: AuditLogRow) => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    setClosing(false);
    if (selectedId === row.id) {
      closeDrawer();
      return;
    }
    setSelectedId(row.id);
    setSelectedRow(row);
  };

  useEffect(() => () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
  }, []);

  const runExport = async (format: "csv" | "pdf") => {
    setExporting(format);
    setExportError(null);
    try {
      await downloadExport(query, format);
      reload();
    } catch (error) {
      setExportError(error instanceof ApiRequestError ? error.message : "The export could not be downloaded.");
    } finally {
      setExporting(null);
    }
  };

  const userOptions = [
    { value: "", label: "All users" },
    ...(facets.state === "ready"
      ? facets.data.users.map((user) => ({ value: user.id, label: user.name, hint: user.role ?? undefined }))
      : []),
  ];
  const storeOptions = [
    { value: "", label: "All branches" },
    ...(stores.state === "ready"
      ? stores.data.map((store) => ({ value: store.id, label: `${store.code} · ${store.name}` }))
      : []),
  ];
  const actionOptions = [
    { value: "" as const, label: "All actions" },
    ...Object.values(AuditActionType).map((type) => ({ value: type, label: AUDIT_ACTION_LABELS[type] })),
  ];

  const stats = summary.state === "ready" ? summary.data : null;
  const filtersActive =
    filters.userId !== "" ||
    filters.storeId !== "" ||
    filters.actionType !== "" ||
    filters.sensitiveOnly ||
    filters.search.trim() !== "" ||
    filters.range !== initialFilters.range;

  const columns: DataTableColumn<AuditLogRow>[] = [
    {
      id: "timestamp",
      header: "Timestamp",
      cell: (row) => {
        const stamp = formatStamp(row.occurred_at);
        return (
          <>
            <p className="whitespace-nowrap font-semibold tabular-nums">{stamp.time}</p>
            <p className="whitespace-nowrap text-xs tabular-nums text-charcoal/50">{stamp.day}</p>
          </>
        );
      },
    },
    {
      id: "user",
      header: "User",
      cell: (row) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar name={row.user_name} />
          <div className="min-w-0">
            <p className="truncate font-semibold">{row.user_name ?? "System"}</p>
            <DeviceLabel device={row.client_device} />
          </div>
        </div>
      ),
    },
    { id: "role", header: "Role", className: "text-charcoal/70", cell: (row) => row.user_role ?? "—" },
    {
      id: "branch",
      header: "Branch",
      cell: (row) =>
        row.store_code ? (
          <span className="rounded-full bg-surface px-2.5 py-1 font-mono text-xs font-semibold">{row.store_code}</span>
        ) : (
          <span className="text-xs text-charcoal/40">All</span>
        ),
    },
    {
      id: "action",
      header: "Action",
      cell: (row) => (
        <>
          <ActionBadge type={row.action_type} />
          {row.approver_name ? (
            <p className="mt-1 truncate text-[11px] text-charcoal/50">by {row.approver_name}</p>
          ) : null}
        </>
      ),
    },
    {
      id: "target",
      header: "Target entity",
      cell: (row) => (
        <>
          <p className="font-semibold">
            {row.target_entity}
            {row.target_entity_id ? (
              <span className="ml-1.5 font-mono text-xs font-medium text-charcoal/40">
                #{shortId(row.target_entity_id)}
              </span>
            ) : null}
          </p>
          <p className="max-w-[220px] truncate text-xs text-charcoal/50">
            {row.changed_fields.length > 0
              ? `${row.changed_fields.length} field${row.changed_fields.length === 1 ? "" : "s"}: ${row.changed_fields.join(", ")}`
              : (row.reason_notes ?? row.action)}
          </p>
        </>
      ),
    },
    {
      id: "inspect",
      header: <span className="sr-only">Inspect</span>,
      align: "right",
      cell: (row) => {
        const active = row.id === selectedId && !closing;
        return (
          <button
            type="button"
            onClick={() => inspect(row)}
            aria-pressed={active}
            className={`inline-flex h-9 items-center whitespace-nowrap rounded-full px-4 text-xs font-semibold transition ${
              active ? "bg-accent text-white" : "border border-line bg-white text-charcoal hover:border-charcoal"
            }`}
          >
            Inspect Changes
          </button>
        );
      },
    },
  ];

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="font-sans text-[28px] font-semibold leading-tight tracking-tight md:text-[32px]">
            Audit Trail &amp; Activity
          </h2>
          <p className="mt-1 text-sm text-charcoal/60">
            An append-only record of every change, override, login, and export across the portal and registers.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={reload}
            aria-label="Refresh"
            title="Refresh"
            className="grid h-11 w-11 place-items-center rounded-full border border-line bg-white transition hover:border-charcoal"
          >
            <RefreshCw size={16} aria-hidden="true" className={page.state === "loading" ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            onClick={() => void runExport("csv")}
            disabled={exporting !== null}
            className="inline-flex h-11 items-center gap-2 rounded-full border border-line bg-white px-5 text-sm font-semibold transition hover:border-charcoal disabled:opacity-50"
          >
            <FileSpreadsheet size={16} aria-hidden="true" />
            {exporting === "csv" ? "Exporting…" : "Export CSV"}
          </button>
          <button
            type="button"
            onClick={() => void runExport("pdf")}
            disabled={exporting !== null}
            className="inline-flex h-11 items-center gap-2 rounded-full bg-charcoal px-5 text-sm font-semibold text-white transition hover:bg-accent disabled:opacity-50"
          >
            <FileDown size={16} aria-hidden="true" />
            {exporting === "pdf" ? "Exporting…" : "Export PDF"}
          </button>
        </div>
      </div>
      {exportError ? (
        <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
          {exportError}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:gap-6">
        <MetricCard
          tone="dark"
          label="Total actions today"
          value={stats?.total_actions ?? null}
          hint="Since midnight, every branch you can see."
          icon={<Activity size={18} aria-hidden="true" />}
        />
        <MetricCard
          tone="accent"
          label="Sensitive overrides"
          value={stats?.sensitive_overrides ?? null}
          hint="Price, credit, stock, role, refund and drawer overrides today."
          icon={<ShieldAlert size={18} aria-hidden="true" />}
        >
          <button
            type="button"
            onClick={() => update({ sensitiveOnly: true, range: "today" })}
            className={`self-start rounded-full bg-white/20 px-3.5 py-1.5 text-xs font-semibold text-white ${actionHoverClass("info")}`}
          >
            Review today&rsquo;s overrides
          </button>
        </MetricCard>
        <MetricCard
          tone="light"
          label="Active staff sessions"
          value={stats?.active_staff_sessions ?? null}
          hint=""
          icon={<Users size={18} aria-hidden="true" />}
        >
          {stats && stats.active_staff.length > 0 ? (
            <div className="flex items-center gap-3">
              <div className="flex -space-x-2">
                {stats.active_staff.slice(0, 5).map((person) => (
                  <span key={person.user_id} className="rounded-full ring-2 ring-white" title={person.user_name}>
                    <Avatar name={person.user_name} size="sm" />
                  </span>
                ))}
              </div>
              <p className="min-w-0 truncate text-xs text-charcoal/60">
                Signed in within {stats.session_window_minutes} min
              </p>
            </div>
          ) : (
            <p className="text-sm text-charcoal/60">
              {stats ? `No sign-ins in the last ${stats.session_window_minutes} minutes.` : "Loading…"}
            </p>
          )}
        </MetricCard>
      </div>

      <div className="rounded-2xl border border-line bg-white p-4 sm:p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1fr_1fr_1.3fr]">
          <FilterSelect
            label="Date range"
            value={filters.range}
            options={rangeOptions}
            onChange={(range) => update({ range })}
          />
          <FilterSelect label="User" value={filters.userId} options={userOptions} onChange={(userId) => update({ userId })} />
          <FilterSelect
            label="Store branch"
            value={filters.storeId}
            options={storeOptions}
            onChange={(storeId) => update({ storeId })}
          />
          <FilterSelect
            label="Action"
            value={filters.actionType}
            options={actionOptions}
            onChange={(actionType) => update({ actionType })}
          />
          <label className="block">
            <span className={filterLabel}>Search</span>
            <span className="relative block">
              <Search
                size={15}
                className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-charcoal/40"
                aria-hidden="true"
              />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="User, entity, action or reason"
                className="h-11 w-full rounded-full border border-transparent bg-surface pl-10 pr-4 text-sm transition placeholder:text-charcoal/40 focus:border-accent focus:bg-white focus:outline-none"
              />
            </span>
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {filters.range === "custom" ? (
            <>
              <label className="block">
                <span className={filterLabel}>From</span>
                <DateInput
                  value={filters.customFrom}
                  max={filters.customTo || undefined}
                  onChange={(event) => update({ customFrom: event.target.value })}
                  className="h-11 rounded-full border border-transparent bg-surface px-4 text-sm tabular-nums focus:border-accent focus:bg-white focus:outline-none"
                />
              </label>
              <label className="block">
                <span className={filterLabel}>To</span>
                <DateInput
                  value={filters.customTo}
                  min={filters.customFrom || undefined}
                  onChange={(event) => update({ customTo: event.target.value })}
                  className="h-11 rounded-full border border-transparent bg-surface px-4 text-sm tabular-nums focus:border-accent focus:bg-white focus:outline-none"
                />
              </label>
            </>
          ) : null}
          <button
            type="button"
            role="switch"
            aria-checked={filters.sensitiveOnly}
            onClick={() => update({ sensitiveOnly: !filters.sensitiveOnly })}
            className={`inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold transition ${
              filters.sensitiveOnly ? "bg-accent text-white" : "bg-surface text-charcoal hover:bg-charcoal/10"
            }`}
          >
            <ShieldAlert size={15} aria-hidden="true" /> Sensitive only
          </button>
          {filtersActive ? (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                update(initialFilters);
              }}
              className="inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold text-charcoal/60 transition hover:bg-surface hover:text-charcoal"
            >
              <SlidersHorizontal size={15} aria-hidden="true" /> Reset filters
            </button>
          ) : null}
          <p className="ml-auto text-sm tabular-nums text-charcoal/60">
            {page.state === "ready" ? `${total.toLocaleString()} ${total === 1 ? "entry" : "entries"}` : ""}
          </p>
        </div>
      </div>

      <div className="flex items-start gap-6">
        <div className="min-w-0 flex-1 space-y-3">
          {page.state === "error" ? (
            <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
              {page.message}
            </p>
          ) : null}
          <DataTable
            aria-label="Audit trail"
            minWidth="880px"
            columns={columns}
            data={rows}
            getRowId={(row) => row.id}
            isLoading={page.state === "loading" && rows.length === 0}
            isFetching={page.state === "loading" && rows.length > 0}
            isRowActive={(row) => row.id === selectedId && !closing}
            rowClassName={(row) => (row.sensitive && row.id !== selectedId ? "bg-surface/40" : "")}
            emptyState={{ icon: Activity, title: "No activity matches these filters" }}
            pagination={{
              mode: "server",
              currentPage: pager.page,
              pageSize: pager.pageSize,
              totalRecords: total,
              onPageChange: pager.setPage,
              onPageSizeChange: pager.setPageSize,
            }}
          />
        </div>

        {selectedRow ? <AuditDiffDrawer row={selectedRow} closing={closing} onClose={closeDrawer} /> : null}
      </div>
    </section>
  );
}
