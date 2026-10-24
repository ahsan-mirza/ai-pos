import { Permission, type ProductModel } from "@ai-pos/shared-types";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, FilterSelect, PrimaryButton, SearchField } from "../../components/ui/Field";
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ProductModel | "new" | null>(null);

  const reload = useCallback(async () => {
    try {
      setModels(await modelsApi.list({ brand_id: brandId || null }));
      setLoadError(null);
    } catch (caught) {
      setLoadError(message(caught, "Could not load models."));
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
          {manage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <span className="inline-flex items-center gap-2">
                <Plus size={16} aria-hidden="true" /> New model
              </span>
            </PrimaryButton>
          ) : null}
        </div>
      </div>
      <ErrorNote message={error ?? loadError ?? brandsError ?? categoriesError} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-3 font-medium">Model name</th>
              <th className="pb-3 font-medium">Brand</th>
              <th className="pb-3 font-medium">Category / sub-category</th>
              <th className="pb-3 font-medium">Release / year / spec code</th>
              <th className="pb-3 text-right font-medium">Linked products</th>
              {manage ? <th className="pb-3 text-right font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {visible.map((model) => (
              <tr key={model.id} className="border-t border-line">
                <td className="py-3 font-semibold">{model.name}</td>
                <td className="py-3">
                  <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold text-charcoal/80">
                    {model.brand_name}
                  </span>
                </td>
                <td className="py-3 text-charcoal/80">
                  {model.category_name} &gt; {model.sub_category_name}
                </td>
                <td className="py-3 font-mono text-xs text-charcoal/70">{specLabel(model)}</td>
                <td className="py-3 text-right tabular-nums">{model.variant_count}</td>
                {manage ? (
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      <IconButton label={`Edit ${model.name}`} onClick={() => setEditing(model)}>
                        <Pencil size={14} />
                      </IconButton>
                      <IconButton label={`Delete ${model.name}`} onClick={() => void remove(model)}>
                        <Trash2 size={14} />
                      </IconButton>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && !loadError ? <p className="py-8 text-sm text-charcoal/60">No models match.</p> : null}
      </div>
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
