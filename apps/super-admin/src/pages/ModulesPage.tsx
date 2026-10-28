import type { ModuleCatalogueItem, ModuleSummary } from "@ai-pos/shared-types";
import { DataTable, type DataTableColumn } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ErrorNote } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money } from "../lib/format";

const columns: DataTableColumn<ModuleCatalogueItem>[] = [
  { id: "key", header: "Key", className: "font-mono text-xs", cell: (row) => row.key },
  { id: "name", header: "Module", cell: (row) => row.label },
  {
    id: "state",
    header: "Implementation",
    cell: (row) => (row.available ? "Implemented" : "Not implemented"),
  },
  {
    id: "requires",
    header: "Depends on",
    cell: (row) => (row.requires.length ? row.requires.join(", ") : "—"),
  },
  {
    id: "types",
    header: "Business types",
    cell: (row) => String(row.business_types.length),
  },
  {
    id: "plans",
    header: "Plans",
    cell: (row) => (row.plan_codes.length ? row.plan_codes.join(", ") : "—"),
  },
  {
    id: "addons",
    header: "Add-ons",
    cell: (row) => (row.addon_codes.length ? row.addon_codes.join(", ") : "—"),
  },
];

export function ModulesPage() {
  const [rows, setRows] = useState<ModuleCatalogueItem[]>([]);
  const [summary, setSummary] = useState<ModuleSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.get<ModuleCatalogueItem[]>("/modules"), api.get<ModuleSummary>("/modules/summary")])
      .then(([catalogue, counts]) => {
        setRows(catalogue);
        setSummary(counts);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the module catalogue.")));
  }, []);
  return (
    <section>
      <h1 className="text-2xl font-semibold">Module catalogue</h1>
      <p className="mt-1 max-w-3xl text-sm text-charcoal/60">
        These are the modules the product actually registers. A commercial add-on can be mapped to them from Add-on pricing.
        Mapping does not turn a module on for a store. Access still follows the business type, the store selection, and a console override.
      </p>
      <ErrorNote message={error} />
      {summary ? (
        <dl className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Registered modules" value={String(summary.catalogue_total)} hint={`${summary.implemented} implemented`} />
          <Stat label="Active add-ons" value={String(summary.active_addons)} hint={`${summary.mapped_addons} mapped to a module`} />
          <Stat label="Active subscriptions" value={String(summary.active_subscriptions)} hint={`${summary.trialing_subscriptions} on trial`} />
          <Stat label="Add-on MRR" value={money(summary.addon_mrr_fils, "AED")} hint="Active subscriptions only. Excludes trials and one-time fees." />
          <Stat label="Pending receipts" value={String(summary.pending_payments)} hint="Awaiting verification" />
          <Stat label="Past due" value={String(summary.past_due_subscriptions)} hint={`${summary.canceled_subscriptions} cancelled`} />
        </dl>
      ) : null}
      <div className="mt-6">
        <DataTable aria-label="Module catalogue" columns={columns} data={rows} getRowId={(row) => row.key} />
      </div>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-3xl border border-line bg-white px-5 py-4">
      <dt className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{label}</dt>
      <dd className="mt-2 text-2xl font-semibold tabular-nums">{value}</dd>
      <dd className="mt-1 text-xs text-charcoal/50">{hint}</dd>
    </div>
  );
}
