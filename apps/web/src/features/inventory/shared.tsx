import type { Brand, Category, ProductModel, StockStatus, Store } from "@ai-pos/shared-types";
import { stockStatusLabel } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { FilterSelect } from "../../components/ui/Field";
import type { SelectOption } from "../../components/ui/Select";
import { brandsApi, categoriesApi, message, modelsApi, storesApi } from "./api";

export function useStores() {
  const [stores, setStores] = useState<Store[]>([]);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setStores(await storesApi.list());
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load stores."));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { stores, error, reload };
}

export function useCategories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setCategories(await categoriesApi.list());
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load categories."));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { categories, setCategories, error, reload };
}

export function useBrands(subCategoryId?: string | null) {
  const [brands, setBrands] = useState<Brand[]>([]);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setBrands(await brandsApi.list({ sub_category_id: subCategoryId }));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load brands."));
    }
  }, [subCategoryId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { brands, error, reload };
}

/** Models for a sub-category and/or brand; nothing is fetched until at least one filter is set. */
export function useModels(subCategoryId: string | null, brandId: string | null) {
  const [models, setModels] = useState<ProductModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    if (!subCategoryId && !brandId) {
      setModels([]);
      return;
    }
    try {
      setModels(await modelsApi.list({ sub_category_id: subCategoryId, brand_id: brandId }));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load models."));
    }
  }, [subCategoryId, brandId]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { models, error, reload };
}

export function variantSummary(attributes: Record<string, string> | undefined): string {
  return Object.values(attributes ?? {}).join(" · ");
}

export { useStoreScope } from "../../lib/storeScope";

export function StoreSelect({
  stores,
  value,
  onChange,
  disabled = false,
  allowAll = true,
  label = "Store",
}: {
  stores: Store[];
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  allowAll?: boolean;
  label?: string;
}) {
  const options = [
    ...(allowAll ? [{ value: "", label: "All Stores (Consolidated)" }] : []),
    ...storeOptions(stores),
  ];
  return (
    <FilterSelect
      label={label}
      className="min-w-[240px]"
      value={value ?? ""}
      options={options}
      placeholder="Choose a store"
      disabled={disabled}
      onChange={(next) => onChange(next === "" ? null : next)}
    />
  );
}

export function storeOptions(
  stores: readonly Pick<Store, "id" | "code" | "name" | "is_warehouse" | "is_active">[],
): SelectOption[] {
  return stores.map((store) => ({
    value: store.id,
    label: `${store.code} · ${store.name}`,
    hint: [store.is_warehouse ? "Warehouse" : null, store.is_active === false ? "Inactive" : null]
      .filter(Boolean)
      .join(" · ") || undefined,
  }));
}

export function CategoryCascade({
  categories,
  categoryId,
  subCategoryId,
  onChange,
}: {
  categories: Category[];
  categoryId: string | null;
  subCategoryId: string | null;
  onChange: (categoryId: string | null, subCategoryId: string | null) => void;
}) {
  const current = categories.find((category) => category.id === categoryId);
  return (
    <>
      <FilterSelect
        label="Category"
        className="min-w-[190px]"
        value={categoryId ?? ""}
        options={[
          { value: "", label: "All categories" },
          ...categories.map((category) => ({ value: category.id, label: category.name })),
        ]}
        onChange={(next) => onChange(next === "" ? null : next, null)}
      />
      <FilterSelect
        label="Sub-category"
        className="min-w-[210px]"
        value={subCategoryId ?? ""}
        disabled={current === undefined || current.sub_categories.length === 0}
        options={[
          { value: "", label: current ? "All sub-categories" : "Pick a category first" },
          ...(current?.sub_categories ?? []).map((sub) => ({ value: sub.id, label: sub.name })),
        ]}
        onChange={(next) => onChange(categoryId, next === "" ? null : next)}
      />
    </>
  );
}

export function BrandModelFilters({
  subCategoryId,
  brandId,
  modelId,
  onChange,
}: {
  subCategoryId: string | null;
  brandId: string | null;
  modelId: string | null;
  onChange: (brandId: string | null, modelId: string | null) => void;
}) {
  const { brands } = useBrands(subCategoryId);
  const { models } = useModels(brandId ? subCategoryId : null, brandId);
  return (
    <>
      <FilterSelect
        label="Brand"
        className="min-w-[170px]"
        value={brandId ?? ""}
        options={[{ value: "", label: "All brands" }, ...brands.map((brand) => ({ value: brand.id, label: brand.name }))]}
        onChange={(next) => onChange(next === "" ? null : next, null)}
      />
      <FilterSelect
        label="Model"
        className="min-w-[210px]"
        value={modelId ?? ""}
        disabled={brandId === null}
        options={[
          { value: "", label: brandId ? "All models" : "Pick a brand first" },
          ...models.map((model) => ({ value: model.id, label: model.name, hint: model.sub_category_name })),
        ]}
        onChange={(next) => onChange(brandId, next === "" ? null : next)}
      />
    </>
  );
}

const badgeStyles: Record<StockStatus, string> = {
  ok: "bg-charcoal text-white",
  low: "bg-accent text-white",
  out: "bg-accent/10 text-accent ring-1 ring-accent/40",
  over: "bg-surface text-charcoal ring-1 ring-line",
  unavailable: "bg-accent/10 text-accent ring-1 ring-accent/40",
};

export function StatusBadge({ status }: { status: StockStatus }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${badgeStyles[status]}`}>
      {stockStatusLabel(status)}
    </span>
  );
}

export function DocStatus({ status }: { status: string }) {
  const accent = ["ordered", "requested", "in_transit", "partially_received"].includes(status);
  const muted = status === "cancelled";
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ${
        muted ? "bg-surface text-charcoal/50" : accent ? "bg-accent text-white" : "bg-charcoal text-white"
      }`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function statusLabel(status: string): string {
  const words = status.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatDate(value: string | null): string {
  if (value === null) return "—";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
