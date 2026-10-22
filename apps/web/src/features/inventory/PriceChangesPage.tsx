import {
  formatMoney,
  Permission,
  PRICE_TIER_LABELS,
  type PriceChange,
  type PriceChangeStatus,
  type PriceTier,
} from "@ai-pos/shared-types";
import { CalendarClock, ChevronDown, ChevronRight, Plus, Printer, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ProductPicker } from "../../components/ui/ProductPicker";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { priceListsApi } from "./priceListsApi";

const TIERS: PriceTier[] = ["TIER_1", "TIER_2", "DISTRIBUTOR"];

const STATUS_TONE: Record<PriceChangeStatus, string> = {
  SCHEDULED: "bg-accent text-white",
  APPLIED: "bg-charcoal text-white",
  CANCELLED: "bg-white text-charcoal/50 ring-1 ring-line",
};

function when(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function PriceChangesPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const [changes, setChanges] = useState<PriceChange[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const manage = can(Permission.PortalPricingManage);

  const load = useCallback(async () => {
    try {
      setChanges(await priceListsApi.changes());
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load price changes."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (change: PriceChange, action: "apply" | "cancel") => {
    if (action === "apply" && !window.confirm(`Apply ${change.name} now? New prices reach registers on their next sync.`)) return;
    setBusy(change.id);
    try {
      const next = await (action === "apply" ? priceListsApi.applyChange(change.id) : priceListsApi.cancelChange(change.id));
      setChanges((current) => current?.map((row) => (row.id === next.id ? next : row)) ?? null);
      setToast(action === "apply" ? `${next.name} applied. Print the new shelf labels.` : `${next.name} cancelled.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the price change."));
    } finally {
      setBusy(null);
    }
  };

  const scheduled = changes?.filter((row) => row.status === "SCHEDULED") ?? [];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Scheduled</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{scheduled.length}</p>
          <p className="mt-2 text-xs text-white/50">Applied automatically at their time</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Next change</p>
          <p className="mt-4 text-2xl font-semibold">{scheduled.length ? when(scheduled[scheduled.length - 1]!.run_at) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">{scheduled.length ? scheduled[scheduled.length - 1]!.name : "Nothing queued"}</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Products affected</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{scheduled.reduce((sum, row) => sum + row.lines.length, 0)}</p>
          <p className="mt-2 text-xs text-charcoal/50">Across scheduled changes</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Scheduled price changes</h2>
            <p className="text-sm text-charcoal/60">
              Prepare new retail and tier prices ahead of time. Each change is audited and keeps the old prices.
            </p>
          </div>
          {manage ? (
            <PrimaryButton onClick={() => setCreating(true)}>
              <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> New price change
            </PrimaryButton>
          ) : null}
        </div>
        <ErrorNote message={error} />
        <ul className="divide-y divide-line">
          {(changes ?? []).map((change) => (
            <li key={change.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setOpen(open === change.id ? null : change.id)}
                  className="flex items-center gap-2 text-left"
                >
                  {open === change.id ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                  <span>
                    <span className="block font-medium">{change.name}</span>
                    <span className="block text-xs text-charcoal/60">
                      {change.status === "APPLIED" && change.applied_at ? `Applied ${when(change.applied_at)}` : `Runs ${when(change.run_at)}`} ·{" "}
                      {change.lines.length} products{change.created_by_name ? ` · by ${change.created_by_name}` : ""}
                    </span>
                  </span>
                </button>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_TONE[change.status]}`}>
                    {change.status.toLowerCase()}
                  </span>
                  {change.status === "APPLIED" ? (
                    <GhostButton onClick={() => void priceListsApi.changeLabels(change.id).catch((caught: unknown) => setError(errorMessage(caught, "Could not print.")))}>
                      <Printer size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Labels
                    </GhostButton>
                  ) : null}
                  {change.status === "SCHEDULED" && manage ? (
                    <>
                      <GhostButton disabled={busy === change.id} onClick={() => void act(change, "cancel")}>
                        Cancel
                      </GhostButton>
                      <PrimaryButton disabled={busy === change.id} onClick={() => void act(change, "apply")}>
                        Apply now
                      </PrimaryButton>
                    </>
                  ) : null}
                </div>
              </div>
              {open === change.id ? (
                <table className="mt-3 w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                    <tr>
                      <th className="pb-2 font-medium">Product</th>
                      <th className="pb-2 text-right font-medium">Retail</th>
                      <th className="pb-2 pl-6 font-medium">Tier prices</th>
                    </tr>
                  </thead>
                  <tbody>
                    {change.lines.map((line) => {
                      const before = change.status === "APPLIED" ? line.previous_retail_cents : line.current_retail_cents;
                      const tiersBefore = change.status === "APPLIED" ? (line.previous_tier_prices ?? {}) : line.current_tier_prices;
                      return (
                        <tr key={line.product_id} className="border-t border-line">
                          <td className="py-2">
                            <span className="block font-medium">{line.name}</span>
                            <span className="block font-mono text-xs text-charcoal/50">{line.sku}</span>
                          </td>
                          <td className="py-2 text-right tabular-nums">
                            {line.retail_price_cents === null ? (
                              <span className="text-charcoal/40">unchanged</span>
                            ) : (
                              <>
                                <span className="text-charcoal/50 line-through">{formatMoney(before ?? 0, currency)}</span>{" "}
                                <span className="font-semibold">{formatMoney(line.retail_price_cents, currency)}</span>
                              </>
                            )}
                          </td>
                          <td className="py-2 pl-6 text-xs tabular-nums">
                            {Object.entries(line.tier_prices).map(([tier, cents]) => (
                              <span key={tier} className="mr-3 inline-block">
                                {PRICE_TIER_LABELS[tier as PriceTier] ?? tier}: {tiersBefore[tier] !== undefined ? `${formatMoney(tiersBefore[tier]!, currency)} → ` : ""}
                                <span className="font-semibold">{formatMoney(cents, currency)}</span>
                              </span>
                            ))}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : null}
            </li>
          ))}
        </ul>
        {changes && changes.length === 0 ? (
          <p className="flex items-center gap-2 py-8 text-sm text-charcoal/60">
            <CalendarClock size={16} aria-hidden="true" /> No price changes yet.
          </p>
        ) : null}
      </div>
      {creating ? (
        <NewChangeModal
          currency={currency}
          onClose={() => setCreating(false)}
          onCreated={(change) => {
            setCreating(false);
            setToast(`${change.name} scheduled for ${when(change.run_at)}.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

interface DraftLine {
  product_id: string;
  name: string;
  retail: number;
  next: string;
  tiers: Partial<Record<PriceTier, string>>;
}

function NewChangeModal({
  currency,
  onClose,
  onCreated,
}: {
  currency: string;
  onClose: () => void;
  onCreated: (change: PriceChange) => void;
}) {
  const tomorrow = new Date(Date.now() + 24 * 3_600_000);
  tomorrow.setHours(6, 0, 0, 0);
  const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  const [name, setName] = useState("");
  const [runAt, setRunAt] = useState(local);
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cents = (value: string | undefined) => (value && value.trim() ? Math.round(Number(value) * 100) : null);

  const save = async () => {
    if (!name.trim()) return setError("Name the price change.");
    const payload = lines.map((line) => ({
      product_id: line.product_id,
      retail_price_cents: cents(line.next),
      tier_prices: Object.fromEntries(
        Object.entries(line.tiers)
          .map(([tier, value]) => [tier, cents(value)] as const)
          .filter((entry): entry is readonly [string, number] => entry[1] !== null),
      ),
    }));
    if (!payload.length || payload.some((line) => line.retail_price_cents === null && Object.keys(line.tier_prices).length === 0)) {
      return setError("Give every product a new retail or tier price.");
    }
    setBusy(true);
    setError(null);
    try {
      onCreated(await priceListsApi.createChange({ name: name.trim(), run_at: new Date(runAt).toISOString(), note: note.trim(), lines: payload }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not schedule the change."));
    } finally {
      setBusy(false);
    }
  };

  const update = (index: number, patch: Partial<DraftLine>) =>
    setLines((current) => current.map((line, at) => (at === index ? { ...line, ...patch } : line)));

  return (
    <Modal
      width="lg"
      title="New price change"
      subtitle="Prices switch over at the time you set; registers pick them up on their next catalogue sync."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Scheduling…" : "Schedule"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Name" value={name} maxLength={120} placeholder="e.g. Supplier price rise" onChange={(event) => setName(event.target.value)} />
          <TextField label="Apply at" type="datetime-local" value={runAt} onChange={(event) => setRunAt(event.target.value)} />
        </div>
        <TextField label="Note (optional)" value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
        <ProductPicker
          onPick={(hit) =>
            setLines((current) =>
              current.some((line) => line.product_id === hit.product.id)
                ? current
                : [...current, { product_id: hit.product.id, name: hit.product.name, retail: hit.product.price_cents, next: "", tiers: {} }],
            )
          }
        />
        {lines.map((line, index) => (
          <div key={line.product_id} className="rounded-2xl border border-line p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <span>
                <span className="block font-medium">{line.name}</span>
                <span className="block text-xs text-charcoal/50">Now {formatMoney(line.retail, currency)} retail</span>
              </span>
              <button
                type="button"
                aria-label={`Remove ${line.name}`}
                onClick={() => setLines((current) => current.filter((_, at) => at !== index))}
                className="text-charcoal/40 hover:text-accent"
              >
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <TextField
                label="New retail"
                inputMode="decimal"
                value={line.next}
                placeholder="—"
                onChange={(event) => update(index, { next: event.target.value.replace(/[^\d.]/g, "") })}
              />
              {TIERS.map((tier) => (
                <TextField
                  key={tier}
                  label={PRICE_TIER_LABELS[tier]}
                  inputMode="decimal"
                  value={line.tiers[tier] ?? ""}
                  placeholder="—"
                  onChange={(event) => update(index, { tiers: { ...line.tiers, [tier]: event.target.value.replace(/[^\d.]/g, "") } })}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
