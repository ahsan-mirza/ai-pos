import {
  Permission,
  formatMoney,
  type PaymentMethod,
  type ProductSearchHit,
  type RepairBoard,
  type RepairDetail,
  type RepairTicket,
} from "@ai-pos/shared-types";
import { DataTable, usePagination, type DataTableColumn } from "@ai-pos/ui";
import { CircleDot, Package, ReceiptText, Trash2, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
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

const views: { id: string; label: string }[] = [
  { id: "all", label: "All repairs" },
  { id: "customer", label: "Customer repairs" },
  { id: "internal", label: "Business repairs" },
  { id: "active", label: "Active jobs" },
  { id: "approval", label: "Awaiting approval" },
  { id: "parts", label: "Waiting for parts" },
  { id: "ready", label: "Ready for collection" },
  { id: "overdue", label: "Overdue repairs" },
  { id: "done", label: "Completed repairs" },
];

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

function viewQuery(view: string): Record<string, string> {
  if (view === "customer") return { ownership: "customer" };
  if (view === "internal") return { ownership: "internal" };
  if (view === "active") return { active: "true" };
  if (view === "approval") return { status: "awaiting_approval" };
  if (view === "parts") return { status: "waiting_parts" };
  if (view === "ready") return { status: "ready" };
  if (view === "overdue") return { overdue: "true" };
  if (view === "done") return { status: "closed" };
  return {};
}

export function RepairsPage() {
  const { can } = useAuth();
  const financial = can(Permission.AccountingManage);
  const { ticketId } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? "all";
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
  const dismissToast = useCallback(() => setToast(null), []);
  const filters = `${view}|${debounced}|${receivedFrom}|${receivedTo}|${technicianId}|${warranty}`;
  const pager = usePagination({ resetKeys: [filters] });

  useEffect(() => {
    apiGet<RepairBoard>("/api/v1/repairs/board")
      .then((board) => setTechnicians(board.technicians))
      .catch(() => setTechnicians([]));
  }, []);

  const load = useCallback(() => {
    const query = new URLSearchParams(viewQuery(view));
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
  }, [view, debounced, receivedFrom, receivedTo, technicianId, warranty, pager.offset, pager.pageSize]);

  useEffect(() => {
    if (ticketId) return;
    load();
  }, [load, ticketId]);

  const setView = (id: string) => {
    const next = new URLSearchParams(params);
    if (id === "all") next.delete("view");
    else next.set("view", id);
    setParams(next, { replace: true });
  };

  const clearFilters = () => {
    setDraft("");
    setReceivedFrom("");
    setReceivedTo("");
    setTechnicianId("");
    setWarranty(false);
    setParams(new URLSearchParams(), { replace: true });
  };

  const filtered = view !== "all" || debounced.trim() !== "" || receivedFrom !== "" || receivedTo !== "" || technicianId !== "" || warranty;
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
          Open
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
          <h2 className="text-2xl font-semibold">Repair jobs</h2>
          <p className="text-sm text-charcoal/60">
            {total} job{total === 1 ? "" : "s"}. Open a row to update status, parts, and the estimate. Booking stays on the register.
          </p>
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
      <div className="flex flex-wrap gap-2">
        {views.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setView(item.id)}
            className={`h-9 rounded-full px-3 text-sm ${view === item.id ? "bg-charcoal text-white" : "bg-white ring-1 ring-line"}`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs text-charcoal/60">
          Search
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Number, customer, phone, device, serial, IMEI"
            aria-label="Search repair jobs"
            className="h-10 w-72 max-w-full rounded-full border border-line px-4 text-sm text-charcoal"
          />
        </label>
        <label className="hidden gap-1 text-xs text-charcoal/60 md:grid">
          Received from
          <input type="date" value={receivedFrom} onChange={(event) => setReceivedFrom(event.target.value)} className="h-10 rounded-xl border border-line px-3 text-sm" />
        </label>
        <label className="hidden gap-1 text-xs text-charcoal/60 md:grid">
          Received to
          <input type="date" value={receivedTo} onChange={(event) => setReceivedTo(event.target.value)} className="h-10 rounded-xl border border-line px-3 text-sm" />
        </label>
        <FilterSelect
          label="Technician"
          className="hidden md:block"
          value={technicianId}
          options={[{ value: "", label: "Anyone" }, ...technicians.map((person) => ({ value: person.id, label: person.name }))]}
          onChange={setTechnicianId}
        />
        <label className="hidden h-10 items-center gap-2 text-sm md:flex">
          <input type="checkbox" checked={warranty} onChange={(event) => setWarranty(event.target.checked)} />
          Warranty repair
        </label>
        {filtered ? <GhostButton onClick={clearFilters}>Clear filters</GhostButton> : null}
      </div>
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
              : { title: "No repair jobs yet", description: "Book the first repair from the register." }
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
      <section className="mx-auto max-w-3xl space-y-4">
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
