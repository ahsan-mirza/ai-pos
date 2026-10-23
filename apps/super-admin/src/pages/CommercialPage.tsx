import type { BillingAddon, BillingCatalog, BillingCycle, BillingFee, BillingPlan, StoreSubscription } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money, when } from "../lib/format";
import { useSession } from "../lib/session";

function aed(fils: number): string {
  return money(fils, "AED");
}

function filsOf(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.round(parsed * 100);
}

function useCatalog() {
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setCatalog(await api.get<BillingCatalog>("/billing/catalog"));
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the catalog."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return { catalog, error, reload: load };
}

function Reason({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <Field label="Reason (kept in the audit log)" value={value} maxLength={500} onChange={(event) => onChange(event.target.value)} />;
}

export function PackagesPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const { catalog, error, reload } = useCatalog();
  const [editing, setEditing] = useState<BillingPlan | null>(null);
  return (
    <section>
      <h1 className="text-2xl font-semibold">Packages</h1>
      <p className="mt-1 text-sm text-charcoal/60">Monthly prices before the billing-cycle discount. Checkout reads these rows.</p>
      <ErrorNote message={error} />
      <ul className="mt-6 grid gap-3">
        {(catalog?.plans ?? []).map((plan) => (
          <li key={plan.id} className="flex flex-wrap items-center gap-4 rounded-3xl border border-line bg-white px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {plan.name} <span className="font-mono text-xs text-charcoal/50">{plan.code}</span>
              </p>
              <p className="mt-1 text-sm text-charcoal/60">
                {aed(plan.monthly_fils)} / month · {plan.included_registers} registers · {plan.trial_days} trial days
                {plan.active ? "" : " · inactive"}
              </p>
              <p className="mt-1 text-xs text-charcoal/50">{plan.included_modules.join(", ") || "No included modules"}</p>
            </div>
            {admin ? <GhostButton onClick={() => setEditing(plan)}>Edit</GhostButton> : null}
          </li>
        ))}
      </ul>
      {editing ? (
        <PlanEditor
          plan={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void reload();
          }}
        />
      ) : null}
    </section>
  );
}

function PlanEditor({ plan, onClose, onSaved }: { plan: BillingPlan; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(plan.name);
  const [price, setPrice] = useState((plan.monthly_fils / 100).toFixed(2));
  const [registers, setRegisters] = useState(String(plan.included_registers));
  const [modules, setModules] = useState(plan.included_modules.join(", "));
  const [trial, setTrial] = useState(String(plan.trial_days));
  const [active, setActive] = useState(plan.active);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={plan.name}
      subtitle={plan.code}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              setBusy(true);
              setError(null);
              api
                .patch<BillingPlan>(`/billing/plans/${plan.id}`, {
                  name,
                  included_registers: Number(registers) || 1,
                  included_modules: modules.split(",").map((item) => item.trim()).filter(Boolean),
                  monthly_fils: filsOf(price),
                  trial_days: Number(trial) || 0,
                  active,
                  sort_order: plan.sort_order,
                  reason: reason.trim(),
                })
                .then(onSaved)
                .catch((caught: unknown) => {
                  setError(errorText(caught, "Could not save the package."));
                  setBusy(false);
                });
            }}
          >
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <Field label="Monthly price (AED)" value={price} inputMode="decimal" onChange={(event) => setPrice(event.target.value)} />
        <Field label="Included registers" value={registers} inputMode="numeric" onChange={(event) => setRegisters(event.target.value)} />
        <Field label="Included modules" value={modules} onChange={(event) => setModules(event.target.value)} hint="Comma-separated capability keys." />
        <Field label="Trial days" value={trial} inputMode="numeric" onChange={(event) => setTrial(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active
        </label>
        <Reason value={reason} onChange={setReason} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

export function BillingPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const { catalog, error, reload } = useCatalog();
  const [cycle, setCycle] = useState<BillingCycle | null>(null);
  const [fee, setFee] = useState<BillingFee | null>(null);
  return (
    <section>
      <h1 className="text-2xl font-semibold">Billing</h1>
      <p className="mt-1 text-sm text-charcoal/60">The cycle discount applies to recurring amounts. The onboarding fee stays at face value.</p>
      <ErrorNote message={error} />
      <ul className="mt-6 grid gap-3">
        {(catalog?.cycles ?? []).map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-4 rounded-3xl border border-line bg-white px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{row.name}</p>
              <p className="mt-1 text-sm text-charcoal/60">
                {row.months} month{row.months === 1 ? "" : "s"} · {(row.discount_bps / 100).toFixed(2)}% off
                {row.active ? "" : " · inactive"}
              </p>
            </div>
            {admin ? <GhostButton onClick={() => setCycle(row)}>Edit</GhostButton> : null}
          </li>
        ))}
      </ul>
      <h2 className="mt-8 text-lg font-semibold">Onboarding fee</h2>
      <ul className="mt-3 grid gap-3">
        {(catalog?.fees ?? []).map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-4 rounded-3xl border border-line bg-white px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{row.name}</p>
              <p className="mt-1 text-sm text-charcoal/60">
                {aed(row.amount_fils)}
                {row.active ? "" : " · inactive"}
              </p>
            </div>
            {admin ? <GhostButton onClick={() => setFee(row)}>Edit</GhostButton> : null}
          </li>
        ))}
      </ul>
      {cycle ? (
        <CycleEditor
          cycle={cycle}
          onClose={() => setCycle(null)}
          onSaved={() => {
            setCycle(null);
            void reload();
          }}
        />
      ) : null}
      {fee ? (
        <FeeEditor
          fee={fee}
          onClose={() => setFee(null)}
          onSaved={() => {
            setFee(null);
            void reload();
          }}
        />
      ) : null}
    </section>
  );
}

function CycleEditor({ cycle, onClose, onSaved }: { cycle: BillingCycle; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(cycle.name);
  const [months, setMonths] = useState(String(cycle.months));
  const [discount, setDiscount] = useState((cycle.discount_bps / 100).toFixed(2));
  const [active, setActive] = useState(cycle.active);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={cycle.name}
      subtitle={cycle.code}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              setBusy(true);
              api
                .patch(`/billing/cycles/${cycle.id}`, {
                  name,
                  months: Number(months) || 1,
                  discount_bps: Math.round(Number(discount) * 100) || 0,
                  active,
                  sort_order: cycle.sort_order,
                  reason: reason.trim(),
                })
                .then(onSaved)
                .catch((caught: unknown) => {
                  setError(errorText(caught, "Could not save the cycle."));
                  setBusy(false);
                });
            }}
          >
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <Field label="Months" value={months} inputMode="numeric" onChange={(event) => setMonths(event.target.value)} />
        <Field label="Discount percent" value={discount} inputMode="decimal" onChange={(event) => setDiscount(event.target.value)} hint="25 is 25 percent off the recurring total." />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active
        </label>
        <Reason value={reason} onChange={setReason} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

function FeeEditor({ fee, onClose, onSaved }: { fee: BillingFee; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(fee.name);
  const [amount, setAmount] = useState((fee.amount_fils / 100).toFixed(2));
  const [active, setActive] = useState(fee.active);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={fee.name}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              setBusy(true);
              api
                .patch(`/billing/fees/${fee.id}`, { name, amount_fils: filsOf(amount), active, reason: reason.trim() })
                .then(onSaved)
                .catch((caught: unknown) => {
                  setError(errorText(caught, "Could not save the fee."));
                  setBusy(false);
                });
            }}
          >
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <Field label="Amount (AED)" value={amount} inputMode="decimal" onChange={(event) => setAmount(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active
        </label>
        <Reason value={reason} onChange={setReason} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

export function AddonsPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const { catalog, error, reload } = useCatalog();
  const [editing, setEditing] = useState<BillingAddon | null>(null);
  return (
    <section>
      <h1 className="text-2xl font-semibold">Add-ons</h1>
      <p className="mt-1 text-sm text-charcoal/60">Lease rent is recurring. A refundable deposit and the onboarding fee are charged once.</p>
      <ErrorNote message={error} />
      <ul className="mt-6 grid gap-3">
        {(catalog?.addons ?? []).map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-4 rounded-3xl border border-line bg-white px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{row.name}</p>
              <p className="mt-1 text-sm text-charcoal/60">{row.description}</p>
              <p className="mt-1 text-sm text-charcoal/60">
                {aed(row.monthly_fils)} / month
                {row.one_time_fils ? ` · ${aed(row.one_time_fils)} once${row.refundable ? " (refundable)" : ""}` : ""}
                {row.active ? "" : " · inactive"}
              </p>
            </div>
            {admin ? <GhostButton onClick={() => setEditing(row)}>Edit</GhostButton> : null}
          </li>
        ))}
      </ul>
      {editing ? (
        <AddonEditor
          addon={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void reload();
          }}
        />
      ) : null}
    </section>
  );
}

function AddonEditor({ addon, onClose, onSaved }: { addon: BillingAddon; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(addon.name);
  const [description, setDescription] = useState(addon.description);
  const [monthly, setMonthly] = useState((addon.monthly_fils / 100).toFixed(2));
  const [once, setOnce] = useState((addon.one_time_fils / 100).toFixed(2));
  const [refundable, setRefundable] = useState(addon.refundable);
  const [active, setActive] = useState(addon.active);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={addon.name}
      subtitle={addon.code}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              setBusy(true);
              api
                .patch(`/billing/addons/${addon.id}`, {
                  name,
                  description,
                  monthly_fils: filsOf(monthly),
                  one_time_fils: filsOf(once),
                  refundable,
                  active,
                  sort_order: addon.sort_order,
                  reason: reason.trim(),
                })
                .then(onSaved)
                .catch((caught: unknown) => {
                  setError(errorText(caught, "Could not save the add-on."));
                  setBusy(false);
                });
            }}
          >
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <Field label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
        <Field label="Monthly rent (AED)" value={monthly} inputMode="decimal" onChange={(event) => setMonthly(event.target.value)} />
        <Field label="One-time amount (AED)" value={once} inputMode="decimal" onChange={(event) => setOnce(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={refundable} onChange={(event) => setRefundable(event.target.checked)} /> Refundable deposit
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active
        </label>
        <Reason value={reason} onChange={setReason} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

export function SubscriptionsPage() {
  const [rows, setRows] = useState<StoreSubscription[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<StoreSubscription[]>("/subscriptions")
      .then(setRows)
      .catch((caught: unknown) => setError(errorText(caught, "Could not load subscriptions.")));
  }, []);
  return (
    <section>
      <h1 className="text-2xl font-semibold">Subscriptions</h1>
      <p className="mt-1 text-sm text-charcoal/60">Assign a package from the store's drawer. The next amount uses today's catalog.</p>
      <ErrorNote message={error} />
      <div className="mt-6 overflow-x-auto rounded-3xl border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-charcoal/50">
            <tr>
              <th className="px-4 py-3 font-semibold">Store</th>
              <th className="px-4 py-3 font-semibold">Package</th>
              <th className="px-4 py-3 font-semibold">Cycle</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold">Trial ends</th>
              <th className="px-4 py-3 text-right font-semibold">Next</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.tenant_id} className="border-t border-line">
                <td className="px-4 py-3">
                  <span className="block font-semibold">{row.tenant_name}</span>
                  <span className="font-mono text-xs text-charcoal/50">{row.tenant_slug}</span>
                </td>
                <td className="px-4 py-3">{row.plan_name}</td>
                <td className="px-4 py-3">{row.cycle_name}</td>
                <td className="px-4 py-3 capitalize">
                  {row.status}
                  {row.practice_mode ? " · practice" : ""}
                </td>
                <td className="px-4 py-3">{when(row.trial_ends_at)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{aed(row.next_recurring_fils)}</td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-charcoal/50">
                  No subscriptions yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
