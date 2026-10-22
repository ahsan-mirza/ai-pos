import {
  Permission,
  formatMoney,
  type WarrantyPlan,
  type WarrantyPolicy,
  type WarrantyPolicyWrite,
  type WarrantyRegistration,
  type WarrantyRegistrationList,
  type WarrantyScope,
} from "@ai-pos/shared-types";
import { Plus, Search, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { useCategories } from "../inventory/shared";
import { errorMessage } from "../users/api";

type View = "all" | "expiring";

const day = (value: string) => new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function CoverageChip({ row }: { row: WarrantyRegistration }) {
  const label =
    row.coverage === "IN_WARRANTY" ? (row.status === "CLAIMED" ? "Claimed" : "Covered") : row.coverage === "VOID" ? "Returned" : "Expired";
  const tone =
    row.coverage === "IN_WARRANTY" ? "bg-charcoal text-white" : row.coverage === "VOID" ? "bg-white text-charcoal/60 ring-1 ring-line" : "bg-surface text-charcoal/60 ring-1 ring-line";
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{label}</span>;
}

export function WarrantyPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const manage = can(Permission.WarrantyManage);
  const [view, setView] = useState<View>("all");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [data, setData] = useState<WarrantyRegistrationList | null>(null);
  const [policies, setPolicies] = useState<WarrantyPolicy[]>([]);
  const [plans, setPlans] = useState<WarrantyPlan[]>([]);
  const [dialog, setDialog] = useState<"policy" | "plan" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "200" });
    if (submitted) params.set("q", submitted);
    if (view === "expiring") params.set("expiring_days", "30");
    try {
      setData(await apiGet<WarrantyRegistrationList>(`/api/v1/warranties?${params.toString()}`));
      setPlans(await apiGet<WarrantyPlan[]>("/api/v1/warranties/plans"));
      if (manage) setPolicies(await apiGet<WarrantyPolicy[]>("/api/v1/warranties/policies"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load warranties."));
    }
  }, [manage, submitted, view]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Units under cover</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{data?.active_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/50">Registered automatically at the sale</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Ending in 30 days</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{data?.expiring_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/80">Customers who opted in get a reminder</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Extended plans sold</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{data?.extended_count ?? "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Rung up at the register with the device</p>
        </article>
      </div>
      <ErrorNote message={error} />

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Warranty register</h2>
            <p className="text-sm text-charcoal/60">Search by IMEI or serial, customer name, or phone.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <form
              className="relative"
              onSubmit={(event) => {
                event.preventDefault();
                setSubmitted(query.trim());
              }}
            >
              <Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-charcoal/40" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="IMEI, customer, phone…"
                aria-label="Search warranties"
                className="h-11 w-72 rounded-full border border-line bg-surface pl-10 pr-4 text-sm focus:border-accent focus:bg-white focus:outline-none"
              />
            </form>
            <SegmentedControl
              label="Show"
              value={view}
              options={[
                { value: "all", label: "All" },
                { value: "expiring", label: "Ending soon" },
              ]}
              onChange={setView}
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Unit</th>
                <th className="pb-3 font-medium">Customer</th>
                <th className="pb-3 font-medium">Sold</th>
                <th className="pb-3 font-medium">Cover until</th>
                <th className="pb-3 font-medium">Plan</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.registrations ?? []).map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="py-3">
                    <span className="block font-medium">{row.product_name}</span>
                    <span className="block font-mono text-xs text-charcoal/50">{row.serial ?? "—"}</span>
                  </td>
                  <td className="py-3">
                    {row.customer_id ? (
                      <Link to={`/customers/${row.customer_id}`} className="font-medium hover:text-accent">
                        {row.customer_name}
                      </Link>
                    ) : (
                      <span className="text-charcoal/60">Walk-in</span>
                    )}
                  </td>
                  <td className="py-3">
                    <span className="block tabular-nums">{day(row.starts_at)}</span>
                    <span className="block font-mono text-xs text-charcoal/50">{row.invoice}</span>
                  </td>
                  <td className="py-3 font-semibold tabular-nums">{day(row.expires_at)}</td>
                  <td className="py-3">{row.plan_name ?? <span className="text-charcoal/40">Standard</span>}</td>
                  <td className="py-3 pl-6">
                    <CoverageChip row={row} />
                    {row.claims > 0 ? <span className="ml-2 text-xs text-charcoal/50">{row.claims} claim{row.claims === 1 ? "" : "s"}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data !== null && data.registrations.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No warranties match. Units are registered when a serialized product is sold.</p>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {manage ? (
          <article className="rounded-card border border-line bg-white p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">Standard cover</h2>
                <p className="text-sm text-charcoal/60">Months of cover given with each unit sold.</p>
              </div>
              <PrimaryButton onClick={() => setDialog("policy")}>
                <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" /> Add
              </PrimaryButton>
            </div>
            <ul className="mt-4 space-y-2">
              {policies.map((policy) => (
                <li key={policy.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
                  <ShieldCheck size={18} aria-hidden="true" className="shrink-0 text-charcoal/60" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{policy.name}</p>
                    <p className="text-xs text-charcoal/50">{policy.scope === "DEFAULT" ? "Everything else" : policy.scope.toLowerCase()}</p>
                  </div>
                  <span className="text-lg font-semibold tabular-nums">{policy.months} mo</span>
                </li>
              ))}
              {policies.length === 0 ? (
                <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-charcoal/60">
                  No standard cover yet; units are registered only when a plan is sold.
                </li>
              ) : null}
            </ul>
          </article>
        ) : null}
        <article className="rounded-card bg-charcoal p-6 text-white">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Extended plans</h2>
              <p className="text-sm text-white/60">Each plan is a service product cashiers ring up with the device.</p>
            </div>
            {manage ? (
              <button
                type="button"
                onClick={() => setDialog("plan")}
                className="inline-flex h-10 items-center gap-1.5 rounded-full bg-accent px-4 text-sm font-semibold"
              >
                <Plus size={16} aria-hidden="true" /> New plan
              </button>
            ) : null}
          </div>
          <ul className="mt-4 space-y-2">
            {plans.map((plan) => (
              <li key={plan.id} className="flex items-center gap-3 rounded-2xl bg-white/5 p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{plan.name}</p>
                  <p className="font-mono text-xs text-white/50">{plan.sku}</p>
                </div>
                <span className="text-sm text-white/70">+{plan.extra_months} mo</span>
                <span className="text-lg font-semibold tabular-nums">{formatMoney(plan.price_cents, currency)}</span>
              </li>
            ))}
            {plans.length === 0 ? <li className="rounded-2xl bg-white/5 p-6 text-center text-sm text-white/60">No plans yet.</li> : null}
          </ul>
        </article>
      </div>

      {dialog === "policy" ? (
        <PolicyModal
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            setToast("Standard cover saved.");
            void load();
          }}
        />
      ) : null}
      {dialog === "plan" ? (
        <PlanModal
          currency={currency}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            setToast("Plan created. Registers see it after their next catalog refresh.");
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function PolicyModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { categories } = useCategories();
  const [name, setName] = useState("Manufacturer warranty");
  const [scope, setScope] = useState<WarrantyScope>("DEFAULT");
  const [categoryId, setCategoryId] = useState("");
  const [months, setMonths] = useState("12");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const body: WarrantyPolicyWrite = {
      name: name.trim(),
      scope,
      category_id: scope === "CATEGORY" ? categoryId || null : null,
      months: Number(months) || 0,
    };
    setBusy(true);
    setError(null);
    try {
      await apiPost<WarrantyPolicy[]>("/api/v1/warranties/policies", body);
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the cover."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Standard cover"
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
        <SegmentedControl
          label="Applies to"
          value={scope === "PRODUCT" ? "DEFAULT" : scope}
          options={[
            { value: "DEFAULT", label: "Everything" },
            { value: "CATEGORY", label: "One category" },
          ]}
          onChange={(value) => setScope(value as WarrantyScope)}
        />
        {scope === "CATEGORY" ? (
          <SelectField
            label="Category"
            value={categoryId}
            placeholder="Choose a category"
            options={categories.map((item) => ({ value: item.id, label: item.name }))}
            onChange={setCategoryId}
          />
        ) : null}
        <TextField label="Months of cover" type="number" min={0} max={120} value={months} onChange={(event) => setMonths(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function PlanModal({ currency, onClose, onSaved }: { currency: string; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("Care+ 1 year");
  const [months, setMonths] = useState("12");
  const [price, setPrice] = useState("99.00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const cents = Math.round(Number(price) * 100);
    if (!Number.isFinite(cents) || cents < 0) return setError("Enter a price like 99.00.");
    setBusy(true);
    setError(null);
    try {
      await apiPost<WarrantyPlan[]>("/api/v1/warranties/plans", {
        name: name.trim(),
        extra_months: Number(months) || 0,
        price_cents: cents,
      });
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not create the plan."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New extended plan"
      subtitle="Creates a service product with this price for the register."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Creating…" : "Create plan"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Extra months" type="number" min={1} max={60} value={months} onChange={(event) => setMonths(event.target.value)} />
          <TextField label={`Price (${currency})`} inputMode="decimal" value={price} className="tabular-nums" onChange={(event) => setPrice(event.target.value)} />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
