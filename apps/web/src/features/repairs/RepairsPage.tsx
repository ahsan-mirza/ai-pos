import seed from "@ai-pos/catalog/seed.json";
import {
  Permission,
  RepairStatus,
  SerialKind,
  formatMoney,
  type PaymentMethod,
  type ProductSearchHit,
  type RepairDetail,
  type RepairTicket,
} from "@ai-pos/shared-types";
import { CircleDot, Package, ReceiptText, Trash2, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiDelete, apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { message, toCents } from "../customers/api";
import { RepairBench } from "./RepairBench";
import { WorkshopPanel } from "./WorkshopPanel";

const stamped = "2026-10-19T00:00:00.000Z";

const sampleRepairs: RepairTicket[] = [
  {
    id: "00000000-0000-4000-8000-000000000101",
    store_id: seed.store.id,
    customer_name: "Walk-in customer",
    customer_phone: "+1 202 555 0142",
    device_model: "Pixel 9",
    identifier_kind: SerialKind.Imei,
    identifier_value: "490154203237518",
    issue: "Cracked rear glass",
    status: RepairStatus.InRepair,
    estimated_cost_cents: 12900,
    currency: "USD",
    created_at: stamped,
    updated_at: stamped,
  },
  {
    id: "00000000-0000-4000-8000-000000000102",
    store_id: seed.store.id,
    customer_name: "Walk-in customer",
    customer_phone: "+1 202 555 0188",
    device_model: "Tablet 11",
    identifier_kind: SerialKind.Serial,
    identifier_value: "TAB-44190",
    issue: "Battery drains overnight",
    status: RepairStatus.Ready,
    estimated_cost_cents: 8900,
    currency: "USD",
    created_at: stamped,
    updated_at: stamped,
  },
];

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
    intake: "Booked in",
    diagnosing: "Diagnosing",
    awaiting_approval: "Awaiting approval",
    in_repair: "In repair",
    waiting_parts: "Waiting for parts",
    ready: "Ready",
    closed: "Collected",
    cancelled: "Cancelled",
  })[status] ?? status;

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
  const { currency } = useCurrency();
  const [live, setLive] = useState<RepairTicket[] | null>(null);
  const [view, setView] = useState<"list" | "bench">("bench");
  const [openId, setOpenId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const tickets = live ?? sampleRepairs.map((ticket) => ({ ...ticket, currency }));
  const source = live === null ? "sample" : "live";

  const load = useCallback(() => {
    apiGet<RepairTicket[]>("/api/v1/repairs?limit=200")
      .then(setLive)
      .catch(() => setLive(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Repair board</h2>
          <p className="text-sm text-charcoal/60">
            {source === "live"
              ? "Move a job from intake to collection, approve the estimate, and invoice with the deposit credited."
              : "Showing sample tickets until the API responds."}
          </p>
        </div>
        {source === "live" ? (
          <SegmentedControl
            label="Repair view"
            value={view}
            options={[
              { value: "bench", label: "Bench" },
              { value: "list", label: "List" },
            ]}
            onChange={setView}
          />
        ) : null}
      </div>
      {source === "live" && view === "bench" ? (
        <RepairBench onOpen={setOpenId} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
        {tickets.map((ticket) => (
          <button
            key={ticket.id}
            type="button"
            disabled={source !== "live"}
            onClick={() => setOpenId(ticket.id)}
            className="rounded-card border border-line bg-white p-5 text-left transition-colors hover:border-accent/60 disabled:hover:border-line"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">{ticket.device_model}</h3>
                <p className="text-sm text-charcoal/60">{ticket.customer_name}</p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${statusClass[ticket.status]}`}>
                {statusLabel(ticket.status)}
              </span>
            </div>
            <p className="mt-4 text-sm">{ticket.issue}</p>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-charcoal/50">Identifier</dt>
                <dd className="tabular-nums">{ticket.identifier_value}</dd>
              </div>
              <div>
                <dt className="text-charcoal/50">Estimate</dt>
                <dd className="tabular-nums">{formatMoney(ticket.estimated_cost_cents, ticket.currency)}</dd>
              </div>
            </dl>
          </button>
        ))}
        {tickets.length === 0 ? <p className="text-sm text-charcoal/60">No repair tickets yet.</p> : null}
      </div>
      )}
      {openId ? (
        <RepairDrawer
          ticketId={openId}
          onClose={() => {
            setOpenId(null);
            load();
          }}
          onToast={setToast}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function RepairDrawer({ ticketId, onClose, onToast }: { ticketId: string; onClose: () => void; onToast: (text: string) => void }) {
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

  return (
    <Modal
      title={ticket ? `${ticket.device_model} · ${ticket.customer_name}` : "Repair ticket"}
      subtitle={ticket ? `${ticket.issue} · ${ticket.identifier_value}` : undefined}
      onClose={onClose}
      width="lg"
      footer={<GhostButton onClick={onClose}>Close</GhostButton>}
    >
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
