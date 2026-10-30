import {
  Permission,
  formatMoney,
  variantAttributeLabel,
  type MatrixCell,
  type ProductModel,
  type VariantMatrix,
} from "@ai-pos/shared-types";
import { downloadCsv } from "@ai-pos/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { message, modelsApi, storesApi } from "./api";
import { MatrixBuilderModal } from "./VariantMatrixPanel";
import { VariantGrid } from "./VariantGrid";
import { ModelFormModal } from "./ModelFormModal";
import { useBrands, useCategories } from "./shared";
import { useProductDetails } from "./useProductDetails";

interface CurveCell {
  product_id: string;
  sold: number;
}

interface Broken {
  store_name: string;
  size: string;
  color: string | null;
  suggest_from_name: string | null;
  quantity: number;
}

interface Report {
  cells: CurveCell[];
  broken_runs: Broken[];
}

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

function emptyMatrix(model: ProductModel): VariantMatrix {
  return {
    model_id: model.id,
    model_name: model.name,
    axes: [],
    cells: [],
    on_hand: 0,
    sold_90d: 0,
    created: 0,
    skipped: 0,
  };
}

/** Management grid for one model's variants: stock, sales, price, and bulk edits. */
export function SizeCurvePage() {
  const { currency } = useCurrency();
  const { can, user } = useAuth();
  const manage = can(Permission.PortalInventoryManage) && user?.store_id === null;
  const seeCost = can(Permission.PortalInventoryManage);
  const { brands } = useBrands();
  const { categories } = useCategories();
  const [models, setModels] = useState<ProductModel[]>([]);
  const [stores, setStores] = useState<{ id: string; name: string }[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [brandId, setBrandId] = useState("");
  const [modelId, setModelId] = useState("");
  const [storeId, setStoreId] = useState("");
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState(() => isoDaysAgo(30));
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [matrix, setMatrix] = useState<VariantMatrix | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openCell, setOpenCell] = useState<MatrixCell | null>(null);
  const [creating, setCreating] = useState(false);
  const [building, setBuilding] = useState(false);
  const [bulk, setBulk] = useState<"price" | "activate" | "deactivate" | "reorder" | "barcode" | null>(null);
  const [bulkPrice, setBulkPrice] = useState("");
  const [bulkStore, setBulkStore] = useState("");
  const [bulkReorder, setBulkReorder] = useState("0");
  const [busy, setBusy] = useState(false);

  const loadModels = useCallback(() => {
    modelsApi.list().then(setModels).catch(() => setModels([]));
    storesApi.list().then((rows) => setStores(rows.map((store) => ({ id: store.id, name: store.name })))).catch(() => setStores([]));
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const choices = useMemo(
    () =>
      models.filter(
        (model) =>
          (categoryId === "" || model.category_id === categoryId) && (brandId === "" || model.brand_id === brandId),
      ),
    [models, categoryId, brandId],
  );
  const model = choices.find((row) => row.id === modelId) ?? models.find((row) => row.id === modelId) ?? null;

  const load = useCallback(async () => {
    if (!modelId) return null;
    setError(null);
    try {
      const [grid, curve] = await Promise.all([
        modelsApi.matrix(modelId, storeId || null),
        apiGet<Report>(`/api/v1/reports/size-curve?model_id=${modelId}&from=${from}&to=${to}${storeId ? `&store_id=${storeId}` : ""}`),
      ]);
      return { modelId, grid, curve };
    } catch (caught) {
      setError(message(caught, "Could not load the matrix."));
      return null;
    }
  }, [modelId, storeId, from, to]);

  useEffect(() => {
    setMatrix(null);
    setReport(null);
    setSelected(new Set());
    setOpenCell(null);
  }, [modelId]);

  useEffect(() => {
    let cancelled = false;
    void load().then((result) => {
      if (cancelled || result === null || result.modelId !== modelId) return;
      setMatrix(result.grid);
      setReport(result.curve);
    });
    return () => {
      cancelled = true;
    };
  }, [load, modelId]);

  const sold = useMemo(() => new Map((report?.cells ?? []).map((cell) => [cell.product_id, cell.sold])), [report]);
  const cells = useMemo(() => {
    const rows = matrix?.cells ?? [];
    if (status === "active") return rows.filter((cell) => cell.is_active !== false);
    if (status === "inactive") return rows.filter((cell) => cell.is_active === false);
    return rows;
  }, [matrix, status]);

  const details = useProductDetails(openCell?.product_id ?? null, { enabled: false, status: null, query: "" });

  const toggle = (cell: MatrixCell) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(cell.product_id)) next.delete(cell.product_id);
      else next.add(cell.product_id);
      return next;
    });
  };

  const exportCells = (rows: MatrixCell[]) => {
    downloadCsv(
      "size-color-matrix.csv",
      ["Name", "SKU", "Barcode", "Attributes", "Price", "Price source", "On hand", "Sold", "Status"],
      rows.map((cell) => [
        cell.name,
        cell.sku,
        cell.barcode,
        Object.entries(cell.attributes).map(([key, value]) => `${key}=${value}`).join("; "),
        (cell.price_cents / 100).toFixed(2),
        cell.price_source === "override" ? "Override" : "Inherited",
        String(cell.on_hand),
        String(sold.get(cell.product_id) ?? cell.sold_90d),
        cell.is_active === false ? "Inactive" : "Active",
      ]),
    );
  };

  const runBulk = async () => {
    if (!modelId || selected.size === 0 || bulk === null) return;
    setBusy(true);
    setError(null);
    try {
      const price = Math.round(Number(bulkPrice) * 100);
      await modelsApi.bulkMatrix(modelId, {
        product_ids: [...selected],
        price_cents: bulk === "price" ? price : null,
        is_active: bulk === "activate" ? true : bulk === "deactivate" ? false : null,
        store_id: bulk === "reorder" ? bulkStore : null,
        min_reorder_level: bulk === "reorder" ? Number(bulkReorder) : null,
        assign_missing_barcodes: bulk === "barcode",
      });
      setBulk(null);
      setSelected(new Set());
      await load();
    } catch (caught) {
      setError(message(caught, "Could not update the variants."));
    } finally {
      setBusy(false);
    }
  };

  const priceOk = bulk !== "price" || (Number.isFinite(Number(bulkPrice)) && Number(bulkPrice) >= 0 && bulkPrice !== "");
  const reorderOk = bulk !== "reorder" || (bulkStore !== "" && Number.isInteger(Number(bulkReorder)) && Number(bulkReorder) >= 0);

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-charcoal">Size & color matrix</h1>
          <p className="mt-1 max-w-2xl text-sm text-charcoal/60">
            Manage product variants, stock availability, pricing, and sales performance by size and color.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {manage ? <PrimaryButton onClick={() => setCreating(true)}>Create model</PrimaryButton> : null}
          {manage ? (
            <GhostButton disabled={!model} onClick={() => setBuilding(true)}>
              Generate missing variants
            </GhostButton>
          ) : null}
          <GhostButton disabled={cells.length === 0} onClick={() => exportCells(cells)}>
            Export matrix
          </GhostButton>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <FilterSelect
          label="Category"
          className="w-44"
          value={categoryId}
          placeholder="All categories"
          options={[{ value: "", label: "All categories" }, ...categories.map((category) => ({ value: category.id, label: category.name }))]}
          onChange={(value) => {
            setCategoryId(value);
            setModelId("");
          }}
        />
        <FilterSelect
          label="Brand"
          className="w-44"
          value={brandId}
          placeholder="All brands"
          options={[{ value: "", label: "All brands" }, ...brands.map((brand) => ({ value: brand.id, label: brand.name }))]}
          onChange={(value) => {
            setBrandId(value);
            setModelId("");
          }}
        />
        <FilterSelect
          label="Model"
          className="w-56"
          value={modelId}
          placeholder="Choose a model"
          options={[{ value: "", label: "Choose a model" }, ...choices.map((row) => ({ value: row.id, label: row.name }))]}
          onChange={setModelId}
        />
        <FilterSelect
          label="Store"
          className="w-44"
          value={storeId}
          placeholder="All stores"
          options={[{ value: "", label: "All stores" }, ...stores.map((store) => ({ value: store.id, label: store.name }))]}
          onChange={setStoreId}
        />
        <FilterSelect
          label="Status"
          className="w-36"
          value={status}
          options={[
            { value: "all", label: "All" },
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
          ]}
          onChange={setStatus}
        />
        <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
      </div>
      <ErrorNote message={error} />

      {!modelId ? (
        <p className="rounded-2xl border border-dashed border-line px-4 py-10 text-center text-sm text-charcoal/50">
          Choose a model to see its size and colour grid.
        </p>
      ) : matrix ? (
        <section className="rounded-2xl border border-line p-4">
          <h2 className="text-base font-semibold">{matrix.model_name}</h2>
          <p className="mb-3 text-xs text-charcoal/60">
            {cells.length} variants · {matrix.on_hand} on hand
            {storeId ? " at this store" : ""} · number is stock, second line is units sold in the selected dates
          </p>
          {selected.size > 0 && manage ? (
            <div className="mb-3 flex flex-wrap gap-2">
              <GhostButton onClick={() => setBulk("price")}>Update prices</GhostButton>
              <GhostButton onClick={() => setBulk("activate")}>Activate</GhostButton>
              <GhostButton onClick={() => setBulk("deactivate")}>Deactivate</GhostButton>
              <GhostButton onClick={() => setBulk("reorder")}>Reorder levels</GhostButton>
              <GhostButton onClick={() => setBulk("barcode")}>Assign missing barcodes</GhostButton>
              <GhostButton onClick={() => exportCells(cells.filter((cell) => selected.has(cell.product_id)))}>
                Export selected
              </GhostButton>
            </div>
          ) : null}
          <VariantGrid
            axes={matrix.axes}
            cells={cells}
            swatches={model?.axis_swatches}
            selected={selected}
            onOpen={setOpenCell}
            onToggle={manage ? toggle : undefined}
            soldFor={(cell) => sold.get(cell.product_id) ?? 0}
          />
          {report && report.broken_runs.length > 0 ? (
            <ul className="mt-4 space-y-1 text-sm">
              {report.broken_runs.map((run, index) => (
                <li key={`${run.store_name}-${run.size}-${index}`}>
                  {run.store_name} is out of {run.size}
                  {run.color ? ` / ${run.color}` : ""}
                  {run.suggest_from_name ? ` — move ${run.quantity} from ${run.suggest_from_name}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {openCell ? (
        <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-md overflow-y-auto border-l border-line bg-white p-5 shadow-xl">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-lg font-semibold">{openCell.name}</h2>
            <GhostButton onClick={() => setOpenCell(null)}>Close</GhostButton>
          </div>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-charcoal/50">SKU</dt><dd>{openCell.sku}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-charcoal/50">Barcode</dt><dd>{openCell.barcode}</dd></div>
            <div className="flex justify-between gap-3">
              <dt className="text-charcoal/50">Selling price</dt>
              <dd>
                {formatMoney(openCell.price_cents, currency)}{" "}
                <span className="text-charcoal/50">{openCell.price_source === "override" ? "Override" : "Inherited"}</span>
              </dd>
            </div>
            {seeCost ? (
              <div className="flex justify-between gap-3">
                <dt className="text-charcoal/50">Cost</dt>
                <dd>
                  {details.purchases.state === "ready" && details.purchases.data.latest_unit_cost_cents !== null
                    ? formatMoney(details.purchases.data.latest_unit_cost_cents, currency)
                    : openCell.cost_cents != null
                      ? formatMoney(openCell.cost_cents, currency)
                      : "—"}
                </dd>
              </div>
            ) : null}
            <div className="flex justify-between gap-3">
              <dt className="text-charcoal/50">Status</dt>
              <dd>{openCell.is_active === false ? "Inactive" : "Active"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-charcoal/50">Sold</dt>
              <dd>{sold.get(openCell.product_id) ?? openCell.sold_90d}</dd>
            </div>
          </dl>
          <ul className="mt-3 text-sm text-charcoal/70">
            {Object.entries(openCell.attributes).map(([key, value]) => (
              <li key={key}>
                {variantAttributeLabel(key)}: {value}
              </li>
            ))}
          </ul>
          <h3 className="mt-4 text-sm font-semibold">Stock by branch</h3>
          <ul className="mt-1 text-sm">
            {Object.entries(openCell.by_store).length === 0 ? <li className="text-charcoal/50">No stock rows</li> : null}
            {Object.entries(openCell.by_store).map(([code, units]) => (
              <li key={code} className="flex justify-between">
                <span>{code}</span>
                <span className="tabular-nums">{units}</span>
              </li>
            ))}
          </ul>
          {seeCost && details.purchases.state === "ready" ? (
            <>
              <h3 className="mt-4 text-sm font-semibold">Purchase history</h3>
              <ul className="mt-1 space-y-1 text-sm">
                {details.purchases.data.rows.slice(0, 5).map((row) => (
                  <li key={`${row.purchase_order_id}-${row.grn_number ?? ""}`}>
                    {row.po_number} · {row.supplier_name} · {row.quantity_received} at {formatMoney(row.unit_cost_cents, currency)}
                  </li>
                ))}
                {details.purchases.data.rows.length === 0 ? <li className="text-charcoal/50">No receipts yet</li> : null}
              </ul>
            </>
          ) : null}
          <Link className="mt-5 inline-block text-sm font-semibold text-accent" to={`/inventory/products?product=${openCell.product_id}`}>
            Open product
          </Link>
        </aside>
      ) : null}

      {creating ? (
        <ModelFormModal
          model={null}
          brands={brands}
          categories={categories}
          initialBrandId={brandId}
          onClose={() => setCreating(false)}
          onSaved={async (saved) => {
            setCreating(false);
            setMatrix(null);
            setModels((current) => [saved, ...current.filter((row) => row.id !== saved.id)]);
            setModelId(saved.id);
            setBuilding(true);
          }}
        />
      ) : null}
      {building && model ? (
        <MatrixBuilderModal
          model={model}
          existing={matrix ?? emptyMatrix(model)}
          onClose={() => setBuilding(false)}
          onGenerated={() => {
            setBuilding(false);
            void load();
          }}
        />
      ) : null}
      {bulk ? (
        <Modal
          title={
            bulk === "price"
              ? "Update selling prices"
              : bulk === "reorder"
                ? "Update reorder levels"
                : bulk === "barcode"
                  ? "Assign missing barcodes"
                  : bulk === "activate"
                    ? "Activate variants"
                    : "Deactivate variants"
          }
          subtitle={`${selected.size} variant${selected.size === 1 ? "" : "s"}. Stock quantities are not changed.`}
          onClose={() => (busy ? undefined : setBulk(null))}
          footer={
            <>
              <GhostButton disabled={busy} onClick={() => setBulk(null)}>Cancel</GhostButton>
              <PrimaryButton disabled={busy || !priceOk || !reorderOk} onClick={() => void runBulk()}>
                {busy ? "Saving…" : "Confirm"}
              </PrimaryButton>
            </>
          }
        >
          <div className="space-y-3 text-sm">
            <p>
              Current prices:{" "}
              {[...new Set(cells.filter((cell) => selected.has(cell.product_id)).map((cell) => formatMoney(cell.price_cents, currency)))].join(", ") || "—"}
            </p>
            {bulk === "price" ? (
              <TextField label={`New price (${currency})`} inputMode="decimal" value={bulkPrice} onChange={(event) => setBulkPrice(event.target.value)} />
            ) : null}
            {bulk === "reorder" ? (
              <>
                <FilterSelect
                  label="Store"
                  value={bulkStore}
                  placeholder="Choose a store"
                  options={stores.map((store) => ({ value: store.id, label: store.name }))}
                  onChange={setBulkStore}
                />
                <TextField label="Min reorder level" inputMode="numeric" value={bulkReorder} onChange={(event) => setBulkReorder(event.target.value)} />
              </>
            ) : null}
            {bulk === "activate" || bulk === "deactivate" ? (
              <p>{bulk === "activate" ? "These variants become sellable again." : "These variants stay in stock and history, and the register will not sell them."}</p>
            ) : null}
            {bulk === "barcode" ? <p>Only variants with a blank barcode receive a new in-store barcode.</p> : null}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
