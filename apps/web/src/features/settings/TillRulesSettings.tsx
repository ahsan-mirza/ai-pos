import {
  Capability,
  formatMoney,
  resolvePosPolicy,
  type BusinessSettings,
  type PosPolicy,
  type ReturnConditionRule,
} from "@ai-pos/shared-types";
import { ScrollText } from "lucide-react";
import { useEffect, useState } from "react";
import { useTenant } from "../../context/TenantContext";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { errorMessage } from "../users/api";
import { ChoiceList, percent, toBps } from "./policyFields";
import { RestaurantVoidPolicySettings } from "./RestaurantVoidPolicySettings";
import { RetailReturnsPolicySettings, presetReturns } from "./RetailReturnsPolicySettings";

/** Cashier discounts, gift cards and the returns policy: business-wide rules every register caches and enforces. */
export function TillRulesSettings() {
  const { user } = useAuth();
  const { currency, settings, applySettings } = useCurrency();
  const { has } = useCapabilities();
  const { isFnB, isElectronics, isFashion } = useTenant();
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

  useEffect(() => {
    if (form === null || window.location.hash !== "#void-policy") return;
    document.getElementById("void-policy")?.scrollIntoView({ behavior: "smooth" });
  }, [form]);

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
  const giftCardsOn = has(Capability.GiftCards);
  const labelsMissing = isFnB
    ? form.voids.reasons.some((reason) => !reason.label.trim())
    : form.returns.reasons.some((reason) => !reason.label.trim()) ||
      form.returns.conditions.some((condition) => !condition.label.trim());
  const problem =
    limitBps === null
      ? "Enter the default discount limit as a percent from 0 to 100."
      : giftCardsOn && (minCents === null || maxCents === null || minCents < 100)
        ? "Enter gift card amounts like 50.00 (at least 1.00)."
        : giftCardsOn && maxCents !== null && minCents !== null && maxCents < minCents
          ? "The largest gift card must be at least the smallest."
          : form.discounts.reasons.some((reason) => !reason.label.trim()) || labelsMissing
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
              {isFnB
                ? "Discounts and void rules. Every register enforces these, even offline."
                : "Discounts, gift cards and returns. Every register enforces these, even offline."}
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

        {isFnB ? (
          <RestaurantVoidPolicySettings
            policy={form.voids}
            onChange={(voids) => setForm({ ...form, voids })}
          />
        ) : (
          <RetailReturnsPolicySettings
            returns={returns}
            showElectronicsPreset={isElectronics}
            showFashionPreset={isFashion}
            showSerialRouting={isElectronics}
            onPreset={(preset) => setForm({ ...form, returns: presetReturns(preset) })}
            onPatch={setReturns}
            onCondition={setCondition}
          />
        )}
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
