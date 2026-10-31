import {
  IMPORT_SOURCE_LABELS,
  Permission,
  formatMoney,
  type BatchDetail,
  type BatchItem,
  type BatchItemUpdate,
  type RollbackResult,
} from "@ai-pos/shared-types";
import { DateInput, actionHoverClass } from "@ai-pos/ui";
import {
  Download,
  FilePlus2,
  Loader2,
  Lock,
  MessageSquareText,
  Pencil,
  Printer,
  ScrollText,
  Smartphone,
  Trash2,
  Undo2,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton } from "../../../components/ui/Field";
import { Toggle } from "../../../components/ui/Toggle";
import { useAuth } from "../../../lib/auth";
import { labelsApi, message } from "../api";
import { batchesApi, centsInput, parseCents } from "../import/api";
import { BatchStatusBadge, SoldMeter, formatDay, formatTime } from "./BatchParts";
import { RollbackModal } from "./RollbackModal";

interface Draft {
  cost: string;
  price: string;
  quantity: string;
  expiry: string;
}

function draftOf(item: BatchItem): Draft {
  return {
    cost: centsInput(item.purchase_cost_per_unit),
    price: centsInput(item.selling_price_per_unit),
    quantity: String(item.quantity_imported),
    expiry: item.expiry_date ?? "",
  };
}

function changesOf(items: BatchItem[], drafts: Record<string, Draft>): BatchItemUpdate[] {
  const out: BatchItemUpdate[] = [];
  for (const item of items) {
    const draft = drafts[item.id];
    if (!draft) continue;
    const change: BatchItemUpdate = { id: item.id };
    const cost = parseCents(draft.cost);
    const price = parseCents(draft.price);
    const quantity = draft.quantity.trim() === "" ? null : Number(draft.quantity);
    if (cost !== null && cost !== item.purchase_cost_per_unit) change.purchase_cost_per_unit = cost;
    if (price !== null && price !== item.selling_price_per_unit) change.selling_price_per_unit = price;
    if (item.editable_quantity && quantity !== null && quantity !== item.quantity_imported)
      change.quantity_imported = quantity;
    if (draft.expiry !== (item.expiry_date ?? "")) {
      if (draft.expiry) change.expiry_date = draft.expiry;
      else change.clear_expiry = true;
    }
    if (Object.keys(change).length > 1) out.push(change);
  }
  return out;
}

function Stat({ label, value, tone = "plain" }: { label: string; value: string; tone?: "plain" | "good" | "bad" }) {
  return (
    <div className="min-w-0 bg-white px-5 py-3.5">
      <span className="block text-xs font-medium text-charcoal/55">{label}</span>
      <span
        className={`mt-1 block truncate text-lg font-semibold tabular-nums tracking-tight ${
          tone === "good" ? "text-emerald-600" : tone === "bad" ? "text-red-600" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function Section({ title, meta, children }: { title: string; meta?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="border-b border-line px-5 py-5 last:border-b-0">
      <h3 className="mb-3 flex items-baseline justify-between gap-3 text-[13px] font-semibold">
        {title}
        {meta ? <span className="text-xs font-medium text-charcoal/45">{meta}</span> : null}
      </h3>
      {children}
    </section>
  );
}

interface AuditEntry {
  icon: LucideIcon;
  tone: "plain" | "accent" | "bad";
  title: string;
  body?: string;
  at?: string;
}

function auditEntries(batch: BatchDetail): AuditEntry[] {
  const template = batch.mapping_template_used?.template_name;
  const entries: AuditEntry[] = [
    {
      icon: FilePlus2,
      tone: "accent",
      title: `Imported by ${batch.created_by_name ?? "system"}`,
      body: [
        `${batch.line_count} line${batch.line_count === 1 ? "" : "s"}, ${batch.total_items_count} units into ${batch.store_code}`,
        IMPORT_SOURCE_LABELS[batch.import_source],
        batch.file_name,
        template ? `template “${template}”` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      at: batch.created_at,
    },
  ];
  if (batch.notes) entries.push({ icon: MessageSquareText, tone: "plain", title: "Note", body: batch.notes });
  if (batch.status === "REVERSED") {
    entries.push({
      icon: Undo2,
      tone: "bad",
      title: `Reversed${batch.reversed_by_name ? ` by ${batch.reversed_by_name}` : ""}`,
      body: batch.reversal_reason ? `“${batch.reversal_reason}”` : undefined,
      at: batch.reversed_at ?? undefined,
    });
  }
  return entries;
}

const toneStyles: Record<AuditEntry["tone"], string> = {
  plain: "bg-white text-charcoal/50 ring-line",
  accent: "bg-accent/10 text-accent ring-accent/20",
  bad: "bg-red-50 text-red-600 ring-red-600/20",
};

const editInput =
  "h-9 w-full rounded-lg border border-line bg-white px-2 text-right text-[13px] tabular-nums focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 disabled:bg-surface disabled:text-charcoal/40";

const toolbarButton =
  "inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40";

export function BatchDrawer({
  batchId,
  closing,
  onClose,
  onChanged,
  onRolledBack,
}: {
  batchId: string;
  closing: boolean;
  onClose: () => void;
  onChanged: () => void;
  onRolledBack: (result: RollbackResult) => void;
}) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const { can } = useAuth();
  const canCorrect = can(Permission.InventoryAdjustStock);
  const canReadAudit = can(Permission.AuditRead);
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [applyToMaster, setApplyToMaster] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setBatch(await batchesApi.get(batchId));
    } catch (caught) {
      setError(message(caught, "Could not load this batch."));
    }
  }, [batchId]);

  useEffect(() => {
    setBatch(null);
    setEditing(false);
    void load();
  }, [load]);

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !rollingBack) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, rollingBack]);

  const startEdit = () => {
    if (!batch) return;
    setDrafts(Object.fromEntries(batch.items.map((item) => [item.id, draftOf(item)])));
    setApplyToMaster(false);
    setReason("");
    setEditing(true);
  };

  const pending = batch ? changesOf(batch.items, drafts) : [];

  const save = async () => {
    if (!batch) return;
    setSaving(true);
    setError(null);
    try {
      setBatch(
        await batchesApi.update(batch.id, {
          items: pending,
          apply_price_to_master: applyToMaster,
          reason: reason.trim() || null,
        }),
      );
      setEditing(false);
      onChanged();
    } catch (caught) {
      setError(message(caught, "The batch could not be updated."));
    } finally {
      setSaving(false);
    }
  };

  const setDraft = (id: string, patch: Partial<Draft>) =>
    setDrafts((current) => ({ ...current, [id]: { ...(current[id] as Draft), ...patch } }));

  const reversed = batch?.status === "REVERSED";

  return (
    <>
      <div
        className={`drawer-backdrop fixed inset-0 z-40 bg-charcoal/40 backdrop-blur-[2px] lg:hidden ${closing ? "opacity-0" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-labelledby={titleId}
        data-state={closing ? "closing" : "open"}
        className="drawer-panel fixed inset-y-0 right-0 z-50 flex w-full flex-col overflow-hidden bg-white shadow-2xl outline-none sm:max-w-xl lg:static lg:z-auto lg:h-full lg:w-[min(560px,46%)] lg:max-w-none lg:shrink-0 lg:border-l lg:border-line lg:shadow-none"
      >
        <header className="sticky top-0 z-20 flex-none border-b border-line bg-white px-5 pb-4 pt-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                {batch ? <BatchStatusBadge status={batch.status} /> : null}
                {batch ? (
                  <span className="rounded-md bg-charcoal/[0.06] px-1.5 py-0.5 text-[11px] font-semibold text-charcoal/60">
                    {IMPORT_SOURCE_LABELS[batch.import_source]}
                  </span>
                ) : null}
                {batch?.is_consignment ? (
                  <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">
                    Consignment · supplier-owned
                  </span>
                ) : null}
              </div>
              <h2 id={titleId} className="mt-2 truncate font-mono text-[17px] font-semibold tracking-tight">
                {batch?.batch_number ?? "Loading batch…"}
              </h2>
              {batch ? (
                <p className="mt-0.5 text-[13px] text-charcoal/55">
                  {batch.store_code} · {batch.store_name}
                  {batch.supplier_name ? ` · ${batch.supplier_name}` : ""} · {formatDay(batch.created_at)}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              aria-label="Close batch"
              onClick={onClose}
              className="-mr-1.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-charcoal/50 transition hover:bg-charcoal/[0.05] hover:text-charcoal"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          {batch && !editing ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {!reversed ? (
                <button
                  type="button"
                  title="One label per unit received"
                  onClick={() =>
                    void labelsApi.batch(batch.id, "a4_3x8").catch((caught: unknown) => setError(message(caught, "Could not print labels.")))
                  }
                  className={`${toolbarButton} border border-line text-charcoal hover:bg-charcoal/[0.04]`}
                >
                  <Printer size={13} aria-hidden="true" /> Print labels
                </button>
              ) : null}
              {canCorrect && !reversed ? (
                <>
                  <button
                    type="button"
                    onClick={startEdit}
                    className={`${toolbarButton} bg-charcoal text-white hover:bg-black`}
                  >
                    <Pencil size={13} aria-hidden="true" /> Edit batch
                  </button>
                  <button
                    type="button"
                    onClick={() => setRollingBack(true)}
                    className={`${toolbarButton} border border-line text-charcoal ${actionHoverClass("danger")}`}
                  >
                    <Trash2 size={13} aria-hidden="true" /> Delete & rollback
                  </button>
                </>
              ) : null}
              {batch.file_name ? (
                <button
                  type="button"
                  onClick={() =>
                    void batchesApi
                      .download(batch.id, batch.file_name ?? "import")
                      .catch((caught: unknown) => setError(message(caught, "The file could not be downloaded.")))
                  }
                  className={`${toolbarButton} border border-line text-charcoal/75 hover:bg-[#f8fafc]`}
                >
                  <Download size={13} aria-hidden="true" />
                  <span className="max-w-[180px] truncate">{batch.file_name}</span>
                </button>
              ) : null}
            </div>
          ) : null}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {batch === null ? (
            error ? null : (
              <div className="flex items-center gap-2 px-5 py-10 text-sm text-charcoal/60">
                <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Loading batch…
              </div>
            )
          ) : (
            <>
              {reversed ? (
                <div className="flex items-start gap-3 border-b border-red-100 bg-red-50 px-5 py-3 text-[13px] text-red-700">
                  <Lock size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
                  <p>Sold records are locked; remaining stock was pulled back out of inventory.</p>
                </div>
              ) : null}

              <div aria-label="Batch P&L" role="group" className="grid grid-cols-2 gap-px border-b border-line bg-line">
                <Stat label="Batch cost" value={formatMoney(batch.total_cost_amount, batch.currency)} />
                <Stat label="Revenue" value={formatMoney(batch.revenue_cents, batch.currency)} />
                <Stat label="COGS (FIFO)" value={formatMoney(batch.cogs_cents, batch.currency)} />
                <Stat
                  label="Realized profit"
                  value={formatMoney(batch.realized_profit_cents, batch.currency)}
                  tone={batch.realized_profit_cents < 0 ? "bad" : batch.realized_profit_cents > 0 ? "good" : "plain"}
                />
              </div>

              <Section title="FIFO progress" meta={`${batch.units_remaining.toLocaleString()} on the shelf`}>
                <SoldMeter
                  percent={batch.sold_percent}
                  reversed={reversed}
                  label={`${batch.units_sold} of ${batch.total_items_count} units sold`}
                />
                <p className="mt-2 text-xs text-charcoal/55">
                  <span className="font-semibold tabular-nums text-charcoal">{batch.units_sold.toLocaleString()}</span> of{" "}
                  <span className="tabular-nums">{batch.total_items_count.toLocaleString()}</span> units sold. Sales draw
                  from this batch once older batches of the same product run out.
                </p>
              </Section>

              <section aria-label="Line items" className="border-b border-line">
                <h3 className="flex items-baseline justify-between px-5 pb-3 pt-5 text-[13px] font-semibold">
                  Line items
                  <span className="text-xs font-medium text-charcoal/45">
                    {batch.line_count} line{batch.line_count === 1 ? "" : "s"}
                  </span>
                </h3>
                <div className="overflow-x-auto">
                  <table className={`w-full text-left text-[13px] ${editing ? "min-w-[640px]" : "min-w-[520px]"}`}>
                    <thead>
                      <tr className="border-y border-line bg-[#f8fafc] text-[11px] font-semibold uppercase tracking-wider text-charcoal/45">
                        <th className="py-2 pl-5 pr-2 font-semibold">Product</th>
                        <th className="w-24 px-2 py-2 text-right font-semibold">Units</th>
                        <th className="w-28 px-2 py-2 text-right font-semibold">Unit cost</th>
                        <th className="w-28 px-2 py-2 text-right font-semibold">Price</th>
                        <th className="w-28 py-2 pl-2 pr-5 text-right font-semibold">{editing ? "Expiry" : "Profit"}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line/70">
                      {batch.items.map((item) => {
                        const draft = drafts[item.id];
                        const consumed = item.quantity_imported - item.quantity_remaining;
                        return (
                          <tr key={item.id} className="align-top">
                            <td className="py-2.5 pl-5 pr-2">
                              <span className="block truncate font-medium">{item.product_name}</span>
                              <span className="block font-mono text-[11px] text-charcoal/45">{item.sku}</span>
                              {item.is_serialized ? (
                                <span className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-charcoal/55">
                                  <Smartphone size={11} aria-hidden="true" />
                                  {item.serials_last4.slice(0, 6).map((last4) => (
                                    <span key={last4} className="rounded bg-charcoal/[0.05] px-1 font-mono">
                                      ••{last4}
                                    </span>
                                  ))}
                                  {item.serial_count > 6 ? `+${item.serial_count - 6}` : null}
                                </span>
                              ) : null}
                            </td>
                            <td className="px-2 py-2.5 text-right tabular-nums">
                              {editing && draft ? (
                                <>
                                  <input
                                    aria-label={`Units imported for ${item.product_name}`}
                                    inputMode="numeric"
                                    value={draft.quantity}
                                    disabled={!item.editable_quantity}
                                    title={item.editable_quantity ? undefined : "IMEI lines change by re-import"}
                                    onChange={(event) =>
                                      setDraft(item.id, { quantity: event.target.value.replace(/\D/g, "") })
                                    }
                                    className={editInput}
                                  />
                                  {consumed ? (
                                    <span className="mt-0.5 block text-[10px] text-charcoal/50">min {consumed}</span>
                                  ) : null}
                                </>
                              ) : (
                                <>
                                  <span className="font-semibold">{item.quantity_remaining}</span>
                                  <span className="text-charcoal/40"> / {item.quantity_imported}</span>
                                  {item.quantity_sold ? (
                                    <span className="block text-[11px] text-charcoal/45">{item.quantity_sold} sold</span>
                                  ) : null}
                                </>
                              )}
                            </td>
                            <td className="px-2 py-2.5 text-right tabular-nums">
                              {editing && draft ? (
                                <input
                                  aria-label={`Unit cost for ${item.product_name}`}
                                  inputMode="decimal"
                                  value={draft.cost}
                                  onChange={(event) => setDraft(item.id, { cost: event.target.value })}
                                  className={editInput}
                                />
                              ) : (
                                formatMoney(item.purchase_cost_per_unit, batch.currency)
                              )}
                            </td>
                            <td className="px-2 py-2.5 text-right tabular-nums">
                              {editing && draft ? (
                                <input
                                  aria-label={`Selling price for ${item.product_name}`}
                                  inputMode="decimal"
                                  value={draft.price}
                                  onChange={(event) => setDraft(item.id, { price: event.target.value })}
                                  className={editInput}
                                />
                              ) : (
                                <>
                                  {formatMoney(item.selling_price_per_unit, batch.currency)}
                                  {item.master_price_cents !== item.selling_price_per_unit ? (
                                    <span className="block text-[11px] text-charcoal/45">
                                      Master {formatMoney(item.master_price_cents, batch.currency)}
                                    </span>
                                  ) : null}
                                </>
                              )}
                            </td>
                            <td className="py-2.5 pl-2 pr-5 text-right tabular-nums">
                              {editing && draft ? (
                                <DateInput
                                  aria-label={`Expiry date for ${item.product_name}`}
                                  value={draft.expiry}
                                  onChange={(event) => setDraft(item.id, { expiry: event.target.value })}
                                  className={`${editInput} text-left`}
                                />
                              ) : (
                                <span
                                  className={`font-semibold ${
                                    item.realized_profit_cents < 0
                                      ? "text-red-600"
                                      : item.realized_profit_cents > 0
                                        ? "text-emerald-600"
                                        : ""
                                  }`}
                                >
                                  {item.quantity_sold ? formatMoney(item.realized_profit_cents, batch.currency) : "—"}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              {editing ? (
                <section aria-label="Save corrections" className="space-y-3 border-b border-line bg-accent/[0.03] px-5 py-5">
                  <Toggle
                    label="Apply changed selling prices to the master catalog"
                    description="Off: only this batch's recorded price changes."
                    checked={applyToMaster}
                    onChange={setApplyToMaster}
                  />
                  <label className="block text-[13px] font-medium">
                    Reason (optional)
                    <input
                      value={reason}
                      maxLength={500}
                      onChange={(event) => setReason(event.target.value)}
                      placeholder="e.g. Supplier credit note CN-204"
                      className="mt-1.5 h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-normal focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                    />
                  </label>
                  <p className="text-xs text-charcoal/55">
                    Cost corrections re-cost units already sold from this batch, so realized profit stays accurate.
                    Units can only be reduced down to what has already left the batch.
                  </p>
                  <div className="flex flex-wrap justify-end gap-3">
                    <GhostButton disabled={saving} onClick={() => setEditing(false)}>
                      Cancel
                    </GhostButton>
                    <PrimaryButton disabled={saving || pending.length === 0} onClick={() => void save()}>
                      {saving ? "Saving…" : `Save ${pending.length || ""} change${pending.length === 1 ? "" : "s"}`}
                    </PrimaryButton>
                  </div>
                </section>
              ) : null}

              <Section title="Sold from this batch" meta="FIFO">
                {batch.sales.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-line px-4 py-5 text-center text-[13px] text-charcoal/50">
                    No sales have drawn from this batch yet.
                  </p>
                ) : (
                  <ul className="-mx-5 divide-y divide-line/70 border-y border-line">
                    {batch.sales.map((sale) => (
                      <li key={`${sale.sale_item_id}-${sale.unit_cost_cents}`} className="flex items-center gap-3 px-5 py-2.5">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{sale.product_name}</span>
                          <span className="block text-xs text-charcoal/50">
                            <span className="font-mono">#{sale.sale_id.slice(0, 8).toUpperCase()}</span> ·{" "}
                            {formatDay(sale.sold_at)} · {sale.quantity} × {formatMoney(sale.unit_sale_cents, batch.currency)}
                            {sale.returned ? ` · ${sale.returned} returned` : ""}
                          </span>
                        </span>
                        <span
                          className={`shrink-0 text-[13px] font-semibold tabular-nums ${
                            sale.profit_cents < 0 ? "text-red-600" : "text-emerald-600"
                          }`}
                        >
                          {sale.profit_cents >= 0 ? "+" : ""}
                          {formatMoney(sale.profit_cents, batch.currency)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              <Section title="Audit notes">
                <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[13px] before:top-2 before:w-px before:bg-line">
                  {auditEntries(batch).map((entry) => (
                    <li key={entry.title} className="relative flex gap-3">
                      <span
                        className={`relative z-[1] flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-1 ${toneStyles[entry.tone]}`}
                      >
                        <entry.icon size={13} aria-hidden="true" />
                      </span>
                      <div className="min-w-0 pt-0.5">
                        <p className="text-[13px] font-semibold">
                          {entry.title}
                          {entry.at ? (
                            <span className="ml-2 font-normal text-charcoal/45">
                              {formatDay(entry.at)} {formatTime(entry.at)}
                            </span>
                          ) : null}
                        </p>
                        {entry.body ? <p className="mt-0.5 break-words text-xs text-charcoal/60">{entry.body}</p> : null}
                      </div>
                    </li>
                  ))}
                </ol>
                {canReadAudit ? (
                  <Link
                    to="/settings/audit-logs"
                    className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:underline"
                  >
                    <ScrollText size={13} aria-hidden="true" /> Cost and price corrections are in the audit trail
                  </Link>
                ) : null}
              </Section>
            </>
          )}
          {error ? (
            <div className="px-5 pb-5">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
      </aside>
      {rollingBack && batch ? (
        <RollbackModal
          batch={batch}
          onClose={() => setRollingBack(false)}
          onDone={(result) => {
            setRollingBack(false);
            onRolledBack(result);
            if (result.status !== "DELETED") void load();
          }}
        />
      ) : null}
    </>
  );
}
