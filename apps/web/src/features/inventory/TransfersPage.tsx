import { Permission, type Product, type StockTransfer, type Store, type TransferStatus } from "@ai-pos/shared-types";
import { ArrowRight, Plus, Trash2, Truck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { inventoryApi, message } from "./api";
import { GridQuantityEditor } from "./GridQuantityEditor";
import { DocStatus, StoreSelect, formatDate, statusLabel, useStoreScope, useStores } from "./shared";
import { IconButton } from "./StockPage";

const statuses: (TransferStatus | "all")[] = ["all", "requested", "in_transit", "received", "cancelled"];
const statusOptions = statuses.map((value) => ({ value, label: value === "all" ? "All statuses" : statusLabel(value) }));

export function TransfersPage() {
  const { can } = useAuth();
  const { stores } = useStores();
  const { storeId, setStoreId, pinned } = useStoreScope();
  const [status, setStatus] = useState<TransferStatus | "all">("all");
  const pager = usePagination({ resetKeys: [status, storeId] });
  const [transfers, setTransfers] = useState<StockTransfer[]>([]);
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
      const page = await inventoryApi.transfers(
        { status: status === "all" ? null : status, store_id: storeId },
        { offset: pager.offset, limit: pager.pageSize },
      );
      setTransfers(page.rows);
      setTotal(page.total);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load transfers."));
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [status, storeId, pager.offset, pager.pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (next: StockTransfer) =>
    setTransfers((current) => current.map((item) => (item.id === next.id ? next : item)));
  const open = transfers.find((item) => item.id === openId) ?? null;

  const columns: DataTableColumn<StockTransfer>[] = [
    {
      id: "number",
      header: "Transfer",
      className: "whitespace-nowrap font-mono text-xs",
      cell: (transfer) => transfer.number,
    },
    {
      id: "route",
      header: "Route",
      cell: (transfer) => (
        <span className="inline-flex items-center gap-2 whitespace-nowrap font-medium">
          {transfer.source_store_code} <ArrowRight size={14} className="text-accent" aria-label="to" />{" "}
          {transfer.destination_store_code}
        </span>
      ),
    },
    { id: "status", header: "Status", cell: (transfer) => <DocStatus status={transfer.status} /> },
    {
      id: "units",
      header: "Units",
      align: "right",
      cell: (transfer) => transfer.lines.reduce((sum, line) => sum + line.quantity, 0),
    },
    ...(
      [
        ["requested", "Requested", "created_at"],
        ["shipped", "Shipped", "shipped_at"],
        ["received", "Received", "received_at"],
      ] as const
    ).map(
      ([id, header, key]): DataTableColumn<StockTransfer> => ({
        id,
        header,
        className: "whitespace-nowrap text-xs text-charcoal/60",
        cell: (transfer) => formatDate(transfer[key]),
      }),
    ),
  ];

  return (
    <section className="overflow-hidden rounded-card border border-line bg-white">
      <div className="flex flex-wrap items-end justify-between gap-3 p-6 pb-5">
        <div className="flex flex-wrap items-end gap-3">
          <StoreSelect stores={stores} value={storeId} onChange={setStoreId} disabled={pinned} allowAll={!pinned} label="Branch" />
          <FilterSelect label="Status" className="min-w-[200px]" value={status} options={statusOptions} onChange={setStatus} />
        </div>
        {manage ? (
          <PrimaryButton onClick={() => setCreating(true)}>
            <span className="inline-flex items-center gap-2">
              <Plus size={16} aria-hidden="true" /> New transfer
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
        aria-label="Stock transfers"
        variant="flush"
        minWidth="860px"
        columns={columns}
        data={transfers}
        getRowId={(transfer) => transfer.id}
        isLoading={loading && !loaded}
        isFetching={loading && loaded}
        onRowClick={(transfer) => setOpenId(transfer.id)}
        isRowActive={(transfer) => transfer.id === openId}
        emptyState={{
          icon: Truck,
          title: status === "all" ? "No transfers yet" : `No ${statusLabel(status).toLowerCase()} transfers`,
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
        <CreateTransfer
          stores={stores}
          pinnedStore={pinned ? storeId : null}
          onClose={() => setCreating(false)}
          onCreated={(transfer) => {
            setCreating(false);
            setTransfers((current) => [transfer, ...current.filter((item) => item.id !== transfer.id)]);
            if (pager.page === 1) void load();
            else pager.setPage(1);
            setOpenId(transfer.id);
          }}
        />
      ) : null}
      {open ? <TransferDetail transfer={open} manage={manage} onClose={() => setOpenId(null)} onChanged={replace} /> : null}
    </section>
  );
}

interface DraftLine {
  key: string;
  productId: string;
  quantity: string;
}

function CreateTransfer({
  stores,
  pinnedStore,
  onClose,
  onCreated,
}: {
  stores: Store[];
  pinnedStore: string | null;
  onClose: () => void;
  onCreated: (transfer: StockTransfer) => void;
}) {
  const warehouse = stores.find((store) => store.is_warehouse);
  const [source, setSource] = useState(warehouse?.id ?? "");
  const [destination, setDestination] = useState(pinnedStore ?? "");
  const [note, setNote] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [lines, setLines] = useState<DraftLine[]>([{ key: crypto.randomUUID(), productId: "", quantity: "1" }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (source === "") {
      setProducts([]);
      return;
    }
    inventoryApi
      .products({ store_id: source })
      .then(setProducts)
      .catch(() => setProducts([]));
  }, [source]);

  const update = (key: string, patch: Partial<DraftLine>) =>
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));

  const save = async () => {
    if (source === "" || destination === "") return setError("Choose both the source and destination stores.");
    if (source === destination) return setError("Source and destination must be different.");
    const parsed = lines.map((line) => ({ product_id: line.productId, quantity: Number(line.quantity) }));
    if (parsed.some((line) => line.product_id === "" || !Number.isInteger(line.quantity) || line.quantity < 1)) {
      return setError("Every line needs a product and a whole quantity of at least 1.");
    }
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await inventoryApi.createTransfer({
          source_store_id: source,
          destination_store_id: destination,
          note: note.trim(),
          lines: parsed,
        }),
      );
    } catch (caught) {
      setError(message(caught, "Could not request the transfer."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New stock transfer"
      subtitle="Stock is reserved at the source now, leaves when shipped, and arrives when received."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Requesting…" : "Request transfer"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <StoreSelect stores={stores} value={source || null} onChange={(value) => setSource(value ?? "")} allowAll={false} label="From (source)" />
        <StoreSelect
          stores={stores}
          value={destination || null}
          onChange={(value) => setDestination(value ?? "")}
          allowAll={false}
          label="To (destination)"
        />
      </div>
      <h3 className="mt-6 text-sm font-semibold">Lines</h3>
      <div className="mt-2 space-y-2">
        {lines.map((line) => {
          const product = products.find((item) => item.id === line.productId);
          const available = product ? product.stock_quantity - (product.quantity_reserved ?? 0) : null;
          return (
            <div key={line.key} className="grid grid-cols-[1fr_110px_40px] items-end gap-2">
              <SelectField
                label="Product"
                value={line.productId}
                placeholder={source === "" ? "Choose the source store first" : "Choose a product"}
                disabled={source === ""}
                options={products.map((item) => ({
                  value: item.id,
                  label: item.name,
                  hint: `${item.sku} · ${item.stock_quantity - (item.quantity_reserved ?? 0)} available`,
                }))}
                onChange={(productId) => update(line.key, { productId })}
              />
              <TextField
                label={available === null ? "Qty" : `Qty (max ${available})`}
                type="number"
                min={1}
                value={line.quantity}
                onChange={(event) => update(line.key, { quantity: event.target.value })}
              />
              <IconButton
                label="Remove line"
                onClick={() => setLines((current) => (current.length > 1 ? current.filter((item) => item.key !== line.key) : current))}
              >
                <Trash2 size={14} />
              </IconButton>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => setLines((current) => [...current, { key: crypto.randomUUID(), productId: "", quantity: "1" }])}
        className="mt-3 text-sm font-semibold text-accent"
      >
        + Add line
      </button>
      <GridQuantityEditor
        onApply={(rows) =>
          setLines((current) => [
            ...current.filter((line) => line.productId !== ""),
            ...rows.map((row) => ({ key: crypto.randomUUID(), productId: row.productId, quantity: String(row.quantity) })),
          ])
        }
      />
      <div className="mt-4">
        <TextField label="Note" value={note} onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function TransferDetail({
  transfer,
  manage,
  onClose,
  onChanged,
}: {
  transfer: StockTransfer;
  manage: boolean;
  onClose: () => void;
  onChanged: (transfer: StockTransfer) => void;
}) {
  const [serials, setSerials] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<StockTransfer>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
    } catch (caught) {
      setError(message(caught, "The transfer could not be updated."));
    } finally {
      setBusy(false);
    }
  };

  const ship = () => {
    const serialLines = transfer.lines
      .filter((line) => line.is_serialized)
      .map((line) => ({
        transfer_line_id: line.id,
        serials: (serials[line.id] ?? "")
          .split(/[\s,;]+/)
          .map((value) => value.trim())
          .filter(Boolean)
          .map((value) => ({ kind: /^\d{15}$/.test(value) ? ("imei" as const) : ("serial" as const), value })),
      }));
    void act(() => inventoryApi.shipTransfer(transfer.id, { serial_lines: serialLines }));
  };

  return (
    <Modal
      title={`${transfer.number} · ${transfer.source_store_code} → ${transfer.destination_store_code}`}
      subtitle={`${transfer.source_store_name} to ${transfer.destination_store_name}`}
      onClose={onClose}
      width="lg"
      footer={
        manage ? (
          <>
            {transfer.status === "requested" ? (
              <GhostButton disabled={busy} onClick={() => void act(() => inventoryApi.cancelTransfer(transfer.id))}>
                Cancel transfer
              </GhostButton>
            ) : null}
            {transfer.status === "requested" ? (
              <PrimaryButton disabled={busy} onClick={ship}>
                <span className="inline-flex items-center gap-2">
                  <Truck size={16} aria-hidden="true" /> {busy ? "Shipping…" : "Ship from source"}
                </span>
              </PrimaryButton>
            ) : null}
            {transfer.status === "in_transit" ? (
              <PrimaryButton disabled={busy} onClick={() => void act(() => inventoryApi.receiveTransfer(transfer.id))}>
                {busy ? "Receiving…" : "Receive at destination"}
              </PrimaryButton>
            ) : null}
          </>
        ) : undefined
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-charcoal/60">
        <DocStatus status={transfer.status} />
        <span>Requested {formatDate(transfer.created_at)}{transfer.requested_by_name ? ` by ${transfer.requested_by_name}` : ""}</span>
        {transfer.shipped_at ? <span>Shipped {formatDate(transfer.shipped_at)}</span> : null}
        {transfer.received_at ? <span>Received {formatDate(transfer.received_at)}</span> : null}
      </div>
      <ul className="divide-y divide-line rounded-2xl border border-line">
        {transfer.lines.map((line) => {
          const units = transfer.serials.filter((serial) => serial.transfer_line_id === line.id);
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
                <span className="font-semibold tabular-nums">{line.quantity}</span>
              </div>
              {units.length > 0 ? (
                <p className="mt-2 flex flex-wrap gap-1">
                  {units.map((unit) => (
                    <span key={unit.serial_number_id} className="rounded-full bg-surface px-2 py-0.5 font-mono text-[11px]">
                      •••• {unit.last4} · {unit.status.replace(/_/g, " ")}
                    </span>
                  ))}
                </p>
              ) : null}
              {manage && transfer.status === "requested" && line.is_serialized ? (
                <label className="mt-3 block text-sm font-medium">
                  IMEIs to ship ({line.quantity})
                  <textarea
                    rows={2}
                    value={serials[line.id] ?? ""}
                    onChange={(event) => setSerials({ ...serials, [line.id]: event.target.value })}
                    placeholder="Scan one per line"
                    className="mt-1 w-full rounded-2xl border border-line bg-surface p-3 font-mono text-sm"
                  />
                </label>
              ) : null}
            </li>
          );
        })}
      </ul>
      {transfer.note ? <p className="mt-4 text-sm text-charcoal/70">{transfer.note}</p> : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
