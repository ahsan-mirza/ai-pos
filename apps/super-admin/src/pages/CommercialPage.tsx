import type {
  BillingAddon,
  BillingCatalog,
  BillingCycle,
  BillingFee,
  BillingPlan,
  ModuleCatalogueItem,
  StoreSubscription,
} from "@ai-pos/shared-types";
import { DataTable, type DataTableColumn } from "@ai-pos/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
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
                {row.module_keys?.length ? ` · ${row.module_keys.join(", ")}` : ""}
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
  const [modules, setModules] = useState<string[]>(addon.module_keys ?? []);
  const [choices, setChoices] = useState<ModuleCatalogueItem[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<ModuleCatalogueItem[]>("/modules")
      .then((rows) => setChoices(rows.filter((row) => row.available)))
      .catch(() => setChoices([]));
  }, []);
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
                  module_keys: modules,
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
        <fieldset>
          <legend className="text-sm font-medium">Modules this add-on may sell</legend>
          <p className="mt-1 text-xs text-charcoal/50">Saving this does not enable the module for existing stores.</p>
          <div className="mt-2 grid max-h-48 gap-1 overflow-y-auto">
            {choices.map((choice) => (
              <label key={choice.key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={modules.includes(choice.key)}
                  onChange={(event) =>
                    setModules((current) =>
                      event.target.checked ? [...current, choice.key] : current.filter((key) => key !== choice.key),
                    )
                  }
                />
                {choice.label}
                {choice.requires.length ? <span className="text-xs text-charcoal/50">needs {choice.requires.join(", ")}</span> : null}
              </label>
            ))}
          </div>
        </fieldset>
        <Reason value={reason} onChange={setReason} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

export function SubscriptionsPage() {
  const [rows, setRows] = useState<StoreSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const load = useCallback(() => {
    setLoading(true);
    api
      .get<StoreSubscription[]>("/subscriptions")
      .then((found) => {
        setRows(found);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load subscriptions.")))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (status !== "" && row.status !== status) return false;
        if (needle === "") return true;
        return `${row.tenant_name} ${row.tenant_slug} ${row.plan_name}`.toLowerCase().includes(needle);
      }),
    [needle, rows, status],
  );
  const columns: DataTableColumn<StoreSubscription>[] = [
    {
      id: "store",
      header: "Store",
      sortValue: (row) => row.tenant_name,
      cell: (row) => (
        <span>
          <span className="block font-semibold">{row.tenant_name}</span>
          <span className="font-mono text-xs text-charcoal/50">{row.tenant_slug}</span>
        </span>
      ),
    },
    { id: "package", header: "Package", sortValue: (row) => row.plan_name, cell: (row) => row.plan_name },
    { id: "cycle", header: "Cycle", sortValue: (row) => row.cycle_name, cell: (row) => row.cycle_name },
    {
      id: "status",
      header: "Status",
      sortValue: (row) => row.status,
      cell: (row) => (
        <span className="capitalize">
          {row.status.replace("_", " ")}
          {row.practice_mode ? " · practice" : ""}
        </span>
      ),
    },
    { id: "trial", header: "Trial ends", cell: (row) => when(row.trial_ends_at) },
    {
      id: "next",
      header: "Next",
      align: "right",
      sortValue: (row) => row.next_recurring_fils,
      cell: (row) => aed(row.next_recurring_fils),
    },
  ];
  return (
    <section>
      <h1 className="text-2xl font-semibold">Subscriptions</h1>
      <p className="mt-1 text-sm text-charcoal/60">Assign a package from the store's drawer. The next amount uses today's catalog.</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search store or package"
          aria-label="Search subscriptions"
          className="h-10 w-64 rounded-full border border-line px-4 text-sm"
        />
        <select
          aria-label="Subscription status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-10 rounded-full border border-line bg-white px-3 text-sm"
        >
          <option value="">All statuses</option>
          <option value="trialing">Trialing</option>
          <option value="active">Active</option>
          <option value="past_due">Past due</option>
          <option value="canceled">Canceled</option>
        </select>
      </div>
      <div className="mt-4">
        <DataTable
          aria-label="Subscriptions"
          minWidth="760px"
          columns={columns}
          data={visible}
          getRowId={(row) => row.tenant_id}
          isLoading={loading}
          error={error}
          onRetry={load}
          pagination={{ mode: "client", resetKey: `${needle}:${status}` }}
          emptyState={{ title: "No subscriptions match", description: "Try another status or search." }}
        />
      </div>
    </section>
  );
}
