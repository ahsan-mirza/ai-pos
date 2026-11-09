import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote, Field, GhostButton, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money, when } from "../lib/format";
import { useSession } from "../lib/session";

interface TrialConfig {
  enabled: boolean;
  days: number;
  eligible_plans: string[];
  promotional_plan: string;
  active_trials: number;
  consumed_trials: number;
  commercial_revision: number;
}

interface PlanPrice {
  id: string;
  plan_code: string;
  country: string;
  currency: string;
  monthly_fils: number;
  enabled: boolean;
}

interface ConfigChange {
  id: string;
  action: string;
  reason: string | null;
  created_at: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export function CommercialControlsPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [trial, setTrial] = useState<TrialConfig | null>(null);
  const [prices, setPrices] = useState<PlanPrice[]>([]);
  const [history, setHistory] = useState<ConfigChange[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    Promise.all([
      api.get<TrialConfig>("/billing/pro-ai-trial"),
      api.get<PlanPrice[]>("/billing/plan-prices"),
      api.get<ConfigChange[]>("/billing/configuration-history"),
    ])
      .then(([nextTrial, nextPrices, nextHistory]) => {
        setTrial(nextTrial);
        setPrices(nextPrices);
        setHistory(nextHistory);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load commercial controls.")));
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <section className="grid gap-8">
      <PageHeader
        title="Commercial"
        description="Plans, prices, and the Pro AI promotion are published here. Issued invoices keep the amount they were created with."
      />
      <ErrorNote message={error} />
      {trial ? <TrialEditor trial={trial} admin={admin} onSaved={load} /> : null}
      <AnnualDiscount admin={admin} onSaved={load} />
      <PriceList prices={prices} admin={admin} onSaved={load} />
      <HistoryList rows={history} />
    </section>
  );
}

function TrialEditor({ trial, admin, onSaved }: { trial: TrialConfig; admin: boolean; onSaved: () => void }) {
  const [enabled, setEnabled] = useState(trial.enabled);
  const [days, setDays] = useState(String(trial.days));
  const [plans, setPlans] = useState(trial.eligible_plans.join(", "));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <section className="rounded-2xl border border-line bg-white p-5">
      <h2 className="text-sm font-semibold">Pro AI promotional trial</h2>
      <p className="mt-1 text-xs text-charcoal/50">
        Promotional plan {trial.promotional_plan}. {trial.active_trials} active, {trial.consumed_trials} consumed. Revision {trial.commercial_revision}. Changing the length does not move a trial that already started. Turning enrollment off does not end an active trial.
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <Field label="Duration (days)" value={days} inputMode="numeric" onChange={(event) => setDays(event.target.value)} />
        <Field label="Eligible base plans" value={plans} onChange={(event) => setPlans(event.target.value)} hint="Plan codes, comma-separated. FREE and GROWTH are the approved start." />
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} disabled={!admin} />
        New stores can start the trial
      </label>
      <Field className="mt-3" label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      <ErrorNote message={error} />
      {admin ? (
        <PrimaryButton
          className="mt-3"
          disabled={busy || reason.trim().length < 3}
          onClick={() => {
            setBusy(true);
            setError(null);
            api
              .put<TrialConfig>("/billing/pro-ai-trial", {
                enabled,
                days: Number(days) || trial.days,
                eligible_plans: plans.split(",").map((item) => item.trim()).filter(Boolean),
                reason: reason.trim(),
              })
              .then(() => {
                setReason("");
                setBusy(false);
                onSaved();
              })
              .catch((caught: unknown) => {
                setError(errorText(caught, "Could not publish the trial settings."));
                setBusy(false);
              });
          }}
        >
          {busy ? "Publishing…" : "Publish trial settings"}
        </PrimaryButton>
      ) : null}
    </section>
  );
}

function AnnualDiscount({ admin, onSaved }: { admin: boolean; onSaved: () => void }) {
  const [percent, setPercent] = useState("20");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<{ current_annual_discount_bps: number }>("/billing/catalog")
      .then((catalog) => setPercent((catalog.current_annual_discount_bps / 100).toFixed(0)))
      .catch(() => undefined);
  }, []);
  return (
    <section className="rounded-2xl border border-line bg-white p-5">
      <h2 className="text-sm font-semibold">New-plan annual discount</h2>
      <p className="mt-1 text-xs text-charcoal/50">
        Applies to a new Free, Growth, Pro AI, or Enterprise annual invoice. Lite, Standard, and Pro keep the billing-cycle discount. Issued invoices stay as they were.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Discount percent" value={percent} inputMode="decimal" onChange={(event) => setPercent(event.target.value)} />
        <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      </div>
      <ErrorNote message={error} />
      {admin ? (
        <PrimaryButton
          className="mt-3"
          disabled={busy || reason.trim().length < 3}
          onClick={() => {
            setBusy(true);
            api
              .put("/billing/annual-discount", {
                discount_bps: Math.round(Number(percent) * 100) || 0,
                reason: reason.trim(),
              })
              .then(() => {
                setReason("");
                setBusy(false);
                onSaved();
              })
              .catch((caught: unknown) => {
                setError(errorText(caught, "Could not publish the discount."));
                setBusy(false);
              });
          }}
        >
          {busy ? "Publishing…" : "Publish discount"}
        </PrimaryButton>
      ) : null}
    </section>
  );
}

function PriceList({ prices, admin, onSaved }: { prices: PlanPrice[]; admin: boolean; onSaved: () => void }) {
  const [editing, setEditing] = useState<PlanPrice | null>(null);
  return (
    <section>
      <h2 className="text-sm font-semibold">Country prices</h2>
      <p className="mt-1 text-xs text-charcoal/50">Only countries with a row are for sale. A blank GCC market is not given the UAE price.</p>
      <ul className="mt-3 grid gap-2">
        {prices.map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3 text-sm">
            <span className="font-mono text-xs">{row.country}</span>
            <span className="font-semibold">{row.plan_code}</span>
            <span className="tabular-nums">{money(row.monthly_fils, row.currency)}</span>
            <span className="text-charcoal/50">{row.enabled ? "On sale" : "Hidden"}</span>
            {admin ? (
              <GhostButton className="ml-auto" onClick={() => setEditing(row)}>
                Edit
              </GhostButton>
            ) : null}
          </li>
        ))}
      </ul>
      {editing ? (
        <PriceEditor
          price={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onSaved();
          }}
        />
      ) : null}
    </section>
  );
}

function PriceEditor({ price, onClose, onSaved }: { price: PlanPrice; onClose: () => void; onSaved: () => void }) {
  const [amount, setAmount] = useState((price.monthly_fils / 100).toFixed(2));
  const [enabled, setEnabled] = useState(price.enabled);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="mt-3 grid gap-3 rounded-2xl border border-line bg-[#f8fafc] p-4"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        api
          .patch(`/billing/plan-prices/${price.id}`, {
            monthly_fils: Math.round(Number(amount) * 100) || 0,
            enabled,
            reason: reason.trim(),
          })
          .then(onSaved)
          .catch((caught: unknown) => {
            setError(errorText(caught, "Could not publish the price."));
            setBusy(false);
          });
      }}
    >
      <p className="text-sm font-semibold">
        {price.plan_code} · {price.country} · {price.currency}
      </p>
      <Field label="Monthly price" value={amount} inputMode="decimal" onChange={(event) => setAmount(event.target.value)} />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> On sale for new quotes
      </label>
      <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      <ErrorNote message={error} />
      <div className="flex gap-2">
        <GhostButton type="button" onClick={onClose}>
          Cancel
        </GhostButton>
        <PrimaryButton type="submit" disabled={busy || reason.trim().length < 3}>
          {busy ? "Publishing…" : "Publish price"}
        </PrimaryButton>
      </div>
    </form>
  );
}

function HistoryList({ rows }: { rows: ConfigChange[] }) {
  return (
    <section>
      <h2 className="text-sm font-semibold">Configuration history</h2>
      <p className="mt-1 text-xs text-charcoal/50">Each publish is a new audit row. Rolling back means publishing again. Issued invoices are not edited.</p>
      <ul className="mt-3 grid gap-2">
        {rows.length === 0 ? <li className="text-sm text-charcoal/50">No commercial changes yet.</li> : null}
        {rows.map((row) => (
          <li key={row.id} className="rounded-2xl border border-line bg-white px-4 py-3 text-sm">
            <p className="font-medium">{row.action}</p>
            <p className="text-xs text-charcoal/50">{when(row.created_at)} · {row.reason || "No reason recorded"}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
