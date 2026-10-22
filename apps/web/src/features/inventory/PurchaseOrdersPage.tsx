import {
  Permission,
  formatMoney,
  type Product,
  type PurchaseOrder,
  type PurchaseOrderStatus,
} from "@ai-pos/shared-types";
import { PackagePlus, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { inventoryApi, message } from "./api";
import { GridQuantityEditor } from "./GridQuantityEditor";
import { DocStatus, StoreSelect, formatDate, statusLabel, storeOptions, useStoreScope, useStores } from "./shared";
import { IconButton } from "./StockPage";

const statuses: (PurchaseOrderStatus | "all")[] = ["all", "draft", "ordered", "partially_received", "received", "cancelled"];
const statusOptions = statuses.map((value) => ({ value, label: value === "all" ? "All statuses" : statusLabel(value) }));

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
      <div className="flex flex-wrap items-end justify-between gap-3 p-6 pb-5">
        <div className="flex flex-wrap items-end gap-3">
          <StoreSelect
            stores={stores}
            value={storeId}
            onChange={setStoreId}
            disabled={pinned}
            allowAll={!pinned}
            label="Receiving store"
          />
          <FilterSelect label="Status" className="min-w-[200px]" value={status} options={statusOptions} onChange={setStatus} />
        </div>
        {manage ? (
          <PrimaryButton onClick={() => setCreating(true)}>
            <span className="inline-flex items-center gap-2">
              <Plus size={16} aria-hidden="true" /> New purchase order
            </span>
          </PrimaryButton>
        ) : null}
        {error ? (
          <div className="w-full">
            <ErrorNote message={error} />
          </div>
        ) : null}
      </div>
      <DataTable
        aria-label="Purchase orders"
        variant="flush"
        minWidth="860px"
        columns={columns}
        data={orders}
        getRowId={(order) => order.id}
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

      {creating ? (
        <CreatePurchaseOrder
          stores={stores}
          pinnedStore={pinned ? storeId : null}
          onClose={() => setCreating(false)}
          onCreated={(order) => {
            setCreating(false);
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
  onClose,
  onCreated,
}: {
  stores: { id: string; code: string; name: string; is_warehouse?: boolean }[];
  pinnedStore: string | null;
  onClose: () => void;
  onCreated: (order: PurchaseOrder) => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [supplier, setSupplier] = useState("");
  const [destination, setDestination] = useState(pinnedStore ?? stores.find((store) => store.is_warehouse)?.id ?? "");
  const [expected, setExpected] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ key: crypto.randomUUID(), productId: "", quantity: "1", cost: "" }]);
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
  const [receiving, setReceiving] = useState(false);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [serials, setSerials] = useState<Record<string, string>>({});
  const [locations, setLocations] = useState<Record<string, string>>({});
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

  const receive = () => {
    const lines = order.lines
      .map((line) => {
        const outstanding = line.quantity_ordered - line.quantity_received;
        const values = line.is_serialized ? parseSerials(serials[line.id] ?? "") : [];
        const quantity = line.is_serialized ? values.length : Number(quantities[line.id] ?? outstanding);
        return {
          purchase_order_line_id: line.id,
          quantity,
          serials: values.map((value) => ({ kind: /^\d{15}$/.test(value) ? ("imei" as const) : ("serial" as const), value })),
          aisle_shelf_location: locations[line.id]?.trim() || null,
        };
      })
      .filter((line) => line.quantity > 0);
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
              <PrimaryButton onClick={() => setReceiving(true)}>
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
              {receiving && outstanding > 0 ? (
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
