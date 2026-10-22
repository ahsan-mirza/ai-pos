import {
  formatMoney,
  type ReplenishmentAcceptResult,
  type ReplenishmentRun,
  type ReplenishmentSuggestion,
  type SeasonalEvent,
  type SupplierLeadTime,
  type Weekday,
} from "@ai-pos/shared-types";
import { CalendarRange, RefreshCw, Trash2, Truck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { formatDate, storeOptions, useStores } from "./shared";

export function ReplenishmentPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const navigate = useNavigate();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [run, setRun] = useState<ReplenishmentRun | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [events, setEvents] = useState<SeasonalEvent[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierLeadTime[]>([]);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<"event" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  useEffect(() => {
    if (!storeId && stores.length > 0) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [storeId, stores]);

  const adopt = useCallback((next: ReplenishmentRun | null) => {
    setRun(next);
    const pending = (next?.suggestions ?? []).filter((row) => row.status === "PENDING");
    setQuantities(Object.fromEntries(pending.map((row) => [row.id, String(row.suggested_qty)])));
    setSelected(new Set(pending.map((row) => row.id)));
  }, []);

  const load = useCallback(async () => {
    try {
      const [nextEvents, nextSuppliers] = await Promise.all([
        apiGet<SeasonalEvent[]>("/api/v1/replenishment/events"),
        apiGet<SupplierLeadTime[]>("/api/v1/replenishment/suppliers"),
      ]);
      setEvents(nextEvents);
      setSuppliers(nextSuppliers);
      if (storeId) adopt(await apiGet<ReplenishmentRun | null>(`/api/v1/replenishment/runs/latest?store_id=${storeId}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load replenishment."));
    }
  }, [adopt, storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setBusy(true);
    try {
      adopt(await apiPost<ReplenishmentRun>("/api/v1/replenishment/runs", { store_id: storeId, review_days: 7 }));
      setToast("Fresh suggestions from the latest sales.");
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build suggestions."));
    } finally {
      setBusy(false);
    }
  };

  const accept = async () => {
    if (!run) return;
    const lines = [...selected].map((id) => ({ id, quantity: Number(quantities[id] ?? 0) || 0 })).filter((line) => line.quantity > 0);
    if (lines.length === 0) return setError("Tick at least one suggestion with a quantity.");
    setBusy(true);
    try {
      const result = await apiPost<ReplenishmentAcceptResult>(`/api/v1/replenishment/runs/${run.id}/accept`, { lines });
      adopt(result.run);
      setToast(
        `${result.purchase_order_ids.length} draft purchase order${result.purchase_order_ids.length === 1 ? "" : "s"} and ${result.transfer_ids.length} transfer request${result.transfer_ids.length === 1 ? "" : "s"} created.`,
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not create the orders."));
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async (row: ReplenishmentSuggestion) => {
    try {
      adopt(await apiPost<ReplenishmentRun>(`/api/v1/replenishment/suggestions/${row.id}/dismiss`, {}));
    } catch (caught) {
      setError(errorMessage(caught, "Could not dismiss the suggestion."));
    }
  };

  const groups = useMemo(() => {
    const map = new Map<string, ReplenishmentSuggestion[]>();
    for (const row of run?.suggestions ?? []) {
      const key = row.source === "TRANSFER" ? `Transfer from ${row.from_store_code ?? "branch"}` : (row.supplier_name ?? "Supplier to be confirmed");
      map.set(key, [...(map.get(key) ?? []), row]);
    }
    return [...map.entries()];
  }, [run]);

  const selectedValue = (run?.suggestions ?? [])
    .filter((row) => selected.has(row.id) && row.source === "PURCHASE")
    .reduce((sum, row) => sum + (Number(quantities[row.id]) || 0) * row.unit_cost_cents, 0);

  return (
    <section className="space-y-4 p-4 md:p-6">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">To reorder</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {(run?.suggestions ?? []).filter((row) => row.status === "PENDING").length}
          </p>
          <p className="mt-2 text-xs text-white/50">{run ? `Planned ${formatDate(run.created_at)}` : "No plan yet for this branch"}</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Selected purchase value</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(selectedValue, currency)}</p>
          <p className="mt-2 text-xs text-white/80">At the latest purchase cost</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Seasonal events ahead</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {events.filter((row) => row.is_active && row.ends_on >= new Date().toISOString().slice(0, 10)).length}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">Raise forecasts on their days</p>
        </article>
      </div>
      <ErrorNote message={error} />

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Reorder suggestions</h2>
            <p className="text-sm text-charcoal/60">
              Forecast covers supplier lead time plus a week, with safety stock for uneven demand. Surplus at other branches is moved first.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {user?.store_id ? null : (
              <FilterSelect label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} className="w-56" />
            )}
            <GhostButton disabled={busy || !storeId} onClick={() => void generate()}>
              <RefreshCw size={15} aria-hidden="true" className={`-ml-1 mr-2 ${busy ? "animate-spin" : ""}`} /> Recalculate
            </GhostButton>
            <PrimaryButton disabled={busy || selected.size === 0} onClick={() => void accept()}>
              <Truck size={16} aria-hidden="true" className="-ml-1 mr-2" /> Create orders
            </PrimaryButton>
          </div>
        </div>
        {groups.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-charcoal/60">
            {run ? "Nothing needs reordering at this branch." : "Recalculate to plan this branch's reorders."}
          </p>
        ) : null}
        <div className="space-y-5">
          {groups.map(([label, rows]) => (
            <div key={label}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-charcoal/50">{label}</h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                    <tr>
                      <th className="w-8 pb-2" />
                      <th className="pb-2 font-medium">Product</th>
                      <th className="pb-2 text-right font-medium">On hand</th>
                      <th className="pb-2 text-right font-medium">On order</th>
                      <th className="pb-2 text-right font-medium">Per day · model</th>
                      <th className="pb-2 text-right font-medium">Need (incl. safety)</th>
                      <th className="pb-2 text-right font-medium">Order</th>
                      <th className="pb-2 pl-4 font-medium">Status</th>
                      <th className="w-10 pb-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const pending = row.status === "PENDING";
                      return (
                        <tr key={row.id} className={`border-t border-line ${pending ? "" : "opacity-60"}`}>
                          <td className="py-2.5">
                            {pending ? (
                              <input
                                type="checkbox"
                                aria-label={`Include ${row.product_name}`}
                                checked={selected.has(row.id)}
                                onChange={(event) =>
                                  setSelected((current) => {
                                    const next = new Set(current);
                                    if (event.target.checked) next.add(row.id);
                                    else next.delete(row.id);
                                    return next;
                                  })
                                }
                                className="h-4 w-4 accent-accent"
                              />
                            ) : null}
                          </td>
                          <td className="py-2.5">
                            <span className="block font-medium">{row.product_name}</span>
                            <span className="block text-xs text-charcoal/50">
                              {row.sku} · {row.lead_time_days}d lead
                              {row.seasonal_note ? <span className="ml-1 font-semibold text-accent">· {row.seasonal_note}</span> : null}
                              {row.terms_note ? <span className="ml-1 text-charcoal/70">· {row.terms_note}</span> : null}
                            </span>
                          </td>
                          <td className="py-2.5 text-right tabular-nums">{row.on_hand}</td>
                          <td className="py-2.5 text-right tabular-nums">{row.on_order}</td>
                          <td className="py-2.5 text-right tabular-nums">
                            {row.daily_rate.toFixed(1)}
                            {row.forecast_method_label ? (
                              <span
                                className="block text-[11px] text-charcoal/50"
                                title={
                                  row.forecast_accuracy !== null && row.forecast_accuracy !== undefined
                                    ? `Picked by backtest on the last 28 days: ${Math.round(row.forecast_accuracy * 100)}% accurate`
                                    : "Too little history to backtest; using the weighted average"
                                }
                              >
                                {row.forecast_method_label}
                                {row.trend_pct_week ? ` ${row.trend_pct_week > 0 ? "↑" : "↓"}${Math.abs(row.trend_pct_week)}%/wk` : ""}
                                {row.forecast_accuracy !== null && row.forecast_accuracy !== undefined
                                  ? ` · ${Math.round(row.forecast_accuracy * 100)}%`
                                  : ""}
                              </span>
                            ) : null}
                          </td>
                          <td className="py-2.5 text-right tabular-nums">
                            {row.forecast_units}
                            <span className="text-charcoal/50"> + {row.safety_stock}</span>
                          </td>
                          <td className="py-2.5 text-right">
                            {pending ? (
                              <input
                                inputMode="numeric"
                                aria-label={`Quantity for ${row.product_name}`}
                                value={quantities[row.id] ?? ""}
                                onChange={(event) => setQuantities((current) => ({ ...current, [row.id]: event.target.value.replace(/\D/g, "") }))}
                                className="h-9 w-20 rounded-xl border border-line bg-surface px-2 text-right font-semibold tabular-nums focus:border-accent focus:outline-none"
                              />
                            ) : (
                              <span className="font-semibold tabular-nums">{row.suggested_qty}</span>
                            )}
                          </td>
                          <td className="py-2.5 pl-4">
                            {row.status === "ACCEPTED" ? (
                              <button
                                type="button"
                                onClick={() => navigate(row.purchase_order_id ? "/inventory/purchase-orders" : "/inventory/transfers")}
                                className="rounded-full bg-charcoal px-2.5 py-0.5 text-[11px] font-semibold text-white"
                              >
                                {row.purchase_order_id ? "Draft PO" : "Transfer"}
                              </button>
                            ) : row.status === "DISMISSED" ? (
                              <span className="text-xs text-charcoal/50">Dismissed</span>
                            ) : (
                              <span className="text-xs text-charcoal/60">{formatMoney(row.unit_cost_cents, currency)} each</span>
                            )}
                          </td>
                          <td className="py-2.5">
                            {pending ? (
                              <button
                                type="button"
                                aria-label={`Dismiss ${row.product_name}`}
                                onClick={() => void dismiss(row)}
                                className="flex h-8 w-8 items-center justify-center rounded-full text-charcoal/40 hover:bg-charcoal/10 hover:text-charcoal"
                              >
                                <Trash2 size={14} aria-hidden="true" />
                              </button>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <article className="rounded-card border border-line bg-white p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Seasonal events</h2>
              <p className="text-sm text-charcoal/60">Ramadan, Eid, back to school, DSF: demand multipliers on their days.</p>
            </div>
            <PrimaryButton onClick={() => setDialog("event")}>
              <CalendarRange size={16} aria-hidden="true" className="-ml-1 mr-2" /> Add
            </PrimaryButton>
          </div>
          <ul className="mt-4 space-y-2">
            {events.map((row) => (
              <li key={row.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{row.name}</p>
                  <p className="text-xs text-charcoal/50 tabular-nums">
                    {row.starts_on} to {row.ends_on}
                  </p>
                </div>
                <span className="text-lg font-semibold tabular-nums">×{(row.uplift_bps / 10_000).toFixed(2)}</span>
                <button
                  type="button"
                  aria-label={`Remove ${row.name}`}
                  onClick={() =>
                    void apiDelete(`/api/v1/replenishment/events/${row.id}`)
                      .then(() => load())
                      .catch((caught: unknown) => setError(errorMessage(caught, "Could not remove the event.")))
                  }
                  className="flex h-8 w-8 items-center justify-center rounded-full text-charcoal/40 hover:bg-charcoal/10 hover:text-charcoal"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
            {events.length === 0 ? (
              <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-charcoal/60">No events yet.</li>
            ) : null}
          </ul>
        </article>
        <article className="rounded-card bg-charcoal p-6 text-white">
          <h2 className="text-xl font-semibold">Supplier terms</h2>
          <p className="text-sm text-white/60">
            Lead time, minimum order, case size and the days each supplier takes orders. Suggestions round up to these.
          </p>
          <ul className="mt-4 space-y-2">
            {suppliers.map((row) => (
              <SupplierTermsRow
                key={row.id}
                supplier={row}
                onSaved={(next) => {
                  setSuppliers(next);
                  setToast(`${row.name} terms saved. Recalculate to apply them.`);
                }}
                onError={(text) => setError(text)}
              />
            ))}
            {suppliers.length === 0 ? (
              <li className="rounded-2xl bg-white/5 p-6 text-center text-sm text-white/60">Suppliers appear once batches are imported.</li>
            ) : null}
          </ul>
        </article>
      </div>
      {dialog === "event" ? (
        <EventModal
          onClose={() => setDialog(null)}
          onSaved={(next) => {
            setEvents(next);
            setDialog(null);
            setToast("Seasonal event saved. Recalculate to apply it.");
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

const WEEKDAYS: Weekday[] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

function SupplierTermsRow({
  supplier,
  onSaved,
  onError,
}: {
  supplier: SupplierLeadTime;
  onSaved: (next: SupplierLeadTime[]) => void;
  onError: (text: string) => void;
}) {
  const [lead, setLead] = useState(String(supplier.lead_time_days));
  const [moq, setMoq] = useState(String(supplier.moq));
  const [pack, setPack] = useState(String(supplier.pack_size));
  const [days, setDays] = useState<Weekday[]>(supplier.order_days);
  const [busy, setBusy] = useState(false);
  const dirty =
    lead !== String(supplier.lead_time_days) ||
    moq !== String(supplier.moq) ||
    pack !== String(supplier.pack_size) ||
    days.join() !== supplier.order_days.join();

  const save = async () => {
    const values = [Number(lead), Number(moq), Number(pack)];
    if (values.some((value) => !Number.isInteger(value)) || values[1]! < 1 || values[2]! < 1 || values[0]! < 0) {
      return onError("Lead time, minimum order and case size must be whole numbers (minimum and case at least 1).");
    }
    setBusy(true);
    try {
      onSaved(
        await apiPut<SupplierLeadTime[]>(`/api/v1/replenishment/suppliers/${supplier.id}/terms`, {
          lead_time_days: values[0],
          moq: values[1],
          pack_size: values[2],
          order_days: days,
        }),
      );
    } catch (caught) {
      onError(errorMessage(caught, "Could not save the supplier terms."));
    } finally {
      setBusy(false);
    }
  };

  const field = (label: string, value: string, set: (next: string) => void, suffix: string) => (
    <label className="flex items-center gap-1.5 rounded-xl bg-white/5 px-2.5 py-1.5 text-xs text-white/60">
      {label}
      <input
        inputMode="numeric"
        aria-label={`${label} for ${supplier.name}`}
        value={value}
        onChange={(event) => set(event.target.value.replace(/\D/g, ""))}
        className="w-12 bg-transparent text-right text-sm font-semibold tabular-nums text-white focus:outline-none"
      />
      {suffix}
    </label>
  );

  return (
    <li className="rounded-2xl bg-white/5 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">{supplier.name}</p>
          <p className="font-mono text-xs text-white/50">{supplier.code}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {field("Lead", lead, setLead, "days")}
          {field("Min", moq, setMoq, "units")}
          {field("Case", pack, setPack, "units")}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label={`Order days for ${supplier.name}`}>
          {WEEKDAYS.map((day) => {
            const on = days.includes(day);
            return (
              <button
                key={day}
                type="button"
                aria-pressed={on}
                onClick={() => setDays(on ? days.filter((value) => value !== day) : WEEKDAYS.filter((value) => value === day || days.includes(value)))}
                className={`h-7 rounded-full px-2.5 text-[11px] font-semibold ${on ? "bg-accent text-white" : "bg-white/10 text-white/60 hover:text-white"}`}
              >
                {day.slice(0, 2)}
              </button>
            );
          })}
          <span className="self-center pl-1 text-[11px] text-white/40">{days.length === 0 ? "Orders any day" : ""}</span>
        </div>
        {dirty ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void save()}
            className="h-8 rounded-full bg-accent px-4 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        ) : null}
      </div>
    </li>
  );
}

function EventModal({ onClose, onSaved }: { onClose: () => void; onSaved: (events: SeasonalEvent[]) => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [name, setName] = useState("Ramadan");
  const [starts, setStarts] = useState(today);
  const [ends, setEnds] = useState(today);
  const [uplift, setUplift] = useState("130");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const percent = Number(uplift);
    if (!Number.isFinite(percent) || percent < 0) return setError("Enter demand as a percentage of normal, e.g. 130.");
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await apiPost<SeasonalEvent[]>("/api/v1/replenishment/events", {
          name: name.trim(),
          starts_on: starts,
          ends_on: ends,
          uplift_bps: Math.round(percent * 100),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the event."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Seasonal event"
      subtitle="Forecast demand on these days is multiplied by the percentage."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Starts" type="date" value={starts} onChange={(event) => setStarts(event.target.value)} />
          <TextField label="Ends" type="date" value={ends} onChange={(event) => setEnds(event.target.value)} />
        </div>
        <TextField
          label="Demand (% of normal)"
          inputMode="decimal"
          value={uplift}
          className="tabular-nums"
          onChange={(event) => setUplift(event.target.value)}
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
