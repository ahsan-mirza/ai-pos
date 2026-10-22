import {
  Capability,
  RETURNS_PRESETS,
  formatMoney,
  resolvePosPolicy,
  type BusinessSettings,
  type PolicyChoice,
  type PosPolicy,
  type ReturnConditionRule,
} from "@ai-pos/shared-types";
import { Plus, ScrollText, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Select } from "../../components/ui/Select";
import { apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { errorMessage } from "../users/api";

const PRESETS = [
  { value: "electronics", label: "Electronics" },
  { value: "fashion", label: "Fashion" },
  { value: "custom", label: "Custom" },
] as const;

const SERIAL_STATUS = [
  { value: "in_stock", label: "Back to stock" },
  { value: "quarantine", label: "Quarantine" },
  { value: "repair", label: "Send to repair" },
] as const;

/** A stable key for a label the owner typed: lower snake case, starting with a letter, as the API requires. */
function keyOf(label: string, taken: Set<string>): string {
  const base = `r_${label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}`.slice(0, 28) || "r_reason";
  let key = /^[a-z]/.test(base) ? base : `r_${base}`;
  let suffix = 2;
  while (taken.has(key)) key = `${base.slice(0, 26)}_${suffix++}`;
  return key;
}

const percent = (bps: number) => String(bps / 100);
const toBps = (value: string, max: number): number | null => {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const bps = Math.round(Number(trimmed) * 100);
  return bps <= max ? bps : null;
};

function ChoiceList({
  title,
  items,
  locked,
  onChange,
}: {
  title: string;
  items: PolicyChoice[];
  locked: (key: string) => boolean;
  onChange: (items: PolicyChoice[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const label = draft.trim();
    if (!label) return;
    onChange([...items, { key: keyOf(label, new Set(items.map((item) => item.key))), label }]);
    setDraft("");
  };
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">{title}</p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={item.key} className="flex items-center gap-2">
            <input
              aria-label={`${title} ${index + 1}`}
              value={item.label}
              maxLength={60}
              onChange={(event) =>
                onChange(items.map((row, at) => (at === index ? { ...row, label: event.target.value } : row)))
              }
              className="w-full rounded-xl bg-surface px-3 py-2 text-sm focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              type="button"
              aria-label={`Remove ${item.label}`}
              disabled={items.length <= 1 || locked(item.key)}
              onClick={() => onChange(items.filter((_, at) => at !== index))}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent disabled:opacity-30"
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex gap-2">
        <input
          aria-label={`New ${title.toLowerCase()}`}
          placeholder="Add another…"
          value={draft}
          maxLength={60}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          className="w-full rounded-xl border border-dashed border-line px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          aria-label={`Add ${title.toLowerCase()}`}
          disabled={!draft.trim() || items.length >= 20}
          onClick={add}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-charcoal text-white disabled:opacity-30"
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/** Cashier discounts, gift cards and the returns policy: business-wide rules every register caches and enforces. */
export function TillRulesSettings() {
  const { user } = useAuth();
  const { currency, settings, applySettings } = useCurrency();
  const { has } = useCapabilities();
  const [form, setForm] = useState<PosPolicy | null>(null);
  const [saved, setSaved] = useState<string>("");
  const [limit, setLimit] = useState("");
  const [giftMin, setGiftMin] = useState("");
  const [giftMax, setGiftMax] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const businessWide = !user?.store_id;

  const reset = (policy: PosPolicy) => {
    setForm(policy);
    setSaved(JSON.stringify(policy));
    setLimit(percent(policy.discounts.default_limit_bps));
    setGiftMin((policy.gift_cards.min_cents / 100).toFixed(2));
    setGiftMax((policy.gift_cards.max_cents / 100).toFixed(2));
  };

  useEffect(() => {
    if (settings === null || (form !== null && JSON.stringify(form) !== saved)) return;
    reset(resolvePosPolicy(settings.pos_policy));
  }, [settings]);

  if (form === null) return null;

  const limitBps = toBps(limit, 10_000);
  const minCents = toCents(giftMin);
  const maxCents = toCents(giftMax);
  const next: PosPolicy = {
    ...form,
    discounts: { ...form.discounts, default_limit_bps: limitBps ?? form.discounts.default_limit_bps },
    gift_cards: {
      ...form.gift_cards,
      min_cents: minCents ?? form.gift_cards.min_cents,
      max_cents: maxCents ?? form.gift_cards.max_cents,
    },
  };
  const problem =
    limitBps === null
      ? "Enter the default discount limit as a percent from 0 to 100."
      : minCents === null || maxCents === null || minCents < 100
        ? "Enter gift card amounts like 50.00 (at least 1.00)."
        : maxCents < minCents
          ? "The largest gift card must be at least the smallest."
          : form.discounts.reasons.some((reason) => !reason.label.trim()) ||
              form.returns.reasons.some((reason) => !reason.label.trim()) ||
              form.returns.conditions.some((condition) => !condition.label.trim())
            ? "Every reason and condition needs a label."
            : null;
  const changed = JSON.stringify(next) !== saved;
  const returns = form.returns;
  const setReturns = (patch: Partial<PosPolicy["returns"]>) =>
    setForm({ ...form, returns: { ...returns, ...patch, preset: patch.preset ?? "custom" } });
  const setCondition = (index: number, patch: Partial<ReturnConditionRule>) =>
    setReturns({ conditions: returns.conditions.map((row, at) => (at === index ? { ...row, ...patch } : row)) });

  const save = async () => {
    if (problem) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const row = await apiPut<BusinessSettings>("/api/v1/settings/pos-policy", next);
      applySettings(row);
      reset(resolvePosPolicy(row.pos_policy));
      setNotice("Till rules saved. Registers apply them on their next sync.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the till rules."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div id="till-rules" className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <ScrollText size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Till rules</h2>
            <p className="text-sm text-charcoal/60">
              Discounts, gift cards and returns. Every register enforces these, even offline.
            </p>
          </div>
        </div>
        {businessWide ? (
          <PrimaryButton disabled={!changed || busy || problem !== null} onClick={() => void save()}>
            {busy ? "Saving…" : "Save till rules"}
          </PrimaryButton>
        ) : null}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="space-y-4 rounded-2xl border border-line p-4">
          <h3 className="font-semibold">Cashier discounts</h3>
          <TextField
            label="Default limit (%)"
            inputMode="decimal"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            hint="Largest line discount a cashier gives without a manager, unless their role sets its own (Roles page)."
          />
          <ChoiceList
            title="Discount reasons"
            items={form.discounts.reasons}
            locked={() => false}
            onChange={(reasons) => setForm({ ...form, discounts: { ...form.discounts, reasons } })}
          />
        </section>

        {has(Capability.GiftCards) ? (
          <section className="space-y-4 rounded-2xl border border-line p-4">
            <h3 className="font-semibold">Gift cards</h3>
            <div className="grid grid-cols-2 gap-3">
              <TextField label="Smallest card" inputMode="decimal" value={giftMin} onChange={(event) => setGiftMin(event.target.value)} />
              <TextField label="Largest card" inputMode="decimal" value={giftMax} onChange={(event) => setGiftMax(event.target.value)} />
            </div>
            <TextField
              label="Valid for (months)"
              type="number"
              min={1}
              max={120}
              placeholder="Never expires"
              value={form.gift_cards.expiry_months ?? ""}
              onChange={(event) => {
                const months = event.target.value === "" ? null : Math.max(1, Math.min(120, Number(event.target.value)));
                setForm({ ...form, gift_cards: { ...form.gift_cards, expiry_months: months } });
              }}
              hint="Check the consumer rules where you trade before setting an expiry. Leave blank for no expiry."
            />
            {minCents !== null && maxCents !== null ? (
              <p className="text-xs text-charcoal/60">
                Registers sell cards from {formatMoney(minCents, currency)} to {formatMoney(maxCents, currency)}.
              </p>
            ) : null}
          </section>
        ) : null}

        <section className="space-y-4 rounded-2xl border border-line p-4 lg:col-span-2">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-semibold">Returns policy</h3>
              <p className="text-sm text-charcoal/60">
                Refund to the original payment inside the return window, then an exchange or store credit only.
              </p>
            </div>
            <SegmentedControl
              label="Returns preset"
              value={returns.preset}
              options={PRESETS}
              onChange={(preset) =>
                preset === "custom"
                  ? setReturns({ preset: "custom" })
                  : setForm({ ...form, returns: structuredClone(RETURNS_PRESETS[preset]) })
              }
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:max-w-lg">
            <TextField
              label="Refund window (days)"
              type="number"
              min={0}
              max={365}
              value={returns.window_days}
              onChange={(event) => setReturns({ window_days: Math.max(0, Math.min(365, Number(event.target.value) || 0)) })}
            />
            <TextField
              label="Exchange-only days after"
              type="number"
              min={0}
              max={365}
              value={returns.exchange_window_days}
              onChange={(event) =>
                setReturns({ exchange_window_days: Math.max(0, Math.min(365, Number(event.target.value) || 0)) })
              }
            />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-2 font-medium">Condition</th>
                  <th className="pb-2 font-medium">Restock</th>
                  <th className="pb-2 font-medium">Fee %</th>
                  <th className="pb-2 font-medium">Serialized unit goes to</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {returns.conditions.map((condition, index) => (
                  <tr key={condition.key} className="border-t border-line">
                    <td className="py-2 pr-3">
                      <input
                        aria-label={`Condition ${index + 1}`}
                        value={condition.label}
                        maxLength={60}
                        onChange={(event) => setCondition(index, { label: event.target.value })}
                        className="w-full rounded-xl bg-surface px-3 py-2 focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        aria-label={`Restock ${condition.label}`}
                        checked={condition.restock}
                        onChange={(event) => setCondition(index, { restock: event.target.checked })}
                        className="h-4 w-4 accent-accent"
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        aria-label={`Restocking fee for ${condition.label}`}
                        inputMode="decimal"
                        value={percent(condition.fee_bps)}
                        onChange={(event) => {
                          const bps = toBps(event.target.value || "0", 5000);
                          if (bps !== null) setCondition(index, { fee_bps: bps });
                        }}
                        className="w-20 rounded-xl bg-surface px-3 py-2 tabular-nums focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <Select
                        aria-label={`Serial status for ${condition.label}`}
                        value={condition.serial_status}
                        options={SERIAL_STATUS}
                        onChange={(status) => setCondition(index, { serial_status: status })}
                        className="w-44"
                      />
                    </td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        aria-label={`Remove ${condition.label}`}
                        disabled={returns.conditions.length <= 1}
                        onClick={() => setReturns({ conditions: returns.conditions.filter((_, at) => at !== index) })}
                        className="flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent disabled:opacity-30"
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button
              type="button"
              disabled={returns.conditions.length >= 10}
              onClick={() =>
                setReturns({
                  conditions: [
                    ...returns.conditions,
                    {
                      key: keyOf("condition", new Set(returns.conditions.map((condition) => condition.key))),
                      label: "New condition",
                      restock: false,
                      fee_bps: 0,
                      serial_status: "quarantine",
                    },
                  ],
                })
              }
              className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-accent disabled:opacity-40"
            >
              <Plus size={15} aria-hidden="true" /> Add condition
            </button>
          </div>
          <div className="lg:max-w-lg">
            <ChoiceList
              title="Return reasons"
              items={returns.reasons}
              locked={() => false}
              onChange={(reasons) => setReturns({ reasons })}
            />
          </div>
        </section>
      </div>

      {!businessWide ? (
        <p className="mt-4 text-sm text-charcoal/60">Only a business-wide administrator can change the till rules.</p>
      ) : null}
      {notice ? (
        <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">
          {notice}
        </p>
      ) : null}
      <ErrorNote message={error ?? (changed ? problem : null)} />
    </div>
  );
}
