import {
  Permission,
  formatMoney,
  type PaymentMethod,
  type ProductSearchHit,
  type RepairBoard,
  type RepairDetail,
  type RepairTicket,
} from "@ai-pos/shared-types";
import { DataTable, RepairJobsToolbar, usePagination, type DataTableColumn } from "@ai-pos/ui";
import { CircleDot, Package, ReceiptText, Trash2, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiDelete, apiGet, apiGetPage, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { message, toCents } from "../customers/api";
import { RepairBench } from "./RepairBench";
import { WorkshopPanel } from "./WorkshopPanel";

const statusClass: Record<RepairTicket["status"], string> = {
  intake: "bg-surface text-charcoal",
  diagnosing: "bg-surface text-charcoal",
  awaiting_approval: "bg-accent/10 text-accent",
  in_repair: "bg-accent text-white",
  waiting_parts: "bg-accent/10 text-accent",
  ready: "bg-charcoal text-white",
  closed: "bg-neutral text-charcoal",
  cancelled: "bg-neutral text-charcoal",
};

const statusLabel = (status: string) =>
  ({
    intake: "Received",
    diagnosing: "Awaiting diagnosis",
    awaiting_approval: "Awaiting customer approval",
    in_repair: "In progress",
    waiting_parts: "Waiting for parts",
    ready: "Ready for collection",
    closed: "Collected",
    cancelled: "Cancelled",
  })[status] ?? status;

const statusOptions = [
  { value: "", label: "All statuses" },
  { value: "active", label: "Active jobs" },
  { value: "awaiting_approval", label: "Awaiting approval" },
  { value: "waiting_parts", label: "Waiting for parts" },
  { value: "ready", label: "Ready for collection" },
  { value: "overdue", label: "Overdue" },
  { value: "closed", label: "Completed" },
];

const typeOptions = [
  { value: "", label: "All types" },
  { value: "customer", label: "Customer repairs" },
  { value: "internal", label: "Business repairs" },
];

function legacyStatus(view: string): string {
  if (view === "active") return "active";
  if (view === "approval") return "awaiting_approval";
  if (view === "parts") return "waiting_parts";
  if (view === "ready") return "ready";
  if (view === "overdue") return "overdue";
  if (view === "done") return "closed";
  return "";
}

function legacyType(view: string): string {
  return view === "customer" || view === "internal" ? view : "";
}

function useDebounced(value: string): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), 300);
    return () => window.clearTimeout(timer);
  }, [value]);
  return debounced;
}

const nextStatus: Record<RepairTicket["status"], RepairTicket["status"][]> = {
  intake: ["diagnosing", "awaiting_approval", "in_repair", "ready", "cancelled", "closed"],
  diagnosing: ["awaiting_approval", "in_repair", "waiting_parts", "ready", "cancelled", "closed"],
  awaiting_approval: ["diagnosing", "in_repair", "ready", "cancelled", "closed"],
  in_repair: ["diagnosing", "waiting_parts", "ready", "cancelled", "closed"],
  waiting_parts: ["in_repair", "ready", "cancelled", "closed"],
  ready: ["in_repair", "closed"],
  closed: [],
  cancelled: [],
};

const warrantyLabels: Record<NonNullable<RepairDetail["warranty_status"]>, string> = {
  IN_WARRANTY: "Under warranty",
  EXPIRED: "Warranty expired",
  NOT_FOUND: "Not sold here",
};

export function RepairsPage() {
  const { can } = useAuth();
  const financial = can(Permission.AccountingManage);
  const { ticketId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const legacy = params.get("view") ?? "";
  const explicit = params.has("status") || params.has("ownership");
  const status = explicit ? (params.get("status") ?? "") : legacyStatus(legacy);
  const ownership = explicit ? (params.get("ownership") ?? "") : legacyType(legacy);
  const layout = params.get("layout") === "bench" ? "bench" : "jobs";
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const debounced = useDebounced(draft);
  const [receivedFrom, setReceivedFrom] = useState(params.get("from") ?? "");
  const [receivedTo, setReceivedTo] = useState(params.get("to") ?? "");
  const [technicianId, setTechnicianId] = useState(params.get("technician") ?? "");
  const [warranty, setWarranty] = useState(params.get("warranty") === "1");
  const [technicians, setTechnicians] = useState<{ id: string; name: string }[]>([]);
  const [rows, setRows] = useState<RepairTicket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [counts, setCounts] = useState<{ active: number; approval: number; parts: number; ready: number; overdue: number } | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const filters = `${status}|${ownership}|${debounced}|${receivedFrom}|${receivedTo}|${technicianId}|${warranty}`;
  const pager = usePagination({ resetKeys: [filters] });

  useEffect(() => {
    apiGet<RepairBoard>("/api/v1/repairs/board")
      .then((board) => setTechnicians(board.technicians))
      .catch(() => setTechnicians([]));
  }, []);

  useEffect(() => {
    if (ticketId) return;
    let cancelled = false;
    const count = (query: string) =>
      apiGetPage<RepairTicket>(`/api/v1/repairs?${query}`, { offset: 0, limit: 1 }).then((page) => page.total);
    Promise.all([
      count("active=true"),
      count("status=awaiting_approval"),
      count("status=waiting_parts"),
      count("status=ready"),
      count("overdue=true"),
    ])
      .then(([active, approval, parts, ready, overdue]) => {
        if (!cancelled) setCounts({ active, approval, parts, ready, overdue });
      })
      .catch(() => {
        if (!cancelled) setCounts(null);
      });
    return () => {
      cancelled = true;
    };
  }, [rows, ticketId]);

  const load = useCallback(() => {
    const query = new URLSearchParams();
    if (ownership) query.set("ownership", ownership);
    if (status === "active") query.set("active", "true");
    else if (status === "overdue") query.set("overdue", "true");
    else if (status) query.set("status", status);
    if (debounced.trim()) query.set("q", debounced.trim());
    if (receivedFrom) query.set("received_from", receivedFrom);
    if (receivedTo) query.set("received_to", receivedTo);
    if (technicianId) query.set("technician_id", technicianId);
    if (warranty) query.set("warranty", "true");
    setLoading(true);
    apiGetPage<RepairTicket>(`/api/v1/repairs?${query.toString()}`, { offset: pager.offset, limit: pager.pageSize })
      .then((page) => {
        setRows(page.rows);
        setTotal(page.total);
        setError(null);
      })
      .catch((caught: unknown) => setError(message(caught, "Could not load repair jobs.")))
      .finally(() => setLoading(false));
  }, [status, ownership, debounced, receivedFrom, receivedTo, technicianId, warranty, pager.offset, pager.pageSize]);

  useEffect(() => {
    if (ticketId) return;
    load();
  }, [load, ticketId]);

  const writeFilter = (patch: { status?: string; ownership?: string }) => {
    const next = new URLSearchParams(params);
    next.delete("view");
    const nextStatus = patch.status === undefined ? status : patch.status;
    const nextType = patch.ownership === undefined ? ownership : patch.ownership;
    if (nextStatus) next.set("status", nextStatus);
    else next.delete("status");
    if (nextType) next.set("ownership", nextType);
    else next.delete("ownership");
    setParams(next, { replace: true });
  };

  const clearFilters = () => {
    setDraft("");
    setReceivedFrom("");
    setReceivedTo("");
    setTechnicianId("");
    setWarranty(false);
    const next = new URLSearchParams();
    if (layout === "bench") next.set("layout", "bench");
    setParams(next, { replace: true });
  };

  const filtered = status !== "" || ownership !== "" || debounced.trim() !== "" || receivedFrom !== "" || receivedTo !== "" || technicianId !== "" || warranty;
  const columns: DataTableColumn<RepairTicket>[] = [
    {
      id: "number",
      header: "Repair no.",
      className: "font-mono text-xs",
      cell: (row) => row.reference || row.id.slice(0, 8).toUpperCase(),
    },
    {
      id: "owner",
      header: "Customer",
      cell: (row) =>
        row.ownership === "internal" ? (
          <span>
            <span className="block font-medium">Business repair</span>
            <span className="text-xs text-charcoal/50">Internal maintenance</span>
          </span>
        ) : (
          <span>
            <span className="block font-medium">{row.customer_name}</span>
            <span className="text-xs text-charcoal/50">{row.customer_phone}</span>
          </span>
        ),
    },
    { id: "device", header: "Device", cell: (row) => row.device_model },
    {
      id: "serial",
      header: "Serial / IMEI",
      className: "hidden font-mono text-xs md:table-cell",
      headerClassName: "hidden md:table-cell",
      cell: (row) => row.identifier_value,
    },
    {
      id: "fault",
      header: "Reported fault",
      className: "hidden max-w-[16rem] truncate lg:table-cell",
      headerClassName: "hidden lg:table-cell",
      cell: (row) => row.issue,
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass[row.status]} ${row.overdue ? "ring-1 ring-amber-400" : ""}`}>
          {statusLabel(row.status)}
          {row.overdue ? " · overdue" : ""}
        </span>
      ),
    },
    {
      id: "estimate",
      header: "Estimate",
      align: "right",
      cell: (row) => formatMoney(row.estimated_cost_cents, row.currency),
    },
    {
      id: "deposit",
      header: "Deposit",
      align: "right",
      cell: (row) => formatMoney(row.deposit_held_cents ?? 0, row.currency),
    },
    {
      id: "tech",
      header: "Technician",
      className: "hidden lg:table-cell",
      headerClassName: "hidden lg:table-cell",
      cell: (row) => row.technician_name || "—",
    },
    {
      id: "received",
      header: "Received",
      className: "whitespace-nowrap text-xs",
      cell: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      id: "due",
      header: "Expected",
      className: "hidden whitespace-nowrap text-xs xl:table-cell",
      headerClassName: "hidden xl:table-cell",
      cell: (row) => (row.promised_at ? new Date(row.promised_at).toLocaleDateString() : "—"),
    },
    ...(financial
      ? [
          {
            id: "parts",
            header: "Parts cost",
            align: "right" as const,
            cell: (row: RepairTicket) => formatMoney(row.parts_cents ?? 0, row.currency),
          },
          {
            id: "labour",
            header: "Labor cost",
            align: "right" as const,
            cell: (row: RepairTicket) => formatMoney(row.labour_cents ?? 0, row.currency),
          },
        ]
      : []),
    {
      id: "open",
      header: "",
      cell: (row) => (
        <button type="button" className="text-sm font-semibold text-accent" onClick={() => navigate(`/repairs/${row.id}`)}>
          View details
        </button>
      ),
    },
  ];

  if (ticketId) {
    return (
      <>
        <RepairDrawer
          ticketId={ticketId}
          presentation="page"
          onClose={() => navigate("/repairs")}
          onToast={setToast}
        />
        {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
      </>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-charcoal/50">Admin / Repairs</p>
          <h2 className="text-2xl font-semibold">Repairs</h2>
        </div>
        <SegmentedControl
          label="Repair view"
          value={layout}
          options={[
            { value: "jobs", label: "Jobs" },
            { value: "bench", label: "Bench" },
          ]}
          onChange={(next) => {
            const updated = new URLSearchParams(params);
            if (next === "bench") updated.set("layout", "bench");
            else updated.delete("layout");
            setParams(updated, { replace: true });
          }}
        />
      </div>
      {counts ? (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-charcoal/70">
          <span>{counts.active} active</span>
          <span>{counts.approval} awaiting approval</span>
          <span>{counts.parts} waiting for parts</span>
          <span>{counts.ready} ready</span>
          <span>{counts.overdue} overdue</span>
        </p>
      ) : null}
      <div>
        <h3 className="text-lg font-semibold">Repair jobs</h3>
        <p className="text-sm text-charcoal/60">{total} job{total === 1 ? "" : "s"}</p>
      </div>
      <RepairJobsToolbar
        search={draft}
        onSearch={setDraft}
        status={status}
        onStatus={(value) => writeFilter({ status: value })}
        statusOptions={statusOptions}
        type={ownership}
        onType={(value) => writeFilter({ ownership: value })}
        typeOptions={typeOptions}
        from={receivedFrom}
        to={receivedTo}
        onFrom={setReceivedFrom}
        onTo={setReceivedTo}
        technician={technicianId}
        onTechnician={setTechnicianId}
        technicianOptions={[{ value: "", label: "Anyone" }, ...technicians.map((person) => ({ value: person.id, label: person.name }))]}
        moreActive={warranty}
        more={
          <label className="flex h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={warranty} onChange={(event) => setWarranty(event.target.checked)} />
            Warranty repair
          </label>
        }
        onClear={clearFilters}
        clearVisible={filtered}
      />
      {layout === "bench" ? (
        <RepairBench onOpen={(id) => navigate(`/repairs/${id}`)} />
      ) : (
        <DataTable
          aria-label="Repair jobs"
          minWidth="920px"
          columns={columns}
          data={rows}
          getRowId={(row) => row.id}
          isLoading={loading}
          error={error}
          onRetry={load}
          onRowClick={(row) => navigate(`/repairs/${row.id}`)}
          pagination={{
            mode: "server",
            currentPage: pager.page,
            pageSize: pager.pageSize,
            totalRecords: total,
            onPageChange: pager.setPage,
            onPageSizeChange: pager.setPageSize,
          }}
          emptyState={
            filtered
              ? { title: "No repairs match your filters", description: "Clear the search or filters to see every job.", action: <GhostButton onClick={clearFilters}>Clear filters</GhostButton> }
              : {
                  title: "No repair jobs yet",
                  description: "Create your first repair job on the register to start tracking device intake, diagnosis and repair progress.",
                }
          }
        />
      )}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function RepairDrawer({
  ticketId,
  onClose,
  onToast,
  presentation = "modal",
}: {
  ticketId: string;
  onClose: () => void;
  onToast: (text: string) => void;
  presentation?: "modal" | "page";
}) {
  const { can } = useAuth();
  const canUpdate = can(Permission.RepairsUpdate);
  const [ticket, setTicket] = useState<RepairDetail | null>(null);
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState<"PART" | "LABOUR" | null>(null);
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<RepairDetail>(`/api/v1/repairs/${ticketId}`)
      .then(setTicket)
      .catch((caught: unknown) => setError(message(caught, "Could not load the ticket.")));
  }, [ticketId]);

  const run = async (work: () => Promise<RepairDetail>, done?: string) => {
    setBusy(true);
    setError(null);
    try {
      setTicket(await work());
      if (done) onToast(done);
      return true;
    } catch (caught) {
      setError(message(caught, "Could not update the ticket."));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const editable = ticket !== null && canUpdate && ticket.sale_id === null && ticket.status !== "closed" && ticket.status !== "cancelled";
  const money = (cents: number) => formatMoney(cents, ticket?.currency ?? "USD");

  const title = ticket
    ? `${ticket.ownership === "internal" ? "Business repair" : ticket.customer_name} · ${ticket.device_model}`
    : "Repair ticket";
  const body = (
    <>
      {ticket ? (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${statusClass[ticket.status]}`}>
              {statusLabel(ticket.status)}
            </span>
            {ticket.warranty_status ? (
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  ticket.warranty_status === "IN_WARRANTY" ? "bg-accent/10 text-accent" : "bg-surface text-charcoal/70"
                }`}
              >
                {warrantyLabels[ticket.warranty_status]}
              </span>
            ) : null}
            {ticket.invoice_number ? (
              <span className="rounded-full bg-charcoal px-3 py-1 font-mono text-xs font-semibold text-white">{ticket.invoice_number}</span>
            ) : null}
          </div>

          {canUpdate && ticket.sale_id === null ? (
            <div className="rounded-2xl bg-surface p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-charcoal/50">Move to</p>
              <div className="flex flex-wrap gap-1.5">
                {[...(nextStatus[ticket.status] ?? [])].map((status) => (
                    <button
                      key={status}
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () => apiPost<RepairDetail>(`/api/v1/repairs/${ticket.id}/status`, { status, note: note.trim() }),
                          `Ticket moved to ${statusLabel(status)}.`,
                        ).then((ok) => ok && setNote(""))
                      }
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold capitalize ${
                        status === "ready" ? "bg-accent text-white hover:bg-accent-hover" : "border border-line bg-white hover:border-accent hover:text-accent"
                      }`}
                    >
                      {statusLabel(status)}
                    </button>
                  ))}
              </div>
              <input
                value={note}
                maxLength={500}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Note for the timeline (optional)"
                className="mt-3 w-full rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
              />
              {ticket.status !== "ready" ? (
                <p className="mt-2 text-xs text-charcoal/50">Moving to Ready messages the customer if they opted in.</p>
              ) : null}
            </div>
          ) : null}

          <WorkshopPanel ticket={ticket} canUpdate={canUpdate} busy={busy} run={run} onToast={onToast} />

          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">Parts and labour</h3>
              {editable ? (
                <div className="flex gap-1.5">
                  <GhostButton disabled={busy} onClick={() => setAdding("PART")}>
                    <Package size={14} aria-hidden="true" className="-ml-1 mr-1.5" /> Add part
                  </GhostButton>
                  <GhostButton disabled={busy} onClick={() => setAdding("LABOUR")}>
                    <Wrench size={14} aria-hidden="true" className="-ml-1 mr-1.5" /> Add labour
                  </GhostButton>
                </div>
              ) : null}
            </div>
            {ticket.lines.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-line p-5 text-center text-sm text-charcoal/60">
                No charges yet.{ticket.warranty_status === "IN_WARRANTY" ? " Under warranty: charge parts and labour at 0.00 if covered." : ""}
              </p>
            ) : (
              <table className="w-full text-left text-sm">
                <tbody>
                  {ticket.lines.map((line) => (
                    <tr key={line.id} className="border-t border-line first:border-t-0">
                      <td className="py-2.5">
                        <span className="block font-medium">{line.description}</span>
                        <span className="block text-xs text-charcoal/50">
                          {line.kind === "PART" ? "Part" : "Labour"} · {line.sku}
                        </span>
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-charcoal/60">
                        {line.quantity} × {money(line.unit_price_cents)}
                      </td>
                      <td className="py-2.5 text-right font-semibold tabular-nums">{money(line.line_cents)}</td>
                      <td className="w-10 py-2.5 text-right">
                        {editable ? (
                          <button
                            type="button"
                            aria-label={`Remove ${line.description}`}
                            disabled={busy}
                            onClick={() =>
                              void run(async () => {
                                await apiDelete(`/api/v1/repairs/${ticket.id}/lines/${line.id}`);
                                return apiGet<RepairDetail>(`/api/v1/repairs/${ticket.id}`);
                              })
                            }
                            className="rounded-full p-1.5 text-charcoal/50 hover:bg-surface hover:text-accent"
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line">
                    <td className="pt-3 text-xs text-charcoal/60">
                      Parts {money(ticket.parts_cents)} · Labour {money(ticket.labour_cents)}
                    </td>
                    <td />
                    <td className="pt-3 text-right text-lg font-semibold tabular-nums">{money(ticket.total_cents)}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            )}
          </div>

          {editable && ticket.lines.length > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-charcoal p-4 text-white">
              <div>
                <p className="text-sm font-semibold">Invoice and close</p>
                <p className="text-xs text-white/60">
                  Parts leave stock and the customer gets a tax invoice.
                  {ticket.deposit_held_cents ? ` Deposit of ${money(ticket.deposit_held_cents)} is credited.` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <SegmentedControl
                  label="Paid by"
                  value={method}
                  options={[
                    { value: "cash", label: "Cash" },
                    { value: "card", label: "Card" },
                    ...(ticket.customer_id ? [{ value: "on_account" as const, label: "Account" }] : []),
                  ]}
                  onChange={setMethod}
                />
                <PrimaryButton
                  disabled={busy}
                  onClick={() =>
                    void run(
                      () => apiPost<RepairDetail>(`/api/v1/repairs/${ticket.id}/invoice`, { payment_method: method }),
                      "Repair invoiced and closed.",
                    )
                  }
                >
                  <ReceiptText size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Invoice{" "}
                  {money(ticket.balance_due_cents ?? ticket.total_cents)}
                </PrimaryButton>
              </div>
            </div>
          ) : null}

          <div>
            <h3 className="mb-3 text-sm font-semibold">Timeline</h3>
            <ol className="space-y-3">
              {[...ticket.events].reverse().map((event, index) => (
                <li key={`${event.occurred_at}-${index}`} className="flex gap-3">
                  <CircleDot size={16} aria-hidden="true" className={`mt-0.5 shrink-0 ${index === 0 ? "text-accent" : "text-charcoal/30"}`} />
                  <div className="min-w-0 text-sm">
                    <p className="font-medium capitalize">
                      {event.from_status ? `${statusLabel(event.from_status)} → ` : ""}
                      {statusLabel(event.to_status)}
                    </p>
                    <p className="text-xs text-charcoal/60 tabular-nums">
                      {new Date(event.occurred_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} ·{" "}
                      {event.user_name ?? (event.source === "register" ? "At the register" : "System")}
                    </p>
                    {event.note ? <p className="mt-0.5 text-xs text-charcoal/80">{event.note}</p> : null}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      ) : null}
      <ErrorNote message={error} />
      {adding && ticket ? (
        <AddLineModal
          kind={adding}
          currency={ticket.currency}
          onClose={() => setAdding(null)}
          onSave={async (body) => {
            try {
              setTicket(await apiPost<RepairDetail>(`/api/v1/repairs/${ticket.id}/lines`, body));
              setAdding(null);
              return null;
            } catch (caught) {
              return message(caught, "Could not add the line.");
            }
          }}
        />
      ) : null}
    </>
  );
  if (presentation === "page") {
    return (
      <section className="space-y-4">
        <GhostButton onClick={onClose}>Back to repair jobs</GhostButton>
        <h2 className="text-2xl font-semibold">{title}</h2>
        {ticket ? <p className="text-sm text-charcoal/60">{ticket.issue}</p> : null}
        {body}
      </section>
    );
  }
  return (
    <Modal
      title={title}
      subtitle={ticket ? `${ticket.issue} · ${ticket.identifier_value}` : undefined}
      onClose={onClose}
      width="lg"
      footer={<GhostButton onClick={onClose}>Close</GhostButton>}
    >
      {body}
    </Modal>
  );
}

function AddLineModal({
  kind,
  currency,
  onClose,
  onSave,
}: {
  kind: "PART" | "LABOUR";
  currency: string;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => Promise<string | null>;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ProductSearchHit[]>([]);
  const [picked, setPicked] = useState<ProductSearchHit["product"] | null>(null);
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (kind !== "PART" || query.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      apiGet<ProductSearchHit[]>(`/api/v1/products/search?${new URLSearchParams({ q: query.trim(), limit: "8" }).toString()}`)
        .then((found) => setHits(found.filter((hit) => !hit.product.is_serialized && !hit.product.is_open_price)))
        .catch(() => setHits([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [kind, query]);

  const save = async () => {
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty < 1) return setError("Quantity must be a whole number.");
    const cents = price.trim() === "" ? null : toCents(price);
    if (price.trim() !== "" && cents === null) return setError("Enter a price like 80.00.");
    if (kind === "PART" && !picked) return setError("Pick the part from the catalog.");
    if (kind === "LABOUR" && (cents === null || !description.trim())) return setError("Describe the work and enter the charge.");
    setError(null);
    setError(
      await onSave({
        kind,
        product_id: picked?.id ?? null,
        description: description.trim(),
        quantity: qty,
        unit_price_cents: cents,
      }),
    );
  };

  return (
    <Modal
      title={kind === "PART" ? "Add a part" : "Add labour"}
      subtitle={kind === "PART" ? "Parts come out of this branch's stock when the repair is invoiced." : "Labour is billed with the open-price Repair labour item."}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Add</PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {kind === "PART" ? (
          picked ? (
            <div className="flex items-center justify-between rounded-2xl bg-surface px-4 py-3 text-sm">
              <span>
                <span className="block font-medium">{picked.name}</span>
                <span className="block text-xs text-charcoal/60 tabular-nums">
                  {picked.sku} · {formatMoney(picked.price_cents, currency)}
                </span>
              </span>
              <button type="button" onClick={() => setPicked(null)} className="text-xs font-semibold text-accent">
                Change
              </button>
            </div>
          ) : (
            <div>
              <TextField label="Find the part" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, SKU or barcode" />
              <ul className="mt-2 divide-y divide-line rounded-2xl border border-line">
                {hits.map((hit) => (
                  <li key={hit.product.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setPicked(hit.product);
                        setHits([]);
                      }}
                      className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-surface"
                    >
                      <span>{hit.product.name}</span>
                      <span className="tabular-nums text-charcoal/60">{formatMoney(hit.product.price_cents, currency)}</span>
                    </button>
                  </li>
                ))}
                {query.trim().length >= 2 && hits.length === 0 ? <li className="px-4 py-2.5 text-sm text-charcoal/50">No stocked parts match.</li> : null}
              </ul>
            </div>
          )
        ) : null}
        <TextField
          label={kind === "PART" ? "Description (optional)" : "Work done"}
          value={description}
          maxLength={160}
          placeholder={kind === "PART" ? picked?.name ?? "" : "Screen replacement"}
          onChange={(event) => setDescription(event.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Quantity" inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="tabular-nums" />
          <TextField
            label={kind === "PART" ? "Unit price (blank = catalog)" : "Charge"}
            inputMode="decimal"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            className="tabular-nums"
          />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
