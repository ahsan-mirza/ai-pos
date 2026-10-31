import {
  cycleAmountFils,
  rankAddons,
  type BillingAddon,
  type BillingCatalog,
  type BillingCycle,
  type BillingFee,
  type BillingPlan,
  type ModuleCatalogueItem,
  type StoreSubscription,
} from "@ai-pos/shared-types";
import { DataTable, Select, type DataTableColumn } from "@ai-pos/ui";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { FilterSearch, FilterSlot, PageHeader } from "../components/PageHeader";
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

function addonPayload(
  addon: BillingAddon,
  reason: string,
  patch: Partial<Pick<BillingAddon, "name" | "description" | "monthly_fils" | "one_time_fils" | "refundable" | "active" | "module_keys" | "sort_order">>,
) {
  return {
    name: patch.name ?? addon.name,
    description: patch.description ?? addon.description,
    monthly_fils: patch.monthly_fils ?? addon.monthly_fils,
    one_time_fils: patch.one_time_fils ?? addon.one_time_fils,
    refundable: patch.refundable ?? addon.refundable,
    active: patch.active ?? addon.active,
    module_keys: patch.module_keys ?? addon.module_keys,
    sort_order: patch.sort_order ?? addon.sort_order,
    reason,
  };
}

function StatusPill({ on, onLabel, offLabel }: { on: boolean; onLabel: string; offLabel: string }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${on ? "bg-emerald-50 text-emerald-700" : "bg-charcoal/5 text-charcoal/55"}`}>
      {on ? onLabel : offLabel}
    </span>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-[#f8fafc] p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{title}</h3>
      <dl className="mt-3 space-y-2 text-sm">{children}</dl>
    </section>
  );
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-charcoal/60">{label}</dt>
      <dd className="max-w-[16rem] text-right font-medium">{value}</dd>
    </div>
  );
}

export function PackagesPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const { catalog, error, reload } = useCatalog();
  const [editing, setEditing] = useState<BillingPlan | null>(null);
  const [viewing, setViewing] = useState<BillingPlan | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const needle = query.trim().toLowerCase();
  const plans = (catalog?.plans ?? [])
    .filter((plan) => (status === "" ? true : status === "published" ? plan.active : !plan.active))
    .filter((plan) => needle === "" || `${plan.name} ${plan.code} ${plan.included_modules.join(" ")}`.toLowerCase().includes(needle))
    .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  return (
    <section>
      <PageHeader
        title="Packages"
        description="Monthly prices before the billing-cycle discount. Checkout and the public site read these rows."
        controls={
          <>
            <FilterSearch label="Search packages" value={query} onChange={setQuery} placeholder="Search name or code" />
            <FilterSlot>
              <Select
                aria-label="Publication"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "", label: "All packages" },
                  { value: "published", label: "Published" },
                  { value: "hidden", label: "Unpublished" },
                ]}
              />
            </FilterSlot>
          </>
        }
      />
      <ErrorNote message={error} />
      {catalog && plans.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-line bg-white px-4 py-8 text-center text-sm text-charcoal/60">
          No packages match. Clear the search or publication filter.
        </p>
      ) : null}
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plans.map((plan) => (
          <li key={plan.id} className="flex flex-col rounded-2xl border border-line bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{plan.name}</p>
                <p className="font-mono text-xs text-charcoal/50">{plan.code}</p>
              </div>
              <StatusPill on={plan.active} onLabel="Published" offLabel="Unpublished" />
            </div>
            <p className="mt-4 text-2xl font-semibold tabular-nums">{aed(plan.monthly_fils)}</p>
            <p className="text-xs text-charcoal/50">per month, before the billing-cycle discount</p>
            <p className="mt-3 text-sm text-charcoal/70">
              {plan.included_registers} {plan.included_registers === 1 ? "register" : "registers"} · {plan.trial_days}-day trial
            </p>
            <p className="mt-2 line-clamp-2 text-xs text-charcoal/50">{plan.included_modules.join(", ") || "No included modules"}</p>
            <div className="mt-4 flex gap-2">
              <GhostButton onClick={() => setViewing(plan)}>View</GhostButton>
              {admin ? <GhostButton onClick={() => setEditing(plan)}>Edit</GhostButton> : null}
            </div>
          </li>
        ))}
      </ul>
      {viewing ? (
        <PlanDetail
          plan={viewing}
          cycles={catalog?.cycles ?? []}
          fee={catalog?.fees.find((row) => row.active) ?? null}
          onClose={() => setViewing(null)}
          onEdit={
            admin
              ? () => {
                  setEditing(viewing);
                  setViewing(null);
                }
              : undefined
          }
        />
      ) : null}
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

function PlanDetail({
  plan,
  cycles,
  fee,
  onClose,
  onEdit,
}: {
  plan: BillingPlan;
  cycles: BillingCycle[];
  fee: BillingFee | null;
  onClose: () => void;
  onEdit?: () => void;
}) {
  return (
    <Modal
      wide
      title={plan.name}
      subtitle={plan.code}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Close</GhostButton>
          {onEdit ? <PrimaryButton onClick={onEdit}>Edit</PrimaryButton> : null}
        </>
      }
    >
      <div className="grid gap-3">
        <DetailSection title="Basic information">
          <DetailRow label="Name" value={plan.name} />
          <DetailRow label="Code" value={plan.code} />
          <DetailRow label="Publication" value={plan.active ? "On the public site and in checkout" : "Hidden"} />
        </DetailSection>
        <DetailSection title="Pricing">
          <DetailRow label="Monthly base" value={aed(plan.monthly_fils)} />
          <DetailRow label="Currency" value="AED" />
          {fee ? <DetailRow label="Onboarding fee" value={`${fee.name} · ${aed(fee.amount_fils)} once`} /> : null}
          {cycles
            .filter((cycle) => cycle.active)
            .map((cycle) => (
              <DetailRow
                key={cycle.id}
                label={cycle.name}
                value={`${aed(cycleAmountFils(plan.monthly_fils, cycle.months, cycle.discount_bps))} / ${cycle.months} mo · ${cycle.discount_bps / 100}% off`}
              />
            ))}
        </DetailSection>
        <DetailSection title="Included features">
          <DetailRow label="Registers" value={String(plan.included_registers)} />
          <DetailRow label="Modules" value={plan.included_modules.join(", ") || "None"} />
        </DetailSection>
        <DetailSection title="Trial">
          <DetailRow label="Trial days" value={String(plan.trial_days)} />
        </DetailSection>
        <p className="text-xs text-charcoal/50">Saving a published package changes the public price. Issued invoices stay as they were.</p>
      </div>
    </Modal>
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
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Published on the site and in checkout
        </label>
        {active ? (
          <p className="rounded-2xl bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Publishing updates the public price. Existing subscriptions keep invoices that were already issued.
          </p>
        ) : null}
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
      <PageHeader
        title="Billing"
        description="The cycle discount applies to recurring package and add-on rent. Onboarding, deposits, and one-time fees stay at face value."
      />
      <ErrorNote message={error} />
      <h2 className="text-sm font-semibold">Recurring billing cycles</h2>
      <ul className="mt-3 grid gap-3 md:grid-cols-2">
        {(catalog?.cycles ?? []).map((row) => (
          <li key={row.id} className="rounded-2xl border border-line bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{row.name}</p>
                <p className="font-mono text-xs text-charcoal/50">{row.code}</p>
              </div>
              <StatusPill on={row.active} onLabel="Active" offLabel="Inactive" />
            </div>
            <p className="mt-3 text-sm text-charcoal/70">
              {row.months} month{row.months === 1 ? "" : "s"} · {(row.discount_bps / 100).toFixed(2)}% off recurring charges
            </p>
            <ul className="mt-3 space-y-1 text-xs text-charcoal/60">
              {(catalog?.plans ?? [])
                .filter((plan) => plan.active)
                .map((plan) => (
                  <li key={plan.id}>
                    {plan.name}: {aed(cycleAmountFils(plan.monthly_fils, row.months, row.discount_bps))} for the cycle
                  </li>
                ))}
            </ul>
            {admin ? (
              <GhostButton className="mt-4" onClick={() => setCycle(row)}>
                Edit
              </GhostButton>
            ) : null}
          </li>
        ))}
      </ul>
      <h2 className="mt-8 text-sm font-semibold">One-time onboarding</h2>
      <p className="mt-1 text-xs text-charcoal/50">Charged once. This is not monthly revenue and the cycle discount does not apply.</p>
      <ul className="mt-3 grid gap-3">
        {(catalog?.fees ?? []).map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-white px-5 py-4 shadow-sm">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{row.name}</p>
              <p className="mt-1 text-sm text-charcoal/60">{aed(row.amount_fils)} once</p>
            </div>
            <StatusPill on={row.active} onLabel="Active" offLabel="Inactive" />
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

function priceDetail(row: BillingAddon): string {
  const parts: string[] = [];
  parts.push(row.monthly_fils > 0 ? `${aed(row.monthly_fils)} / month` : "No monthly charge");
  if (row.one_time_fils > 0) {
    parts.push(row.refundable ? `${aed(row.one_time_fils)} refundable deposit` : `${aed(row.one_time_fils)} one-time`);
  } else {
    parts.push("No one-time charge");
  }
  return parts.join(" · ");
}

function AddonActivation({
  addon,
  onClose,
  onSaved,
}: {
  addon: BillingAddon;
  onClose: () => void;
  onSaved: () => void;
}) {
  const turningOn = !addon.active;
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={turningOn ? `Activate ${addon.name}` : `Deactivate ${addon.name}`}
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
                .patch(`/billing/addons/${addon.id}`, addonPayload(addon, reason.trim(), { active: turningOn }))
                .then(onSaved)
                .catch((caught: unknown) => {
                  setError(errorText(caught, "Could not update the add-on."));
                  setBusy(false);
                });
            }}
          >
            {busy ? "Saving…" : turningOn ? "Activate" : "Deactivate"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <p className="text-sm text-charcoal/70">
          {turningOn
            ? "An active add-on is listed in store settings, with the monthly and one-time prices below. Activating it does not bill stores that have not chosen it."
            : "An inactive add-on is hidden from store settings. Stores that already pay for it keep that subscription until it ends."}
        </p>
        <p className="text-sm">{priceDetail(addon)}</p>
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
  const [viewing, setViewing] = useState<BillingAddon | null>(null);
  const [activating, setActivating] = useState<BillingAddon | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const rows = rankAddons(
    (catalog?.addons ?? []).filter((row) => (status === "" ? true : status === "active" ? row.active : !row.active)),
    query,
  );
  const columns = useMemo<DataTableColumn<BillingAddon>[]>(
    () => [
      {
        header: "Add-on",
        cell: (row) => (
          <span className="block min-w-0">
            <span className="block font-semibold">{row.name}</span>
            <span className="block font-mono text-xs text-charcoal/50">{row.code}</span>
          </span>
        ),
      },
      {
        header: "Description",
        cell: (row) => <span className="block max-w-xs text-charcoal/70">{row.description || "—"}</span>,
      },
      {
        header: "Monthly",
        align: "right",
        cell: (row) => (row.monthly_fils > 0 ? `${aed(row.monthly_fils)} / month` : "—"),
      },
      {
        header: "One-time",
        align: "right",
        cell: (row) => (row.one_time_fils > 0 ? aed(row.one_time_fils) : "—"),
      },
      {
        header: "Deposit",
        cell: (row) => (row.one_time_fils > 0 ? (row.refundable ? "Refundable" : "Kept") : "—"),
      },
      {
        header: "Modules",
        cell: (row) => row.module_keys.join(", ") || "—",
      },
      {
        header: "Status",
        cell: (row) => <StatusPill on={row.active} onLabel="Active" offLabel="Inactive" />,
      },
      {
        id: "actions",
        header: "Actions",
        cell: (row) => (
          <span className="flex flex-wrap gap-2">
            <GhostButton onClick={() => setViewing(row)}>View</GhostButton>
            {admin ? (
              <>
                <GhostButton onClick={() => setActivating(row)}>{row.active ? "Deactivate" : "Activate"}</GhostButton>
                <GhostButton onClick={() => setEditing(row)}>Pricing</GhostButton>
              </>
            ) : null}
          </span>
        ),
      },
    ],
    [admin],
  );
  return (
    <section>
      <PageHeader
        title="Add-ons"
        description="Activate an add-on to list it in store settings. Set the monthly price, the one-time price, and whether that one-time amount is a refundable deposit."
        controls={
          <>
            <FilterSearch label="Search add-ons" value={query} onChange={setQuery} placeholder="Name or description" />
            <FilterSlot>
              <Select
                aria-label="Status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "", label: "All add-ons" },
                  { value: "active", label: "Active" },
                  { value: "inactive", label: "Inactive" },
                ]}
              />
            </FilterSlot>
          </>
        }
      />
      <ErrorNote message={error} />
      <DataTable
        aria-label="Add-ons"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        isLoading={catalog === null && error === null}
        emptyState={{ title: query.trim() ? "No add-ons match that search" : "No add-ons" }}
        minWidth="1100px"
      />
      {viewing ? (
        <AddonDetail
          addon={viewing}
          plans={catalog?.plans ?? []}
          onClose={() => setViewing(null)}
          onEdit={
            admin
              ? () => {
                  setEditing(viewing);
                  setViewing(null);
                }
              : undefined
          }
        />
      ) : null}
      {activating ? (
        <AddonActivation
          addon={activating}
          onClose={() => setActivating(null)}
          onSaved={() => {
            setActivating(null);
            void reload();
          }}
        />
      ) : null}
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

function AddonDetail({
  addon,
  plans,
  onClose,
  onEdit,
}: {
  addon: BillingAddon;
  plans: BillingPlan[];
  onClose: () => void;
  onEdit?: () => void;
}) {
  const [stores, setStores] = useState<StoreSubscription[] | null>(null);
  useEffect(() => {
    api
      .get<StoreSubscription[]>("/subscriptions")
      .then((rows) => setStores(rows.filter((row) => row.addons.some((item) => item.code === addon.code && item.quantity > 0))))
      .catch(() => setStores([]));
  }, [addon.code]);
  const carrying = plans.filter((plan) => addon.module_keys.some((key) => plan.included_modules.includes(key)));
  return (
    <Modal
      wide
      title={addon.name}
      subtitle={addon.code}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Close</GhostButton>
          {onEdit ? <PrimaryButton onClick={onEdit}>Edit</PrimaryButton> : null}
        </>
      }
    >
      <div className="grid gap-3">
        <DetailSection title="Basic information">
          <DetailRow label="Description" value={addon.description || "—"} />
          <DetailRow label="Publication" value={addon.active ? "Published" : "Unpublished"} />
        </DetailSection>
        <DetailSection title="Pricing">
          <DetailRow label="Recurring" value={addon.monthly_fils > 0 ? `${aed(addon.monthly_fils)} / month` : "None"} />
          <DetailRow
            label="One-time"
            value={addon.one_time_fils > 0 ? `${aed(addon.one_time_fils)}${addon.refundable ? " · refundable deposit" : ""}` : "None"}
          />
          <DetailRow label="Currency" value="AED" />
        </DetailSection>
        <DetailSection title="Entitlement">
          <DetailRow label="Modules" value={addon.module_keys.join(", ") || "None"} />
          <DetailRow label="Already in packages" value={carrying.map((plan) => plan.name).join(", ") || "None"} />
        </DetailSection>
        <DetailSection title="Marketplace">
          <DetailRow label="Category" value={addon.listing?.category || "—"} />
          <DetailRow label="Publication" value={addon.listing?.publication || (addon.active ? "published" : "draft")} />
          <DetailRow label="Overview" value={addon.listing?.overview || "—"} />
        </DetailSection>
        <DetailSection title="Price history">
          <DetailRow
            label="Earlier prices"
            value={
              (addon.price_history ?? []).length === 0
                ? "None"
                : (addon.price_history ?? [])
                    .map((point) => `${aed(point.monthly_fils)} / month · ${point.effective_at.slice(0, 10)}`)
                    .join("; ")
            }
          />
        </DetailSection>
        <DetailSection title="Subscriptions">
          <DetailRow
            label="Stores"
            value={stores === null ? "Loading…" : stores.length === 0 ? "None" : stores.map((row) => row.tenant_name).join(", ")}
          />
        </DetailSection>
        <p className="text-xs text-charcoal/50">Listing an add-on does not turn its modules on. A store still needs a subscription and a grant.</p>
      </div>
    </Modal>
  );
}

function linesOf(rows: { title: string; description: string }[] | undefined): string {
  return (rows ?? []).map((row) => `${row.title} | ${row.description}`).join("\n");
}

function pairsOf(text: string): { title: string; description: string }[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [title, ...rest] = line.split("|");
      return { title: (title ?? "").trim(), description: rest.join("|").trim() };
    })
    .filter((row) => row.title.length > 0 || row.description.length > 0);
}

function AddonEditor({ addon, onClose, onSaved }: { addon: BillingAddon; onClose: () => void; onSaved: () => void }) {
  const listing = addon.listing;
  const [name, setName] = useState(addon.name);
  const [description, setDescription] = useState(addon.description);
  const [overview, setOverview] = useState(listing?.overview ?? "");
  const [shortText, setShortText] = useState(listing?.short_description ?? "");
  const [category, setCategory] = useState(listing?.category ?? "operations");
  const [tags, setTags] = useState((listing?.tags ?? []).join(", "));
  const [benefits, setBenefits] = useState(linesOf(listing?.benefits));
  const [features, setFeatures] = useState(linesOf(listing?.features));
  const [steps, setSteps] = useState(linesOf(listing?.steps));
  const [requirements, setRequirements] = useState((listing?.requirements ?? []).join("\n"));
  const [docs, setDocs] = useState(listing?.documentation_url ?? "");
  const [video, setVideo] = useState(listing?.video_url ?? "");
  const [support, setSupport] = useState(listing?.support ?? "");
  const [icon, setIcon] = useState(listing?.icon ?? "puzzle");
  const [imageUrl, setImageUrl] = useState(listing?.image_url ?? "");
  const [featured, setFeatured] = useState(listing?.featured ?? false);
  const [publication, setPublication] = useState(listing?.publication ?? (addon.active ? "published" : "draft"));
  const [monthly, setMonthly] = useState((addon.monthly_fils / 100).toFixed(2));
  const [once, setOnce] = useState((addon.one_time_fils / 100).toFixed(2));
  const [refundable, setRefundable] = useState(addon.refundable);
  const [active, setActive] = useState(addon.active);
  const [modules, setModules] = useState<string[]>(addon.module_keys ?? []);
  const [order, setOrder] = useState(String(addon.sort_order));
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
                  active: publication === "published" ? active : false,
                  module_keys: modules,
                  sort_order: Number.isFinite(Number(order)) ? Math.max(0, Math.round(Number(order))) : addon.sort_order,
                  reason: reason.trim(),
                  listing: {
                    short_description: shortText,
                    overview,
                    category,
                    tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
                    benefits: pairsOf(benefits),
                    features: pairsOf(features),
                    steps: pairsOf(steps),
                    requirements: requirements.split("\n").map((line) => line.trim()).filter(Boolean),
                    faqs: listing?.faqs ?? [],
                    documentation_url: docs,
                    video_url: video,
                    support,
                    icon,
                    image_url: imageUrl,
                    featured,
                    publication,
                  },
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
        <Field label="Short description" value={shortText} onChange={(event) => setShortText(event.target.value)} />
        <Field label="Overview" value={overview} onChange={(event) => setOverview(event.target.value)} />
        <Field label="Category" value={category} onChange={(event) => setCategory(event.target.value)} />
        <Field label="Tags" hint="Comma separated. Used by marketplace search." value={tags} onChange={(event) => setTags(event.target.value)} />
        <Field label="Benefits description" hint="One per line: title | description" value={benefits} onChange={(event) => setBenefits(event.target.value)} />
        <Field label="Features description" hint="One per line: title | description" value={features} onChange={(event) => setFeatures(event.target.value)} />
        <Field label="Steps description" hint="One per line: title | description" value={steps} onChange={(event) => setSteps(event.target.value)} />
        <Field label="Requirements description" hint="One requirement per line." value={requirements} onChange={(event) => setRequirements(event.target.value)} />
        <Field label="Icon" hint="monitor, hash, layers, landmark, truck, credit-card, receipt, shield, or puzzle." value={icon} onChange={(event) => setIcon(event.target.value)} />
        <Field label="Logo URL" hint="https link. Leave blank to use the icon." value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} />
        <Field label="Documentation URL" value={docs} onChange={(event) => setDocs(event.target.value)} />
        <Field label="Video URL" value={video} onChange={(event) => setVideo(event.target.value)} />
        <Field label="Support" value={support} onChange={(event) => setSupport(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={featured} onChange={(event) => setFeatured(event.target.checked)} /> Featured
        </label>
        <label className="block text-sm">
          Publication
          <select className="mt-1 block w-full rounded-xl border border-line bg-white px-3 py-2" value={publication} onChange={(event) => setPublication(event.target.value as "published" | "draft" | "archived")}>
            <option value="published">Published</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <Field
          label="Monthly price (AED)"
          hint="Charged every month. A longer billing cycle can discount this amount. Use 0 when there is no recurring charge."
          value={monthly}
          inputMode="decimal"
          onChange={(event) => setMonthly(event.target.value)}
        />
        <Field
          label="One-time price (AED)"
          hint="Charged once, on top of the monthly price. Use 0 when there is no one-time charge."
          value={once}
          inputMode="decimal"
          onChange={(event) => setOnce(event.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={refundable} onChange={(event) => setRefundable(event.target.checked)} />
          The one-time price is a refundable deposit
        </label>
        <Field
          label="Sort order"
          hint="Lower numbers are listed first when a search box is empty."
          value={order}
          inputMode="numeric"
          onChange={(event) => setOrder(event.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
          Active in the store add-on library
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
      <PageHeader
        title="Subscriptions"
        description="Assign a package from the store's drawer. The next amount uses today's catalog."
        controls={
          <>
            <FilterSearch label="Search subscriptions" value={query} onChange={setQuery} placeholder="Search store or package" />
            <FilterSlot>
              <Select
                aria-label="Subscription status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "", label: "All statuses" },
                  { value: "trialing", label: "Trialing" },
                  { value: "active", label: "Active" },
                  { value: "past_due", label: "Past due" },
                  { value: "canceled", label: "Canceled" },
                ]}
              />
            </FilterSlot>
          </>
        }
      />
      <div>
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
