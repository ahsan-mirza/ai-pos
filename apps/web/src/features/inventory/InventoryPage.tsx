import { Permission, formatMoney, noMatchesMessage, type Product } from "@ai-pos/shared-types";
import { Package, Pencil, Plus, Power, Printer, Search, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { GhostButton, PrimaryButton, SearchField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiGet } from "../../lib/api";
import { ProductImage } from "../../components/ui/ProductImage";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { inventoryApi, labelsApi, message } from "./api";
import { ProductDetailDrawer } from "./ProductDetailDrawer";
import { ImportWizardModal } from "./import/ImportWizardModal";
import { ProductFormModal } from "./ProductFormModal";
import { BrandModelFilters } from "./shared";
import { IconButton } from "./StockPage";
import { useProductSearch } from "./useProductSearch";

export function InventoryPage() {
  const { currency } = useCurrency();
  const [live, setLive] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);
  const products = useMemo(() => (live ?? []).map((product) => ({ ...product, currency })), [live, currency]);
  const source = live === null ? "loading" : "live";
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [brandId, setBrandId] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const search = useProductSearch(query, products, source === "live");
  const { debouncedQuery, searching, resolve } = search;
  const hits = search.hits.filter(
    ({ product }) =>
      (brandId === null || product.brand_id === brandId) && (modelId === null || product.product_model_id === modelId),
  );

  const { can } = useAuth();
  const manage = can(Permission.PortalInventoryManage);
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [importing, setImporting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Product | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [rowBusy, setRowBusy] = useState(false);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const requestedProduct = params.get("product");
  const openedProduct = useRef<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const closeTimer = useRef<number | undefined>(undefined);
  const selected = products.find((product) => product.id === selectedId) ?? null;
  const open = selected !== null && !closing && source === "live";

  const closeDrawer = useCallback(() => {
    setClosing(true);
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      setSelectedId(null);
      setClosing(false);
    }, 200);
  }, []);

  const selectProduct = useCallback((id: string) => {
    window.clearTimeout(closeTimer.current);
    setClosing(false);
    setSelectedId(id);
  }, []);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  const toggleRow = (id: string) => {
    if (selectedId === id && !closing) closeDrawer();
    else selectProduct(id);
  };

  const reload = useCallback(() => {
    apiGet<Product[]>("/api/v1/products?limit=500")
      .then((rows) => {
        setLive(rows);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (!requestedProduct || requestedProduct === openedProduct.current || live === null) return;
    const found = live.find((product) => product.id === requestedProduct);
    if (found) {
      openedProduct.current = requestedProduct;
      selectProduct(found.id);
      return;
    }
    openedProduct.current = requestedProduct;
    apiGet<Product>(`/api/v1/products/${requestedProduct}`)
      .then((product) => {
        setLive((current) => (current?.some((row) => row.id === product.id) ? current : [product, ...(current ?? [])]));
        selectProduct(product.id);
      })
      .catch(() => undefined);
  }, [requestedProduct, live, selectProduct]);

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (trimmed === "") return;
    const found = await resolve(trimmed);
    const exact = found.filter((hit) => hit.match === "exact" || hit.match === "identifier");
    const chosen = exact.length === 1 ? exact[0] : found.length === 1 ? found[0] : undefined;
    if (chosen) {
      selectProduct(chosen.product.id);
      setNotice(
        chosen.match === "identifier"
          ? `${trimmed} belongs to ${chosen.product.name} (${chosen.serial_status ?? "registered"}).`
          : `Selected ${chosen.product.name}.`,
      );
      const index = hits.findIndex((hit) => hit.product.id === chosen.product.id);
      if (index >= 0) setPage(Math.floor(index / pageSize) + 1);
      window.requestAnimationFrame(() =>
        document
          .querySelector(`[data-row-id="${CSS.escape(chosen.product.id)}"]`)
          ?.scrollIntoView({ block: "center", behavior: "smooth" }),
      );
      return;
    }
    if (selectedId !== null) closeDrawer();
    setNotice(found.length === 0 ? noMatchesMessage(trimmed) : `${found.length} products match "${trimmed}".`);
  };

  const trimmedQuery = debouncedQuery.trim();
  const splitHide = open ? "lg:hidden" : "";
  const splitHideCategory = open ? "lg:hidden 2xl:table-cell" : "";

  const columns: DataTableColumn<(typeof hits)[number]>[] = [
    {
      id: "photo",
      header: "Photo",
      className: "w-14",
      cell: ({ product }) => (
        <ProductImage
          url={product.thumb_url ?? product.image_url}
          className="h-10 w-10 rounded-lg object-cover"
          fallback={
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-surface text-charcoal/35" aria-hidden="true">
              <Package size={16} />
            </span>
          }
        />
      ),
    },
    {
      id: "product",
      header: "Product",
      cell: ({ product, match, serial_status: serialStatus }) => (
        <span className={`font-medium ${open && selectedId === product.id ? "text-accent" : ""}`}>
          {product.name}
          {product.is_active === false ? (
            <span className="ml-2 rounded-full bg-charcoal/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-charcoal/60">
              Inactive
            </span>
          ) : null}
          {product.is_serialized ? (
            <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase text-white">
              IMEI
            </span>
          ) : null}
          {match === "identifier" ? (
            <span className="ml-2 rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-semibold uppercase text-white">
              Serial {serialStatus ?? "match"}
            </span>
          ) : null}
        </span>
      ),
    },
    { id: "brand", header: "Brand", className: splitHide, cell: ({ product }) => product.brand ?? "—" },
    {
      id: "model",
      header: "Model",
      className: splitHide,
      cell: ({ product }) => (
        <>
          <span className="block">{product.model_name ?? "—"}</span>
          {product.model_number ? (
            <span className="block font-mono text-[11px] text-charcoal/50">{product.model_number}</span>
          ) : null}
        </>
      ),
    },
    { id: "sku", header: "SKU", cell: ({ product }) => product.sku },
    { id: "barcode", header: "Barcode", className: splitHide, cell: ({ product }) => product.barcode },
    { id: "category", header: "Category", className: splitHideCategory, cell: ({ product }) => product.category },
    { id: "sub", header: "Sub-category", className: splitHide, cell: ({ product }) => product.sub_category ?? "—" },
    {
      id: "price",
      header: "Price",
      align: "right",
      cell: ({ product }) => formatMoney(product.price_cents, product.currency),
    },
    {
      id: "stock",
      header: "Stock",
      align: "right",
      cell: ({ product }) => (
        <>
          {product.stock_quantity}
          {product.is_serialized ? <span className="ml-1 text-xs text-charcoal/50">units</span> : null}
        </>
      ),
    },
    ...(manage
      ? [
          {
            id: "edit",
            header: "Edit",
            align: "right" as const,
            className: splitHide,
            cell: ({ product }: (typeof hits)[number]) => (
              <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
                <IconButton
                  label={product.is_active === false ? `Activate ${product.name}` : `Deactivate ${product.name}`}
                  onClick={() => {
                    setRowBusy(true);
                    setNotice(null);
                    void inventoryApi
                      .updateProduct(product.id, { is_active: product.is_active === false })
                      .then(() => {
                        reload();
                        setNotice(
                          product.is_active === false
                            ? `${product.name} is active and can be sold.`
                            : `${product.name} is inactive and hidden on the register.`,
                        );
                      })
                      .catch((caught: unknown) => setNotice(message(caught, "Could not update this product.")))
                      .finally(() => setRowBusy(false));
                  }}
                >
                  <Power size={14} className={product.is_active === false ? "text-charcoal/40" : "text-accent"} />
                </IconButton>
                <IconButton
                  label={`Delete ${product.name}`}
                  onClick={() => {
                    if (rowBusy) return;
                    setDeleteError(null);
                    setPendingDelete(product);
                  }}
                >
                  <Trash2 size={14} />
                </IconButton>
                <IconButton
                  label={`Print labels for ${product.name}`}
                  onClick={() => {
                    const copies = Number(window.prompt(`How many labels for ${product.name}?`, "1"));
                    if (Number.isInteger(copies) && copies > 0) {
                      void labelsApi.products([{ product_id: product.id, copies: Math.min(copies, 500) }], "a4_3x8");
                    }
                  }}
                >
                  <Printer size={14} />
                </IconButton>
                <IconButton label={`Edit ${product.name}`} onClick={() => setEditing(product)}>
                  <Pencil size={14} />
                </IconButton>
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex items-start gap-4">
      <section
        className={`split-catalog min-w-0 grow basis-full overflow-hidden rounded-card border border-line bg-white p-4 sm:p-6 ${
          open ? "lg:basis-1/2" : ""
        }`}
      >
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold">Catalog</h2>
            <p className="text-sm text-charcoal/60">
              {failed
                ? "Products could not be loaded."
                : source === "live"
                  ? "One catalog for every branch. Stock shown is the total across your stores."
                  : "Loading products…"}
            </p>
          </div>
          {manage && source === "live" ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setImporting(true)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-charcoal/15 bg-white px-6 py-2.5 text-sm font-medium text-charcoal transition-colors hover:border-accent hover:text-accent"
              >
                <Upload size={16} aria-hidden="true" /> Import purchases
              </button>
              <PrimaryButton onClick={() => setEditing("new")}>
                <span className="inline-flex items-center gap-2">
                  <Plus size={16} aria-hidden="true" /> New product
                </span>
              </PrimaryButton>
            </div>
          ) : null}
        </div>
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <SearchField
            hideLabel
            id="inventory-search"
            label="Search Product, Model, Barcode, or IMEI"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setNotice(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void submit(event.currentTarget.value);
              } else if (event.key === "Escape") {
                setQuery("");
              }
            }}
            placeholder="Search Product, Model, Barcode, or IMEI..."
            className="min-w-[min(100%,18rem)] grow-[2] basis-[22rem]"
          />
          {source === "live" ? (
            <BrandModelFilters
              className="min-w-[9rem] grow basis-40"
              subCategoryId={null}
              brandId={brandId}
              modelId={modelId}
              onChange={(brand, model) => {
                setBrandId(brand);
                setModelId(model);
              }}
            />
          ) : null}
        </div>
        {notice ? (
          <p className="mb-4 text-sm" role="status">
            {notice}
          </p>
        ) : null}
        <DataTable
          aria-label="Product catalog"
          variant="flush"
          className="-mx-4 -mb-4 border-t border-line sm:-mx-6 sm:-mb-6"
          minWidth={open ? undefined : "860px"}
          columns={columns}
          data={hits}
          getRowId={(hit) => hit.product.id}
          isLoading={searching && hits.length === 0}
          onRowClick={(hit) => toggleRow(hit.product.id)}
          isRowActive={(hit) => open && selectedId === hit.product.id}
          emptyState={{
            icon: Search,
            title: trimmedQuery !== "" ? noMatchesMessage(trimmedQuery) : "No products in the catalog yet",
          }}
          pagination={{
            mode: "client",
            currentPage: page,
            pageSize,
            onPageChange: setPage,
            onPageSizeChange: setPageSize,
            resetKey: [debouncedQuery, brandId, modelId],
          }}
        />
        {editing !== null ? (
          <ProductFormModal
            product={editing === "new" ? null : editing}
            onClose={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              reload();
              setRefreshKey((value) => value + 1);
            }}
          />
        ) : null}
        {pendingDelete ? (
          <Modal
            title={`Delete ${pendingDelete.name}?`}
            subtitle="Products with sales or stock stay in the catalog. Deactivate those so the register stops selling them."
            onClose={() => {
              if (!rowBusy) setPendingDelete(null);
            }}
            footer={
              <>
                <GhostButton disabled={rowBusy} onClick={() => setPendingDelete(null)}>
                  Cancel
                </GhostButton>
                <PrimaryButton
                  disabled={rowBusy}
                  onClick={() => {
                    const product = pendingDelete;
                    setRowBusy(true);
                    setNotice(null);
                    void inventoryApi
                      .deleteProduct(product.id)
                      .then(() => {
                        if (selectedId === product.id) closeDrawer();
                        setPendingDelete(null);
                        reload();
                        setNotice(`${product.name} was deleted.`);
                      })
                      .catch((caught: unknown) => setDeleteError(message(caught, "Could not delete this product.")))
                      .finally(() => setRowBusy(false));
                  }}
                >
                  {rowBusy ? "Deleting…" : "Delete product"}
                </PrimaryButton>
              </>
            }
          >
            <p className="text-sm text-charcoal/70">{pendingDelete.sku} will be removed. This cannot be undone.</p>
            {deleteError ? <p className="mt-3 text-sm font-medium text-danger">{deleteError}</p> : null}
          </Modal>
        ) : null}
        {importing ? (
          <ImportWizardModal
            onClose={() => setImporting(false)}
            onCommitted={(batch) => {
              reload();
              setRefreshKey((value) => value + 1);
              setNotice(`${batch.batch_number} committed: ${batch.total_items_count} units at ${batch.store_code}.`);
            }}
            onViewBatch={(batch) => navigate(`/inventory/batches?batch=${batch.id}`)}
          />
        ) : null}
      </section>
      {selected !== null && source === "live" ? (
        <ProductDetailDrawer
          key={selected.id}
          product={selected}
          closing={closing}
          escapeEnabled={editing === null}
          refreshKey={refreshKey}
          onClose={closeDrawer}
          onEdit={manage ? setEditing : null}
        />
      ) : null}
    </div>
  );
}
