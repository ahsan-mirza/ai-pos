import type { AcceptedCurrency } from "@ai-pos/shared-types";
import { Coins, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";

const rateText = (micros: number | null) => (micros === null ? "—" : (micros / 1_000_000).toFixed(4));

export function CurrenciesPage() {
  const [rows, setRows] = useState<AcceptedCurrency[]>([]);
  const [adding, setAdding] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const { currency: base } = useCurrency();

  const load = useCallback(async () => {
    try {
      setRows(await apiGet<AcceptedCurrency[]>("/api/v1/currencies"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load currencies."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveRate = async (row: AcceptedCurrency) => {
    const value = Number(drafts[row.code]);
    if (!Number.isFinite(value) || value <= 0) return setError(`Enter how many ${base} one ${row.code} buys.`);
    try {
      setRows(await apiPut<AcceptedCurrency[]>(`/api/v1/currencies/${row.code}/rate`, { rate_micros: Math.round(value * 1_000_000) }));
      setDrafts((current) => ({ ...current, [row.code]: "" }));
      setToast(`${row.code} rate saved. Registers use it after their next refresh.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the rate."));
    }
  };

  const toggle = async (row: AcceptedCurrency, active: boolean) => {
    try {
      setRows(await apiPost<AcceptedCurrency[]>("/api/v1/currencies", { code: row.code, is_active: active }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the currency."));
    }
  };

  const sync = async () => {
    try {
      setRows(await apiPost<AcceptedCurrency[]>("/api/v1/currencies/sync", {}));
      setToast("Rates refreshed from the provider.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not refresh rates."));
    }
  };

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Business currency</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{base || "—"}</p>
          <p className="mt-2 text-xs text-white/50">Prices, reports and change are in this currency</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Foreign cash accepted</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.filter((row) => row.is_active && row.rate_micros).length}</p>
          <p className="mt-2 text-xs text-white/80">Each counted in its own drawer at close</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Rates set manually</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.filter((row) => row.source === "manual").length}</p>
          <p className="mt-2 text-xs text-charcoal/50">The rest follow the daily provider sync</p>
        </article>
      </div>
      <ErrorNote message={error} />
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Foreign currencies</h2>
            <p className="text-sm text-charcoal/60">
              Registers convert at these rates and give change in {base || "the business currency"}.
            </p>
          </div>
          <div className="flex gap-3">
            <GhostButton onClick={() => void sync()}>
              <RefreshCw size={15} aria-hidden="true" className="-ml-1 mr-2" /> Sync rates
            </GhostButton>
            <PrimaryButton onClick={() => setAdding(true)}>
              <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" /> Add currency
            </PrimaryButton>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Currency</th>
                <th className="pb-3 text-right font-medium">1 unit = {base}</th>
                <th className="pb-3 pl-6 font-medium">Updated</th>
                <th className="pb-3 font-medium">New rate</th>
                <th className="pb-3 font-medium">Accept</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code} className={`border-t border-line ${row.is_active ? "" : "opacity-60"}`}>
                  <td className="py-3">
                    <span className="flex items-center gap-2">
                      <Coins size={16} aria-hidden="true" className="text-charcoal/50" />
                      <span className="font-semibold">{row.code}</span>
                      <span className="text-charcoal/50">{row.name}</span>
                    </span>
                  </td>
                  <td className="py-3 text-right text-lg font-semibold tabular-nums">{rateText(row.rate_micros)}</td>
                  <td className="py-3 pl-6 text-charcoal/70">
                    {row.effective_at ? `${formatDate(row.effective_at)} · ${row.source}` : "No rate yet"}
                  </td>
                  <td className="py-3">
                    <form
                      className="flex gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void saveRate(row);
                      }}
                    >
                      <input
                        inputMode="decimal"
                        aria-label={`New ${row.code} rate`}
                        value={drafts[row.code] ?? ""}
                        onChange={(event) => setDrafts((current) => ({ ...current, [row.code]: event.target.value }))}
                        placeholder={rateText(row.rate_micros)}
                        className="h-9 w-28 rounded-xl border border-line bg-surface px-3 text-right tabular-nums focus:border-accent focus:outline-none"
                      />
                      <button type="submit" className="rounded-full bg-charcoal px-3 text-xs font-semibold text-white">
                        Set
                      </button>
                    </form>
                  </td>
                  <td className="py-3">
                    <Toggle label="" checked={row.is_active} onChange={(value) => void toggle(row, value)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Only the business currency is accepted.</p> : null}
        </div>
      </div>
      {adding ? (
        <AddCurrencyModal
          base={base}
          onClose={() => setAdding(false)}
          onSaved={(next) => {
            setRows(next);
            setAdding(false);
            setToast("Currency added.");
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function AddCurrencyModal({ base, onClose, onSaved }: { base: string; onClose: () => void; onSaved: (rows: AcceptedCurrency[]) => void }) {
  const [code, setCode] = useState("USD");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const value = rate.trim() === "" ? null : Number(rate);
    if (value !== null && (!Number.isFinite(value) || value <= 0)) return setError("Enter a positive rate, or leave it for the sync.");
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await apiPost<AcceptedCurrency[]>("/api/v1/currencies", {
          code: code.trim().toUpperCase(),
          rate_micros: value === null ? null : Math.round(value * 1_000_000),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not add the currency."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Accept a foreign currency"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Adding…" : "Add"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField label="ISO code" value={code} maxLength={3} className="font-mono uppercase" onChange={(event) => setCode(event.target.value)} />
        <TextField
          label={`1 ${code.toUpperCase() || "unit"} = ? ${base}`}
          inputMode="decimal"
          value={rate}
          placeholder="3.6725"
          className="tabular-nums"
          onChange={(event) => setRate(event.target.value)}
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
