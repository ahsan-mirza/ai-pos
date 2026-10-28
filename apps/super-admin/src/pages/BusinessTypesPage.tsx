import type { BusinessTypeModules } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote } from "../components/ui";
import { api, errorText } from "../lib/api";

export function BusinessTypesPage() {
  const [rows, setRows] = useState<BusinessTypeModules[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<BusinessTypeModules[]>("/modules/business-types")
      .then((found) => {
        setRows(found);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load business types.")));
  }, []);
  return (
    <section>
      <PageHeader
        title="Business types"
        description="Preset modules are what a new store of that type starts with. Eligible modules are the ones that type may turn on. Changing this list is a product change, not a per-store edit, so it stays in the registered catalogue."
      />
      <ErrorNote message={error} />
      <ul className="mt-6 grid gap-3">
        {rows.map((row) => (
          <li key={row.key} className="rounded-3xl border border-line bg-white px-5 py-4">
            <p className="font-semibold">{row.label}</p>
            <p className="mt-1 font-mono text-xs text-charcoal/50">{row.key}</p>
            <p className="mt-3 text-sm">
              <span className="font-medium">Preset. </span>
              <span className="text-charcoal/70">{row.preset.join(", ") || "None"}</span>
            </p>
            <p className="mt-2 text-sm">
              <span className="font-medium">Eligible. </span>
              <span className="text-charcoal/70">{row.eligible.join(", ") || "None"}</span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
