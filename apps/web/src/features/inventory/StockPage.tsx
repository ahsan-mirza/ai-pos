import { Permission, formatWeight, type StockRow, type StockStatus, type StockSummary, type StockView } from "@ai-pos/shared-types";
import { Boxes, History, Package, SlidersHorizontal, SquarePen, UtensilsCrossed } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { DataTable, type DataTableColumn, type TableFilter } from "../../components/ui/DataTable";
import { ErrorNote } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { useTenant } from "../../context/TenantContext";
import { useAuth } from "../../lib/auth";
import { actionButtonClass, actionIntentFromLabel } from "@ai-pos/ui";
import { ProductImage } from "../../components/ui/ProductImage";
import { AdjustStockModal } from "./AdjustStockModal";
import { inventoryApi, message } from "./api";
import { encodeFashionFilter, FashionFilterControl, fashionFilterValue, NO_FASHION_FILTER, type FashionFilterValue } from "./FashionFilters";
import {
  ScopedBrandFilterControl,
  ScopedModelFilterControl,
  StatusBadge,
  storeOptions,
  useCategories,
  useStoreScope,
  useStores,
} from "./shared";
import { LevelModal, MovementsModal } from "./StockModals";

const CONSOLIDATED_HINT = "Select a specific store branch to adjust stock levels.";

type StatusFilter = "all" | StockStatus;
type Dialog = { kind: "adjust" | "levels" | "history"; row: StockRow } | null;

const stockStatusOptions = [
  { value: "all", label: "All" },
  { value: "low", label: "Low" },
  { value: "out", label: "Out" },
  { value: "over", label: "Over" },
] as const;

const menuStatusOptions = [
  { value: "all", label: "All" },
  { value: "ok", label: "Available" },
  { value: "unavailable", label: "Unavailable" },
] as const;

function stockFilters(input: {
  stores: Parameters<typeof storeOptions>[0];
  pinned: boolean;
  storeId: string | null;
  setStoreId: (value: string | null) => void;
  categories: { id: string; name: string; sub_categories: { id: string; name: string }[] }[];
  categoryId: string | null;
  setCategoryId: (value: string | null) => void;
  subCategoryId: string | null;
  setSubCategoryId: (value: string | null) => void;
  brandId: string | null;
  setBrandId: (value: string | null) => void;
  modelId: string | null;
  setModelId: (value: string | null) => void;
  fashion: FashionFilterValue;
  setFashion: (value: FashionFilterValue) => void;
  status: string;
  setStatus: (value: StatusFilter) => void;
  menu: boolean;
}): TableFilter[] {
  return [
    {
      id: "store",
      label: "Store",
      value: input.storeId ?? "",
      clearedValue: input.pinned ? (input.storeId ?? "") : "",
      disabled: input.pinned,
      onChange: (value) => input.setStoreId(value || null),
      options: [
        ...(input.pinned ? [] : [{ value: "", label: "All Stores (Consolidated)" }]),
        ...storeOptions(input.stores),
      ],
    },
    {
      id: "category",
      label: "Category",
      value: input.categoryId ?? "",
      clears: ["sub", "model"],
      onChange: (value) => input.setCategoryId(value || null),
      options: [
        { value: "", label: "All categories" },
        ...input.categories.map((category) => ({ value: category.id, label: category.name })),
      ],
    },
    {
      id: "sub",
      label: "Sub-category",
      value: input.subCategoryId ?? "",
      clears: ["model"],
      disabled: (draft) => {
        const category = input.categories.find((item) => item.id === draft.category);
        return category === undefined || category.sub_categories.length === 0;
      },
      onChange: (value) => input.setSubCategoryId(value || null),
      options: (draft) => {
        const category = input.categories.find((item) => item.id === draft.category);
        return [
          { value: "", label: category ? "All sub-categories" : "Pick a category first" },
          ...(category?.sub_categories ?? []).map((sub) => ({ value: sub.id, label: sub.name })),
        ];
      },
    },
    {
      id: "brand",
      label: "Brand",
      value: input.brandId ?? "",
      clears: ["model"],
      onChange: (value) => input.setBrandId(value || null),
      Control: ScopedBrandFilterControl,
    },
    {
      id: "model",
      label: "Model",
      value: input.modelId ?? "",
      onChange: (value) => input.setModelId(value || null),
      Control: ScopedModelFilterControl,
    },
    {
      id: "fashion",
      label: "",
      value: encodeFashionFilter(input.fashion),
      clearedValue: encodeFashionFilter(NO_FASHION_FILTER),
      onChange: (value) => input.setFashion(fashionFilterValue(value)),
      Control: FashionFilterControl,
    },
    {
      id: "status",
      label: "Stock status",
      value: input.status,
      clearedValue: "all",
      onChange: (value) => input.setStatus(value as StatusFilter),
      options: input.menu ? menuStatusOptions : stockStatusOptions,
    },
  ];
}

const viewOptions = [
  { value: "stock", label: "Raw ingredients & stock" },
  { value: "menu", label: "Menu item availability" },
] as const;

export function StockPage() {
  const { can } = useAuth();
  const { isFnB } = useTenant();
  const { stores } = useStores();
  const { categories } = useCategories();
  const { storeId, setStoreId, pinned } = useStoreScope();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [subCategoryId, setSubCategoryId] = useState<string | null>(null);
  const [brandId, setBrandId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [view, setView] = useState<StockView>("stock");
  const menu = isFnB && view === "menu";
  const [fashion, setFashion] = useState<FashionFilterValue>(NO_FASHION_FILTER);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [summary, setSummary] = useState<StockSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [toast, setToast] = useState<string | null>(null);
  const manage = can(Permission.PortalInventoryManage);
  const canAdjust = can(Permission.InventoryAdjustStock);
  const dismissToast = useCallback(() => setToast(null), []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 150);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    try {
      setSummary(
        await inventoryApi.stock({
          store_id: storeId,
          category_id: categoryId,
          sub_category_id: subCategoryId,
          brand_id: brandId,
          product_model_id: modelId,
          status: status === "all" ? null : status,
          q: debounced.trim() || null,
          view: isFnB ? view : "stock",
          ...fashion,
        }),
      );
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load stock."));
    }
  }, [storeId, categoryId, subCategoryId, brandId, modelId, status, debounced, fashion, isFnB, view]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = summary?.rows ?? [];
  const store = stores.find((item) => item.id === storeId);
  const saved = () => {
    setDialog(null);
    void load();
  };

  const photoColumn: DataTableColumn<StockRow> = {
    id: "photo",
    header: "Photo",
    className: "w-14",
    cell: (row) => (
      <ProductImage
        url={row.thumb_url}
        className="h-10 w-10 rounded-lg object-cover"
        fallback={
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-surface text-charcoal/35" aria-hidden="true">
            {menu ? <UtensilsCrossed size={16} /> : <Package size={16} />}
          </span>
        }
      />
    ),
  };
  const columns: DataTableColumn<StockRow>[] = menu
    ? [
        photoColumn,
        { id: "sku", header: "SKU", className: "max-w-[130px] font-mono text-xs", accessorKey: "sku" },
        {
          id: "product",
          header: "Menu item",
          className: "min-w-[260px]",
          cell: (row) => (
            <>
              <span className="block font-medium">{row.name}</span>
              <span className="block text-xs text-charcoal/50">{row.availability_note ?? "Prepared to order"}</span>
            </>
          ),
        },
        { id: "category", header: "Category", accessorKey: "category" },
        {
          id: "portions",
          header: "Max portions",
          align: "right",
          className: "font-semibold",
          cell: (row) => (row.menu_status === "available" || row.menu_status === "unavailable" ? row.max_portions ?? 0 : "—"),
        },
        {
          id: "limiting",
          header: "Limited by",
          cell: (row) => row.limiting_ingredient ?? "—",
        },
        { id: "status", header: "Status", cell: (row) => <MenuBadge row={row} /> },
      ]
    : [
    photoColumn,
    { id: "sku", header: "SKU", className: "max-w-[130px] font-mono text-xs", accessorKey: "sku" },
    {
      id: "product",
      header: "Product",
      className: "min-w-[220px]",
      cell: (row) => (
        <>
          <span className="block font-medium">{row.name}</span>
          <span className="block text-xs text-charcoal/50">
            {[row.brand, row.model_name ?? row.model_number].filter(Boolean).join(" · ") || "—"}
            {row.is_serialized ? " · IMEI tracked" : ""}
          </span>
        </>
      ),
    },
    { id: "category", header: "Category", accessorKey: "category" },
    { id: "sub", header: "Sub-category", cell: (row) => row.sub_category ?? "—" },
    {
      id: "branch",
      header: "Store branch",
      cell: (row) =>
        row.store_code ? (
          <>
            <span className="block font-medium">{row.store_code}</span>
            <span className="block text-xs text-charcoal/50">{row.aisle_shelf_location ?? "No shelf set"}</span>
          </>
        ) : (
          <span className="text-charcoal/60">
            {row.store_count} {row.store_count === 1 ? "branch" : "branches"}
          </span>
        ),
    },
    {
      id: "on-hand",
      header: "On hand",
      align: "right",
      className: "font-semibold",
      accessorKey: "quantity_on_hand",
      cell: (row) => (
        <>
          <span>{row.sold_by_weight ? formatWeight(row.quantity_on_hand) : row.quantity_on_hand}</span>
          {row.lot_controlled ? (
            <span className="block text-xs font-normal text-charcoal/50">
              {row.eligible_quantity ?? 0} released in date
            </span>
          ) : null}
        </>
      ),
    },
    {
      id: "reserved",
      header: "Reserved",
      align: "right",
      accessorKey: "quantity_reserved",
      cell: (row) => (row.sold_by_weight ? formatWeight(row.quantity_reserved) : row.quantity_reserved),
    },
    { id: "min", header: "Min reorder", align: "right", accessorKey: "min_reorder_level" },
    { id: "status", header: "Status", cell: (row) => <StatusBadge status={row.status} /> },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">
            {menu
              ? summary?.consolidated
                ? "Portions buildable · all stores"
                : "Portions buildable"
              : summary?.consolidated
                ? "Units on hand · all stores"
                : "Units on hand"}
          </p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{summary?.units_on_hand ?? "—"}</p>
          <p className="mt-2 text-xs text-white/50">
            {store ? `${store.code} · ${store.name}` : `${stores.length} branches and warehouses`}
          </p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">{menu ? "Ingredients unavailable" : "Needs reorder"}</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {menu ? (summary?.out_count ?? "—") : (summary?.low_count ?? "—")}
          </p>
          <p className="mt-2 text-xs text-white/80">
            {menu
              ? "Prepared dishes missing a critical ingredient"
              : `${summary?.out_count ?? 0} ${summary?.out_count === 1 ? "product" : "products"} out of stock`}
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">{menu ? "Dishes listed" : "Products listed"}</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.length}</p>
          <p className="mt-2 text-xs text-charcoal/50">
            {menu
              ? "Prepared dishes, not shelf counts"
              : summary?.consolidated
                ? "Consolidated totals across branches"
                : "Branch-isolated stock"}
          </p>
        </article>
      </div>

      {isFnB ? (
        <SegmentedControl
          label="Inventory view"
          value={view}
          options={viewOptions}
          onChange={(next) => {
            setView(next);
            setStatus("all");
          }}
        />
      ) : null}

      <div className="overflow-hidden rounded-card border border-line bg-white">
        {error ? (
          <div className="px-6 pt-5">
            <ErrorNote message={error} />
          </div>
        ) : null}
        <DataTable
          aria-label={menu ? "Menu item availability" : "Stock levels"}
          variant="flush"
          minWidth="1080px"
          columns={columns}
          data={rows}
          getRowId={(row) => `${row.product_id}-${row.store_id ?? "all"}`}
          rowActionLabel={(row) => row.name}
          rowActions={(row) => [
            {
              id: "adjust",
              label: "Adjust",
              icon: SquarePen,
              hidden: !canAdjust,
              disabled: row.store_id === null,
              title: row.store_id === null ? CONSOLIDATED_HINT : "Adjust stock",
              onSelect: () => setDialog({ kind: "adjust", row }),
            },
            {
              id: "levels",
              label: "Reorder levels",
              icon: SlidersHorizontal,
              hidden: row.store_id === null || !manage,
              onSelect: () => setDialog({ kind: "levels", row }),
            },
            { id: "history", label: "Movement history", icon: History, onSelect: () => setDialog({ kind: "history", row }) },
          ]}
          toolbar={{
            search: {
              value: query,
              onChange: setQuery,
              label: "Search stock",
              placeholder: "Name, SKU, barcode, model, brand",
            },
            filters: stockFilters({
              stores,
              pinned,
              storeId,
              setStoreId,
              categories,
              categoryId,
              setCategoryId,
              subCategoryId,
              setSubCategoryId,
              brandId,
              setBrandId,
              modelId,
              setModelId,
              fashion,
              setFashion,
              status,
              setStatus,
              menu,
            }),
          }}
          isLoading={summary === null && error === null}
          emptyState={{ icon: Boxes, title: "No products match these filters" }}
          pagination={{
            mode: "client",
            resetKey: [storeId, categoryId, subCategoryId, brandId, modelId, status, debounced, view, JSON.stringify(fashion)],
          }}
        />
        {summary?.consolidated && (manage || canAdjust) ? (
          <p className="border-t border-line px-5 py-3 text-xs text-charcoal/50">{CONSOLIDATED_HINT}</p>
        ) : null}
      </div>

      {dialog?.kind === "adjust" ? (
        <AdjustStockModal
          row={dialog.row}
          onClose={() => setDialog(null)}
          onAdjusted={() => {
            setToast(`Stock adjusted successfully for ${dialog.row.name}. Ledger updated.`);
            saved();
          }}
        />
      ) : null}
      {dialog?.kind === "levels" ? <LevelModal row={dialog.row} onClose={() => setDialog(null)} onSaved={saved} /> : null}
      {dialog?.kind === "history" ? <MovementsModal row={dialog.row} onClose={() => setDialog(null)} /> : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function MenuBadge({ row }: { row: StockRow }) {
  if (row.menu_status === "unavailable" || row.status === "unavailable") return <StatusBadge status="unavailable" />;
  const label =
    row.menu_status === "meal" ? "Meal" : row.menu_status === "no_recipe" ? "No recipe" : "Available";
  const tone =
    row.menu_status === "no_recipe"
      ? "bg-surface text-charcoal/70 ring-1 ring-line"
      : "bg-charcoal text-white";
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>
      {label}
    </span>
  );
}

export function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={actionButtonClass(actionIntentFromLabel(label), "icon")}
    >
      {children}
    </button>
  );
}
