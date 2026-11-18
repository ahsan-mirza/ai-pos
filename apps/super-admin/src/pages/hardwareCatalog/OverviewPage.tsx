import { useEffect, useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ErrorNote } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import type { CatalogOverview } from "./types";

const tiles: { key: keyof CatalogOverview; label: string }[] = [
  { key: "categories", label: "Categories" },
  { key: "products", label: "Products" },
  { key: "published_products", label: "Published products" },
  { key: "draft_products", label: "Draft products" },
  { key: "archived_products", label: "Archived products" },
  { key: "packages", label: "Packages" },
  { key: "published_packages", label: "Published packages" },
  { key: "new_enquiries", label: "New enquiries" },
  { key: "converted_enquiries", label: "Converted enquiries" },
];

export function HardwareOverviewPage() {
  const [stats, setStats] = useState<CatalogOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<CatalogOverview>("/hardware-catalog/overview")
      .then(setStats)
      .catch((caught) => setError(errorText(caught, "The catalogue summary could not be loaded.")));
  }, []);

  return (
    <div>
      <PageHeader title="Hardware catalog" description="Published products and packages shown on axizpos.com/hardware." />
      <ErrorNote message={error} />
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {tiles.map((tile) => (
          <li key={tile.key} className="rounded-2xl border border-line bg-card px-4 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-charcoal/50">{tile.label}</p>
            <p className="mt-2 text-2xl font-semibold text-charcoal">{stats ? stats[tile.key] : "—"}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
