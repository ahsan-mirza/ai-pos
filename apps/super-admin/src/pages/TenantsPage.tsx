import { PROFILE_PRESETS, type BusinessProfile, type TenantRow } from "@ai-pos/shared-types";
import { DataTable, Select, type DataTableColumn } from "@ai-pos/ui";
import { Building2, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, StatusBadge } from "../components/ui";
import { api, errorText } from "../lib/api";
import { bytes, date, money } from "../lib/format";

const columns: DataTableColumn<TenantRow>[] = [
  {
    header: "Store",
    cell: (row) => (
      <span className="block min-w-0">
        <span className="block font-semibold">{row.name}</span>
        <span className="block font-mono text-xs text-charcoal/50">{row.domain}</span>
      </span>
    ),
  },
  { header: "Business type", cell: (row) => row.profile_label },
  {
    header: "Plan",
    cell: (row) => (
      <span>
        {row.plan_name}
        {row.practice_mode ? <span className="ml-2 text-xs text-charcoal/50">Practice</span> : null}
      </span>
    ),
  },
  { header: "Stores", align: "right", cell: (row) => row.stats.stores },
  { header: "Customers", align: "right", cell: (row) => row.stats.customers },
  { header: "Sales (30 d)", align: "right", cell: (row) => money(row.stats.sales_30d_cents, row.stats.currency) },
  { header: "Database", align: "right", cell: (row) => bytes(row.stats.db_size_bytes) },
  {
    header: "Status",
    cell: (row) => (
      <span className="flex flex-wrap items-center gap-1.5">
        <StatusBadge value={row.status} />
        {row.stats.onboarded === false ? <StatusBadge value="onboarding" /> : null}
        {row.pending_requests > 0 ? (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">{row.pending_requests} request</span>
        ) : null}
      </span>
    ),
  },
  { header: "Since", align: "right", cell: (row) => date(row.created_at) },
];

/** Every registered store, with its size and activity from the last stats snapshot. */
export function TenantsPage() {
  const navigate = useNavigate();
  const { tenantId } = useParams();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [profile, setProfile] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [rows, setRows] = useState<TenantRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ offset: String((page - 1) * pageSize), limit: String(pageSize) });
    if (debounced.trim()) params.set("q", debounced.trim());
    if (status) params.set("status", status);
    if (profile) params.set("profile", profile);
    setLoading(true);
    try {
      const result = await api.page<TenantRow>(`/tenants?${params.toString()}`);
      setRows(result.rows);
      setTotal(result.total);
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the tenants."));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, debounced, status, profile]);

  useEffect(() => {
    void load();
  }, [load]);

  const profiles = Object.keys(PROFILE_PRESETS) as BusinessProfile[];

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <Building2 size={20} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold">Tenants</h1>
            <p className="text-sm text-charcoal/60">{total} registered stores</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <span className="sr-only">Search tenants</span>
            <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-charcoal/40" />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="Name, subdomain or owner email"
              className="h-10 w-72 rounded-full border border-line bg-white pl-9 pr-4 text-sm focus:border-accent focus:outline-none"
            />
          </label>
          <Select
            className="w-44"
            aria-label="Status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "", label: "All statuses" },
              { value: "active", label: "Active" },
              { value: "suspended", label: "Suspended" },
            ]}
          />
          <Select
            className="w-56"
            aria-label="Business type"
            value={profile}
            onChange={(value) => {
              setProfile(value);
              setPage(1);
            }}
            options={[
              { value: "", label: "All business types" },
              ...profiles.map((id) => ({ value: id, label: PROFILE_PRESETS[id].label })),
            ]}
          />
        </div>
      </div>
      <ErrorNote message={error} />
      <DataTable
        aria-label="Tenants"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        isLoading={loading && rows.length === 0}
        isFetching={loading && rows.length > 0}
        onRowClick={(row) => navigate(`/tenants/${row.id}`)}
        isRowActive={(row) => row.id === tenantId}
        minWidth="980px"
        emptyState={{ title: "No tenants match", description: "Try another search or filter.", icon: Building2 }}
        pagination={{
          mode: "server",
          currentPage: page,
          pageSize,
          totalRecords: total,
          onPageChange: setPage,
          onPageSizeChange: (size) => {
            setPageSize(size);
            setPage(1);
          },
        }}
      />
      <Outlet context={{ reload: load }} />
    </section>
  );
}
