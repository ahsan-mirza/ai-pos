import { DataTable, type DataTableColumn } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { ErrorNote, GhostButton } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import { money } from "../../lib/format";
import { useSession } from "../../lib/session";
import type { CatalogPackage } from "./types";

export function HardwarePackagesPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const navigate = useNavigate();
  const [rows, setRows] = useState<CatalogPackage[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .page<CatalogPackage>("/hardware-catalog/packages?limit=100")
      .then((found) => setRows(found.rows))
      .catch((caught) => setError(errorText(caught, "Packages could not be loaded.")))
      .finally(() => setLoading(false));
  }, []);

  const columns: DataTableColumn<CatalogPackage>[] = [
    { id: "name", header: "Package", cell: (row) => row.name },
    { id: "type", header: "Type", cell: (row) => row.package_type.replaceAll("_", " ") },
    { id: "price", header: "Package price", cell: (row) => (row.display_price_fils == null ? "On request" : money(row.display_price_fils, row.currency)) },
    { id: "plan", header: "Software plan", cell: (row) => row.plan?.name ?? "—" },
    { id: "items", header: "Components", cell: (row) => String(row.items.length) },
    { id: "status", header: "Publishing", cell: (row) => (row.is_published ? "Published" : "Draft") },
    {
      id: "actions",
      header: "Actions",
      cell: (row) => <GhostButton onClick={() => navigate(`/hardware-catalog/packages/${row.id}`)}>{admin ? "Edit" : "View"}</GhostButton>,
    },
  ];

  return (
    <div>
      <PageHeader
        title="POS packages"
        description="A package price stays as entered. Component prices are shown beside it and do not replace it."
        controls={
          admin ? (
            <Link to="/hardware-catalog/packages/new" className="inline-flex h-10 items-center rounded-full bg-accent px-5 text-sm font-medium text-white">
              New package
            </Link>
          ) : null
        }
      />
      <ErrorNote message={error} />
      <DataTable
        aria-label="POS packages"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        isLoading={loading}
        emptyState={{ title: "No packages", description: "Build a package from published products." }}
      />
    </div>
  );
}
