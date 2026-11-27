import {
  Capability,
  Permission,
  formatMoney,
  type Product,
  type PurchaseOrder,
  type PurchaseOrderStatus,
} from "@ai-pos/shared-types";
import { AxizDatePicker } from "@ai-pos/ui";
import { PackagePlus, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DataTable, usePagination, type DataTableColumn, type TableFilter } from "../../components/ui/DataTable";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { inventoryApi, message } from "./api";
import { GridQuantityEditor } from "./GridQuantityEditor";
import { DocStatus, formatDate, statusLabel, storeOptions, useStoreScope, useStores } from "./shared";
import { IconButton } from "./StockPage";

const statuses: (PurchaseOrderStatus | "all")[] = ["all", "draft", "ordered", "partially_received", "received", "cancelled"];
const statusOptions = statuses.map((value) => ({ value, label: value === "all" ? "All statuses" : statusLabel(value) }));

function purchaseOrderFilters(
  stores: Parameters<typeof storeOptions>[0],
  pinned: boolean,
  storeId: string | null,
  setStoreId: (value: string | null) => void,
  status: string,
  setStatus: (value: PurchaseOrderStatus | "all") => void,
): TableFilter[] {
  return [
    {
      id: "store",
      label: "Receiving store",
      value: storeId ?? "",
      clearedValue: pinned ? (storeId ?? "") : "",
      disabled: pinned,
      onChange: (value) => setStoreId(value || null),
      options: [...(pinned ? [] : [{ value: "", label: "All Stores (Consolidated)" }]), ...storeOptions(stores)],
    },
    {
      id: "status",
      label: "Status",
      value: status,
      clearedValue: "all",
      onChange: (value) => setStatus(value as PurchaseOrderStatus | "all"),
      options: statusOptions,
    },
  ];
}

export function PurchaseOrdersPage() {
  const { can } = useAuth();
  const { stores } = useStores();
  const { storeId, setStoreId, pinned } = useStoreScope();
  const [status, setStatus] = useState<PurchaseOrderStatus | "all">("all");
  const pager = usePagination({ resetKeys: [status, storeId] });
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [params, setParams] = useSearchParams();
  const presetProduct = params.get("product");
  const [openId, setOpenId] = useState<string | null>(null);
  const manage = can(Permission.PortalInventoryManage);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await inventoryApi.purchaseOrders(
        { status: status === "all" ? null : status, store_id: storeId },
        { offset: pager.offset, limit: pager.pageSize },
      );
      setOrders(page.rows);
      setTotal(page.total);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load purchase orders."));
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [status, storeId, pager.offset, pager.pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  const open = orders.find((order) => order.id === openId) ?? null;
  const replace = (next: PurchaseOrder) =>
    setOrders((current) => current.map((order) => (order.id === next.id ? next : order)));

  const columns: DataTableColumn<PurchaseOrder>[] = [
    { id: "number", header: "PO", className: "whitespace-nowrap font-mono text-xs", cell: (order) => order.number },
    { id: "supplier", header: "Supplier", className: "font-medium", cell: (order) => order.supplier_name },
    { id: "destination", header: "Destination", cell: (order) => order.destination_store_code },
    { id: "status", header: "Status", cell: (order) => <DocStatus status={order.status} /> },
    {
      id: "received",
      header: "Received",
      align: "right",
      cell: (order) => {
        const ordered = order.lines.reduce((sum, line) => sum + line.quantity_ordered, 0);
        const received = order.lines.reduce((sum, line) => sum + line.quantity_received, 0);
        return `${received} / ${ordered}`;
      },
    },
    { id: "cost", header: "Cost", align: "right", cell: (order) => <PoCost cents={order.total_cost_cents} /> },
    {
      id: "created",
      header: "Created",
      className: "whitespace-nowrap text-xs text-charcoal/60",
      cell: (order) => formatDate(order.created_at),
    },
  ];

  return (
    <section className="overflow-hidden rounded-card border border-line bg-white">
      {error ? (
        <div className="px-6 pt-5">
          <ErrorNote message={error} />
        </div>
      ) : null}
      <DataTable
        aria-label="Purchase orders"
        variant="flush"
        minWidth="860px"
        columns={columns}
        data={orders}
        getRowId={(order) => order.id}
        toolbar={{
          filters: purchaseOrderFilters(stores, pinned, storeId, setStoreId, status, setStatus),
          actions: manage ? (
            <PrimaryButton onClick={() => setCreating(true)}>
              <span className="inline-flex items-center gap-2">
                <Plus size={16} aria-hidden="true" /> New purchase order
              </span>
            </PrimaryButton>
          ) : null,
        }}
        isLoading={loading && !loaded}
        isFetching={loading && loaded}
        onRowClick={(order) => setOpenId(order.id)}
        isRowActive={(order) => order.id === openId}
        emptyState={{
          icon: PackagePlus,
          title: status === "all" ? "No purchase orders yet" : `No ${statusLabel(status).toLowerCase()} purchase orders`,
        }}
        pagination={{
          mode: "server",
          currentPage: pager.page,
          pageSize: pager.pageSize,
          totalRecords: total,
          onPageChange: pager.setPage,
          onPageSizeChange: pager.setPageSize,
        }}
      />

      {creating || presetProduct ? (
        <CreatePurchaseOrder
          stores={stores}
          pinnedStore={pinned ? storeId : null}
          presetProduct={presetProduct}
          presetQuantity={params.get("quantity")}
          presetStore={params.get("store")}
          onClose={() => {
            setCreating(false);
            setParams({});
          }}
          onCreated={(order) => {
            setCreating(false);
            setParams({});
            if (pager.page === 1) void load();
            else pager.setPage(1);
            setOrders((current) => [order, ...current.filter((row) => row.id !== order.id)]);
            setOpenId(order.id);
          }}
        />
      ) : null}
      {open ? <PurchaseOrderDetail order={open} manage={manage} onClose={() => setOpenId(null)} onChanged={replace} /> : null}
    </section>
  );
}

function PoCost({ cents }: { cents: number }) {
  const { currency } = useCurrency();
  return <>{formatMoney(cents, currency)}</>;
}

interface DraftLine {
  key: string;
  productId: string;
  quantity: string;
  cost: string;
}

function CreatePurchaseOrder({
  stores,
  pinnedStore,
  presetProduct,
  presetQuantity,
  presetStore,
  onClose,
  onCreated,
}: {
  stores: { id: string; code: string; name: string; is_warehouse?: boolean }[];
  pinnedStore: string | null;
  presetProduct: string | null;
  presetQuantity: string | null;
  presetStore: string | null;
  onClose: () => void;
  onCreated: (order: PurchaseOrder) => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [supplier, setSupplier] = useState("");
  const [destination, setDestination] = useState(
    presetStore ?? pinnedStore ?? stores.find((store) => store.is_warehouse)?.id ?? "",
  );
  const [expected, setExpected] = useState("");
  const [notes, setNotes] = useState("");
  const presetQty = presetQuantity !== null && Number(presetQuantity) >= 1 ? String(Math.floor(Number(presetQuantity))) : "1";
  const [lines, setLines] = useState<DraftLine[]>([
    { key: crypto.randomUUID(), productId: presetProduct ?? "", quantity: presetQty, cost: "" },
  ]);
  const [find, setFind] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    inventoryApi.products({}).then(setProducts).catch(() => setProducts([]));
  }, []);

  const update = (key: string, patch: Partial<DraftLine>) =>
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));

  const save = async () => {
    if (supplier.trim().length < 2) return setError("Enter the supplier name.");
    if (destination === "") return setError("Choose the receiving store or warehouse.");
    const parsed = lines.map((line) => ({
      product_id: line.productId,
      quantity_ordered: Number(line.quantity),
      unit_cost_cents: line.cost.trim() === "" ? 0 : Math.round(Number(line.cost) * 100),
    }));
    if (parsed.some((line) => line.product_id === "" || !Number.isInteger(line.quantity_ordered) || line.quantity_ordered < 1)) {
      return setError("Every line needs a product and a whole quantity of at least 1.");
    }
    if (parsed.some((line) => Number.isNaN(line.unit_cost_cents) || line.unit_cost_cents < 0)) {
      return setError("Unit costs must be amounts like 6.50.");
    }
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await inventoryApi.createPurchaseOrder({
          supplier_name: supplier.trim(),
          destination_store_id: destination,
          expected_at: expected ? new Date(expected).toISOString() : null,
          notes: notes.trim(),
          lines: parsed,
        }),
      );
    } catch (caught) {
      setError(message(caught, "Could not create the purchase order."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New purchase order"
      subtitle="Goods are received into the destination store or warehouse."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save as draft"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField label="Supplier" value={supplier} onChange={(event) => setSupplier(event.target.value)} />
        <SelectField
          label="Destination store"
          value={destination}
          disabled={pinnedStore !== null}
          placeholder="Choose a store"
          options={storeOptions(stores)}
          onChange={setDestination}
        />
        <TextField label="Expected delivery" type="date" value={expected} onChange={(event) => setExpected(event.target.value)} />
        <TextField label="Notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
      </div>
      <h3 className="mt-6 text-sm font-semibold">Lines</h3>
      <TextField
        label="Find a product"
        value={find}
        placeholder="Name, SKU or barcode"
        onChange={(event) => {
          const value = event.target.value;
          setFind(value);
          if (value.trim().length >= 2) {
            inventoryApi.products({ q: value.trim() }).then(setProducts).catch(() => undefined);
          }
        }}
      />
      <div className="mt-2 space-y-2">
        {lines.map((line) => (
          <div key={line.key} className="grid grid-cols-[1fr_100px_120px_40px] items-end gap-2">
            <SelectField
              label="Product"
              value={line.productId}
              placeholder="Choose a product"
              options={products.map((product) => ({
                value: product.id,
                label: product.name,
                hint: `${product.sku}${product.is_serialized ? " · IMEI tracked" : ""}`,
              }))}
              onChange={(productId) => update(line.key, { productId })}
            />
            <TextField label="Qty" type="number" min={1} value={line.quantity} onChange={(event) => update(line.key, { quantity: event.target.value })} />
            <TextField label="Unit cost" inputMode="decimal" value={line.cost} onChange={(event) => update(line.key, { cost: event.target.value })} />
            <IconButton
              label="Remove line"
              onClick={() => setLines((current) => (current.length > 1 ? current.filter((item) => item.key !== line.key) : current))}
            >
              <Trash2 size={14} />
            </IconButton>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setLines((current) => [...current, { key: crypto.randomUUID(), productId: "", quantity: "1", cost: "" }])}
        className="mt-3 text-sm font-semibold text-accent"
      >
        + Add line
      </button>
      <GridQuantityEditor
        onApply={(rows) =>
          setLines((current) => [
            ...current.filter((line) => line.productId !== ""),
            ...rows.map((row) => ({ key: crypto.randomUUID(), productId: row.productId, quantity: String(row.quantity), cost: "" })),
          ])
        }
      />
      <ErrorNote message={error} />
    </Modal>
  );
}

function parseSerials(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

type LotSlice = { key: string; quantity: string; lot: string; manufactured: string; expiry: string };

function PurchaseOrderDetail({
  order,
  manage,
  onClose,
  onChanged,
}: {
  order: PurchaseOrder;
  manage: boolean;
  onClose: () => void;
  onChanged: (order: PurchaseOrder) => void;
}) {
  const pharmacyLots = useCapability(Capability.PharmacyCatalog);
  const [receiving, setReceiving] = useState(false);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [serials, setSerials] = useState<Record<string, string>>({});
  const [locations, setLocations] = useState<Record<string, string>>({});
  const [slices, setSlices] = useState<Record<string, LotSlice[]>>({});
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<PurchaseOrder>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
      setReceiving(false);
    } catch (caught) {
      setError(message(caught, "The purchase order could not be updated."));
    } finally {
      setBusy(false);
    }
  };

  const beginReceiving = () => {
    const next: Record<string, LotSlice[]> = {};
    for (const line of order.lines) {
      const outstanding = line.quantity_ordered - line.quantity_received;
      if (pharmacyLots && line.lot_controlled && outstanding > 0) {
        next[line.id] = [
          { key: crypto.randomUUID(), quantity: String(outstanding), lot: "", manufactured: "", expiry: "" },
        ];
      }
    }
    setSlices(next);
    setReceiving(true);
  };

  const receive = () => {
    const lines: {
      purchase_order_line_id: string;
      quantity: number;
      serials: { kind: "imei" | "serial"; value: string }[];
      aisle_shelf_location: string | null;
      manufacturer_lot?: string | null;
      manufactured_on?: string | null;
      expiry_date?: string | null;
    }[] = [];
    for (const line of order.lines) {
      const outstanding = line.quantity_ordered - line.quantity_received;
      if (outstanding <= 0) continue;
      if (pharmacyLots && line.lot_controlled) {
        const parts = slices[line.id] ?? [];
        let total = 0;
        for (const slice of parts) {
          const quantity = Number(slice.quantity);
          if (!Number.isInteger(quantity) || quantity <= 0) continue;
          if (slice.lot.trim() === "" || slice.expiry === "") {
            setError(`Enter the manufacturer lot and expiry for ${line.name}.`);
            return;
          }
          if (slice.manufactured !== "" && slice.manufactured > slice.expiry) {
            setError(`Manufacture date for ${line.name} is after the expiry date.`);
            return;
          }
          total += quantity;
          lines.push({
            purchase_order_line_id: line.id,
            quantity,
            serials: [],
            aisle_shelf_location: locations[line.id]?.trim() || null,
            manufacturer_lot: slice.lot.trim(),
            manufactured_on: slice.manufactured || null,
            expiry_date: slice.expiry,
          });
        }
        if (total > outstanding) {
          setError(`${line.name} has only ${outstanding} left to receive.`);
          return;
        }
        continue;
      }
      const values = line.is_serialized ? parseSerials(serials[line.id] ?? "") : [];
      const quantity = line.is_serialized ? values.length : Number(quantities[line.id] ?? outstanding);
      if (quantity > 0) {
        lines.push({
          purchase_order_line_id: line.id,
          quantity,
          serials: values.map((value) => ({ kind: /^\d{15}$/.test(value) ? ("imei" as const) : ("serial" as const), value })),
          aisle_shelf_location: locations[line.id]?.trim() || null,
        });
      }
    }
    if (lines.length === 0) return setError("Enter at least one quantity or IMEI to receive.");
    void act(() => inventoryApi.receivePurchaseOrder(order.id, { note: note.trim(), lines }));
  };

  const canReceive = manage && (order.status === "ordered" || order.status === "partially_received");
  return (
    <Modal
      title={`${order.number} · ${order.supplier_name}`}
      subtitle={`Receiving at ${order.destination_store_code} · ${order.destination_store_name}`}
      onClose={onClose}
      width="lg"
      footer={
        manage ? (
          <>
            {order.status === "draft" || (order.status === "ordered" && order.lines.every((line) => line.quantity_received === 0)) ? (
              <GhostButton disabled={busy} onClick={() => void act(() => inventoryApi.cancelPurchaseOrder(order.id))}>
                Cancel order
              </GhostButton>
            ) : null}
            {order.status === "draft" ? (
              <PrimaryButton disabled={busy} onClick={() => void act(() => inventoryApi.placePurchaseOrder(order.id))}>
                Place order
              </PrimaryButton>
            ) : null}
            {canReceive && !receiving ? (
              <PrimaryButton onClick={beginReceiving}>
                <span className="inline-flex items-center gap-2">
                  <PackagePlus size={16} aria-hidden="true" /> Receive goods (GRN)
                </span>
              </PrimaryButton>
            ) : null}
            {receiving ? (
              <PrimaryButton disabled={busy} onClick={receive}>
                {busy ? "Receiving…" : "Post goods receipt"}
              </PrimaryButton>
            ) : null}
          </>
        ) : undefined
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <DocStatus status={order.status} />
        <span className="text-charcoal/60">Created {formatDate(order.created_at)}</span>
        {order.ordered_at ? <span className="text-charcoal/60">Ordered {formatDate(order.ordered_at)}</span> : null}
        {order.received_at ? <span className="text-charcoal/60">Completed {formatDate(order.received_at)}</span> : null}
      </div>
      <ul className="divide-y divide-line rounded-2xl border border-line">
        {order.lines.map((line) => {
          const outstanding = line.quantity_ordered - line.quantity_received;
          return (
            <li key={line.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <span>
                  <span className="block font-medium">{line.name}</span>
                  <span className="block font-mono text-xs text-charcoal/50">
                    {line.sku}
                    {line.is_serialized ? " · IMEI tracked" : ""}
                  </span>
                </span>
                <span className="text-right text-sm tabular-nums">
                  <span className="block font-semibold">
                    {line.quantity_received} / {line.quantity_ordered}
                  </span>
                  <span className="block text-xs text-charcoal/50">received</span>
                </span>
              </div>
              {receiving && outstanding > 0 && pharmacyLots && line.lot_controlled ? (
                <div className="mt-3 space-y-3">
                  {(slices[line.id] ?? []).map((slice) => (
                    <div key={slice.key} className="grid gap-3 md:grid-cols-4">
                      <TextField
                        label={`Quantity (${outstanding} outstanding)`}
                        type="number"
                        min={0}
                        value={slice.quantity}
                        onChange={(event) =>
                          setSlices((current) => ({
                            ...current,
                            [line.id]: (current[line.id] ?? []).map((item) =>
                              item.key === slice.key ? { ...item, quantity: event.target.value } : item,
                            ),
                          }))
                        }
                      />
                      <TextField
                        label="Manufacturer lot"
                        value={slice.lot}
                        onChange={(event) =>
                          setSlices((current) => ({
                            ...current,
                            [line.id]: (current[line.id] ?? []).map((item) =>
                              item.key === slice.key ? { ...item, lot: event.target.value } : item,
                            ),
                          }))
                        }
                      />
                      <label className="block text-sm font-medium">
                        Manufacture date
                        <AxizDatePicker
                          leading
                          aria-label={`Manufacture date for ${line.name}`}
                          value={slice.manufactured}
                          onChange={(event) =>
                            setSlices((current) => ({
                              ...current,
                              [line.id]: (current[line.id] ?? []).map((item) =>
                                item.key === slice.key ? { ...item, manufactured: event.target.value } : item,
                              ),
                            }))
                          }
                          className="mt-1 h-11 w-full rounded-2xl border border-line bg-surface px-3 text-sm"
                        />
                      </label>
                      <label className="block text-sm font-medium">
                        Expiry date
                        <AxizDatePicker
                          leading
                          aria-label={`Expiry date for ${line.name}`}
                          value={slice.expiry}
                          onChange={(event) =>
                            setSlices((current) => ({
                              ...current,
                              [line.id]: (current[line.id] ?? []).map((item) =>
                                item.key === slice.key ? { ...item, expiry: event.target.value } : item,
                              ),
                            }))
                          }
                          className="mt-1 h-11 w-full rounded-2xl border border-line bg-surface px-3 text-sm"
                        />
                      </label>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="text-sm font-semibold text-accent"
                    onClick={() =>
                      setSlices((current) => ({
                        ...current,
                        [line.id]: [
                          ...(current[line.id] ?? []),
                          { key: crypto.randomUUID(), quantity: "", lot: "", manufactured: "", expiry: "" },
                        ],
                      }))
                    }
                  >
                    + Add another manufacturer lot
                  </button>
                </div>
              ) : null}
              {receiving && outstanding > 0 && !(pharmacyLots && line.lot_controlled) ? (
                <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px]">
                  {line.is_serialized ? (
                    <label className="block text-sm font-medium">
                      IMEI / serial numbers ({outstanding} outstanding)
                      <textarea
                        value={serials[line.id] ?? ""}
                        onChange={(event) => setSerials({ ...serials, [line.id]: event.target.value })}
                        rows={3}
                        placeholder="Scan one per line"
                        className="mt-1 w-full rounded-2xl border border-line bg-surface p-3 font-mono text-sm"
                      />
                    </label>
                  ) : (
                    <TextField
                      label={`Quantity (${outstanding} outstanding)`}
                      type="number"
                      min={0}
                      max={outstanding}
                      value={quantities[line.id] ?? String(outstanding)}
                      onChange={(event) => setQuantities({ ...quantities, [line.id]: event.target.value })}
                    />
                  )}
                  <TextField
                    label="Shelf location"
                    value={locations[line.id] ?? ""}
                    placeholder="Optional"
                    onChange={(event) => setLocations({ ...locations, [line.id]: event.target.value })}
                  />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {receiving ? (
        <div className="mt-4">
          <TextField label="Receipt note" value={note} onChange={(event) => setNote(event.target.value)} />
        </div>
      ) : null}
      {order.receipts.length > 0 ? (
        <>
          <h3 className="mt-6 text-sm font-semibold">Goods receipts</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {order.receipts.map((receipt) => (
              <li key={receipt.id} className="flex justify-between rounded-2xl bg-surface px-4 py-3">
                <span>
                  <span className="font-mono text-xs">{receipt.number}</span>
                  <span className="ml-2 text-charcoal/60">
                    {formatDate(receipt.created_at)}
                    {receipt.received_by_name ? ` · ${receipt.received_by_name}` : ""}
                  </span>
                  {(receipt.lots ?? [])
                    .filter((lot) => lot.manufacturer_lot)
                    .map((lot) => (
                      <span key={lot.batch_item_id} className="mt-1 block text-xs text-charcoal/70">
                        Receipt {receipt.number} · Manufacturer lot {lot.manufacturer_lot}
                        {lot.expiry_date ? ` · expires ${lot.expiry_date}` : ""}
                        {lot.lot_status ? ` · ${lot.lot_status.replace(/_/g, " ").toLowerCase()}` : ""}
                      </span>
                    ))}
                </span>
                <span className="tabular-nums">{receipt.lines.reduce((sum, line) => sum + line.quantity, 0)} units</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
