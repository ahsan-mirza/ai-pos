import { Permission, type ProductModel } from "@ai-pos/shared-types";
import { downloadCsv, type DataTableColumn } from "@ai-pos/ui";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { DataTable } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SearchField } from "../../components/ui/Field";
import { useAuth } from "../../lib/auth";
import { message, modelsApi } from "./api";
import { ModelFormModal } from "./ModelFormModal";
import { IconButton } from "./StockPage";
import { useBrands, useCategories } from "./shared";

function specLabel(model: ProductModel): string {
  const parts = [model.release_year ? String(model.release_year) : null, model.code, model.season].filter(
    (part): part is string => Boolean(part),
  );
  return parts.length > 0 ? parts.join(" / ") : "—";
}

/** Catalog models under each brand. Electronics and fashion only. */
export function ModelsPage() {
  const { can, user } = useAuth();
  const manage = can(Permission.PortalInventoryManage) && user?.store_id === null;
  const confirm = useConfirm();
  const { brands, error: brandsError } = useBrands();
  const { categories, error: categoriesError } = useCategories();
  const [params, setParams] = useSearchParams();
  const brandId = params.get("brand_id") ?? "";
  const [query, setQuery] = useState("");
  const [models, setModels] = useState<ProductModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ProductModel | "new" | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setModels(await modelsApi.list({ brand_id: brandId || null }));
      setLoadError(null);
    } catch (caught) {
      setLoadError(message(caught, "Could not load models."));
    } finally {
      setLoading(false);
    }
  }, [brandId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      models.filter((model) => {
        if (needle === "") return true;
        return `${model.name} ${model.code ?? ""} ${model.brand_name}`.toLowerCase().includes(needle);
      }),
    [models, needle],
  );

  const columns = useMemo<DataTableColumn<ProductModel>[]>(() => {
    const defined: DataTableColumn<ProductModel>[] = [
      { id: "name", header: "Model name", sortValue: (row) => row.name, cell: (row) => <span className="font-semibold">{row.name}</span> },
      {
        id: "brand",
        header: "Brand",
        sortValue: (row) => row.brand_name,
        cell: (row) => (
          <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold text-charcoal/80">{row.brand_name}</span>
        ),
      },
      {
        id: "category",
        header: "Category / sub-category",
        sortValue: (row) => `${row.category_name} ${row.sub_category_name}`,
        cell: (row) => (
          <span className="text-charcoal/80">
            {row.category_name} &gt; {row.sub_category_name}
          </span>
        ),
      },
      {
        id: "spec",
        header: "Release / year / spec code",
        sortValue: (row) => specLabel(row),
        cell: (row) => <span className="font-mono text-xs text-charcoal/70">{specLabel(row)}</span>,
      },
      {
        id: "linked",
        header: "Linked products",
        align: "right",
        sortValue: (row) => row.variant_count,
        cell: (row) => row.variant_count,
      },
    ];
    if (manage) {
      defined.push({
        id: "actions",
        header: "Actions",
        align: "right",
        cell: (row) => (
          <div className="flex justify-end gap-1">
            <IconButton label={`Edit ${row.name}`} onClick={() => setEditing(row)}>
              <Pencil size={14} />
            </IconButton>
            <IconButton label={`Delete ${row.name}`} onClick={() => void remove(row)}>
              <Trash2 size={14} />
            </IconButton>
          </div>
        ),
      });
    }
    return defined;
  }, [manage]);

  const exportModels = () => {
    downloadCsv(
      "models.csv",
      ["Model", "Brand", "Category", "Sub-category", "Release", "Code", "Linked products"],
      visible.map((row) => [
        row.name,
        row.brand_name,
        row.category_name,
        row.sub_category_name,
        row.release_year ? String(row.release_year) : "",
        row.code ?? "",
        String(row.variant_count),
      ]),
    );
  };

  const setBrand = (next: string) => {
    setParams(next ? { brand_id: next } : {}, { replace: true });
  };

  const remove = async (model: ProductModel) => {
    if (model.variant_count > 0) {
      setError(
        `${model.name} has ${model.variant_count} linked product${model.variant_count === 1 ? "" : "s"}. Move or delete those SKUs before deleting the model.`,
      );
      return;
    }
    const accepted = await confirm({
      title: "Delete model",
      message: `Delete ${model.name}?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await modelsApi.remove(model.id);
      await reload();
    } catch (caught) {
      setError(message(caught, "Could not delete the model."));
    }
  };

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Models</h2>
          <p className="max-w-xl text-sm text-charcoal/60">
            Manage product models mapped under catalog brands (e.g., Apple → iPhone 15 Pro, Samsung → Galaxy S24).
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <SearchField
            className="w-64"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search model name, code..."
          />
          <FilterSelect
            label="Brand"
            className="w-52"
            value={brandId}
            placeholder="All brands"
            options={[{ value: "", label: "All brands" }, ...brands.map((brand) => ({ value: brand.id, label: brand.name }))]}
            onChange={setBrand}
          />
          <GhostButton type="button" onClick={exportModels} disabled={visible.length === 0}>
            Export
          </GhostButton>
          {manage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <span className="inline-flex items-center gap-2">
                <Plus size={16} aria-hidden="true" /> New model
              </span>
            </PrimaryButton>
          ) : null}
        </div>
      </div>
      <ErrorNote message={error ?? brandsError ?? categoriesError} />
      <DataTable
        aria-label="Models"
        minWidth="880px"
        columns={columns}
        data={visible}
        getRowId={(row) => row.id}
        isLoading={loading}
        error={loadError}
        onRetry={() => void reload()}
        pagination={{ mode: "client", resetKey: `${brandId}:${needle}` }}
        emptyState={{ title: "No models match", description: "Try another brand or search." }}
      />
      {editing !== null ? (
        <ModelFormModal
          model={editing === "new" ? null : editing}
          brands={brands}
          categories={categories}
          initialBrandId={brandId}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await reload();
          }}
        />
      ) : null}
    </section>
  );
}
