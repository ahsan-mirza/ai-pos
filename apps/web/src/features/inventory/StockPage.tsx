import { Permission, formatWeight, type StockRow, type StockStatus, type StockSummary } from "@ai-pos/shared-types";
import { Boxes, History, SlidersHorizontal, SquarePen } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, filterLabel } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../../lib/auth";
import { AdjustStockModal } from "./AdjustStockModal";
import { inventoryApi, message } from "./api";
import { FashionFilters, NO_FASHION_FILTER, type FashionFilterValue } from "./FashionFilters";
import {
  BrandModelFilters,
  CategoryCascade,
  StatusBadge,
  StoreSelect,
  useCategories,
  useStoreScope,
  useStores,
} from "./shared";
import { LevelModal, MovementsModal } from "./StockModals";

const CONSOLIDATED_HINT = "Select a specific store branch to adjust stock levels.";

type StatusFilter = "all" | StockStatus;
type Dialog = { kind: "adjust" | "levels" | "history"; row: StockRow } | null;

const statusOptions = [
  { value: "all", label: "All" },
  { value: "low", label: "Low" },
  { value: "out", label: "Out" },
  { value: "over", label: "Over" },
] as const;

export function StockPage() {
  const { can } = useAuth();
  const { stores } = useStores();
  const { categories } = useCategories();
  const { storeId, setStoreId, pinned } = useStoreScope();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [subCategoryId, setSubCategoryId] = useState<string | null>(null);
  const [brandId, setBrandId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("all");
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
          ...fashion,
        }),
      );
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load stock."));
    }
  }, [storeId, categoryId, subCategoryId, brandId, modelId, status, debounced, fashion]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = summary?.rows ?? [];
  const store = stores.find((item) => item.id === storeId);
  const saved = () => {
    setDialog(null);
    void load();
  };

  const columns: DataTableColumn<StockRow>[] = [
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
      cell: (row) => (row.sold_by_weight ? formatWeight(row.quantity_on_hand) : row.quantity_on_hand),
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
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1">
          {canAdjust ? (
            <AdjustButton consolidated={row.store_id === null} onClick={() => setDialog({ kind: "adjust", row })} />
          ) : null}
          {row.store_id !== null && manage ? (
            <IconButton label="Reorder levels & shelf" onClick={() => setDialog({ kind: "levels", row })}>
              <SlidersHorizontal size={15} />
            </IconButton>
          ) : null}
          <IconButton label="Movement history" onClick={() => setDialog({ kind: "history", row })}>
            <History size={15} />
          </IconButton>
        </div>
      ),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">{summary?.consolidated ? "Units on hand · all stores" : "Units on hand"}</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{summary?.units_on_hand ?? "—"}</p>
          <p className="mt-2 text-xs text-white/50">
            {store ? `${store.code} · ${store.name}` : `${stores.length} branches and warehouses`}
          </p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Needs reorder</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{summary?.low_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/80">
            {summary?.out_count ?? 0} {summary?.out_count === 1 ? "product" : "products"} out of stock
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Products listed</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.length}</p>
          <p className="mt-2 text-xs text-charcoal/50">
            {summary?.consolidated ? "Consolidated totals across branches" : "Branch-isolated stock"}
          </p>
        </article>
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end gap-3 p-6 pb-5">
          <StoreSelect stores={stores} value={storeId} onChange={setStoreId} disabled={pinned} allowAll={!pinned} />
          <CategoryCascade
            categories={categories}
            categoryId={categoryId}
            subCategoryId={subCategoryId}
            onChange={(category, sub) => {
              setCategoryId(category);
              setSubCategoryId(sub);
              setModelId(null);
            }}
          />
          <BrandModelFilters
            subCategoryId={subCategoryId}
            brandId={brandId}
            modelId={modelId}
            onChange={(brand, model) => {
              setBrandId(brand);
              setModelId(model);
            }}
          />
          <FashionFilters value={fashion} onChange={setFashion} />
          <label className="min-w-[220px] flex-1">
            <span className={filterLabel}>Search</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Name, SKU, barcode, model, brand"
              className="h-11 w-full rounded-full border border-line bg-white px-5 text-sm font-medium text-charcoal transition-all placeholder:font-normal placeholder:text-charcoal/40 hover:border-gray-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </label>
          <SegmentedControl label="Stock status" value={status} options={statusOptions} onChange={setStatus} />
          {error ? (
            <div className="w-full">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
        <DataTable
          aria-label="Stock levels"
          variant="flush"
          minWidth="1080px"
          columns={columns}
          data={rows}
          getRowId={(row) => `${row.product_id}-${row.store_id ?? "all"}`}
          isLoading={summary === null && error === null}
          emptyState={{ icon: Boxes, title: "No products match these filters" }}
          pagination={{
            mode: "client",
            resetKey: [storeId, categoryId, subCategoryId, brandId, modelId, status, debounced, JSON.stringify(fashion)],
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

function AdjustButton({ consolidated, onClick }: { consolidated: boolean; onClick: () => void }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        onClick={consolidated ? undefined : onClick}
        aria-disabled={consolidated}
        aria-label={consolidated ? `Adjust stock. ${CONSOLIDATED_HINT}` : "Adjust stock"}
        className={`flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-xs font-semibold transition-colors ${
          consolidated
            ? "cursor-not-allowed border-line text-charcoal/30"
            : "border-line text-charcoal hover:border-accent hover:text-accent"
        }`}
      >
        <SquarePen size={14} aria-hidden="true" />
        Adjust
      </button>
      {consolidated ? (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full right-0 z-20 mb-2 w-56 rounded-xl bg-charcoal px-3 py-2 text-left text-xs font-normal normal-case tracking-normal text-white opacity-0 shadow-lg transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
        >
          {CONSOLIDATED_HINT}
        </span>
      ) : null}
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
      className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
    >
      {children}
    </button>
  );
}
