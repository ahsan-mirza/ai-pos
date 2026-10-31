import {
  formatMoney,
  Permission,
  SALES_ORDER_SOURCE_LABELS,
  SALES_ORDER_STATUS_LABELS,
  type BackorderRow,
  type Customer,
  type ProductSearchHit,
  type SalesOrder,
  type SalesOrderRow,
  type SalesOrderStatus,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { PackageCheck, Plus, Search, Trash2, Truck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ProductPicker } from "../../components/ui/ProductPicker";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { ApiRequestError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { customersApi } from "../customers/api";
import { formatDate, storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";
import { salesOrdersApi } from "./api";
import { SalesOrderDetail } from "./SalesOrderDetail";

type View = "OPEN" | "DRAFT" | "DELIVERED" | "all" | "backorders";

const VIEWS: { value: View; label: string }[] = [
  { value: "OPEN", label: "Open" },
  { value: "DRAFT", label: "Drafts" },
  { value: "DELIVERED", label: "Delivered" },
  { value: "all", label: "All" },
  { value: "backorders", label: "Backorders" },
];

export function OrderStatusChip({ status }: { status: SalesOrderStatus }) {
  const tone =
    status === "PARTIALLY_DELIVERED" || status === "PICKING"
      ? "bg-accent text-white"
      : status === "CONFIRMED"
        ? "bg-charcoal text-white"
        : status === "DELIVERED"
          ? "bg-surface text-charcoal ring-1 ring-line"
          : "bg-white text-charcoal/50 ring-1 ring-line";
  return (
    <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>
      {SALES_ORDER_STATUS_LABELS[status]}
    </span>
  );
}

export function SalesOrdersPage() {
  const { user, can } = useAuth();
  const { stores } = useStores();
  const { currency } = useCurrency();
  const [view, setView] = useState<View>("OPEN");
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [search, setSearch] = useState("");
  const pager = usePagination({ resetKeys: [view, storeId, search] });
  const [rows, setRows] = useState<SalesOrderRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [backorders, setBackorders] = useState<BackorderRow[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [page, waiting] = await Promise.all([
        view === "backorders"
          ? Promise.resolve(null)
          : salesOrdersApi.list(
              { status: view === "all" ? null : view, store_id: storeId || null, q: search.trim() || null },
              { offset: pager.offset, limit: pager.pageSize },
            ),
        salesOrdersApi.backorders(storeId || null),
      ]);
      if (page) {
        setRows(page.rows);
        setTotal(page.total);
      }
      setBackorders(waiting);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load sales orders."));
    } finally {
      setLoading(false);
    }
  }, [view, storeId, search, pager.offset, pager.pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  if (openId) {
    return (
      <SalesOrderDetail
        orderId={openId}
        onBack={() => {
          setOpenId(null);
          void load();
        }}
      />
    );
  }

  const waitingUnits = backorders.reduce((sum, row) => sum + row.backordered, 0);
  const coverable = backorders.filter((row) => row.available_now > 0).length;

  const columns: DataTableColumn<SalesOrderRow>[] = [
    {
      id: "order",
      header: "Order",
      cell: (row) => (
        <>
          <span className="block font-mono text-xs font-semibold">{row.number}</span>
          <span className="block text-xs text-charcoal/50">
            {formatDate(row.created_at)} · {SALES_ORDER_SOURCE_LABELS[row.source]}
          </span>
        </>
      ),
    },
    { id: "customer", header: "Customer", cell: (row) => <span className="font-medium">{row.customer_name}</span> },
    {
      id: "requested",
      header: "Wanted by",
      cell: (row) => (row.requested_date ? formatDate(row.requested_date) : "—"),
    },
    {
      id: "outstanding",
      header: "To deliver",
      align: "right",
      cell: (row) => (
        <>
          <span className="tabular-nums">{row.outstanding_units}</span>
          {row.backordered_units ? (
            <span className="block text-xs font-semibold text-accent">{row.backordered_units} backordered</span>
          ) : null}
        </>
      ),
    },
    {
      id: "value",
      header: "Value",
      align: "right",
      className: "font-semibold",
      cell: (row) => formatMoney(row.total_cents, row.currency),
    },
    { id: "status", header: "Status", className: "pl-6", cell: (row) => <OrderStatusChip status={row.status} /> },
  ];

  const backorderColumns: DataTableColumn<BackorderRow>[] = [
    {
      id: "order",
      header: "Order",
      cell: (row) => (
        <button type="button" onClick={() => setOpenId(row.order_id)} className="font-mono text-xs font-semibold hover:text-accent">
          {row.order_number}
        </button>
      ),
    },
    { id: "customer", header: "Customer", cell: (row) => row.customer_name },
    {
      id: "product",
      header: "Product",
      cell: (row) => (
        <>
          <span className="block font-medium">{row.product_name}</span>
          <span className="block font-mono text-xs text-charcoal/50">{row.sku}</span>
        </>
      ),
    },
    { id: "waiting", header: "Backordered", align: "right", className: "font-semibold text-accent", cell: (row) => row.backordered },
    {
      id: "free",
      header: "Free now",
      align: "right",
      cell: (row) => (row.available_now > 0 ? <span className="font-semibold">{row.available_now}</span> : "0"),
    },
    { id: "since", header: "Ordered", className: "pl-6", cell: (row) => formatDate(row.ordered_at) },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">{view === "backorders" ? "Lines waiting" : "Orders in this view"}</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{view === "backorders" ? backorders.length : total}</p>
          <p className="mt-2 text-xs text-white/50">Each delivery is invoiced as it leaves the branch</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Backordered units</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{waitingUnits}</p>
          <p className="mt-2 text-xs text-white/80">Reserved first come, first served as stock arrives</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Can be covered now</p>
          <p className={`mt-4 text-4xl font-semibold tabular-nums ${coverable ? "text-accent" : ""}`}>{coverable}</p>
          <p className="mt-2 text-xs text-charcoal/50">Backordered lines with free stock; open the order and allocate</p>
        </article>
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end justify-between gap-3 p-6 pb-5">
          <SegmentedControl label="Order view" value={view} options={VIEWS} onChange={setView} />
          <div className="flex flex-wrap items-end gap-3">
            {view === "backorders" ? null : (
              <label className="w-60">
                <span className="sr-only">Find an order</span>
                <span className="relative block">
                  <Search size={15} aria-hidden="true" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-charcoal/40" />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Order, customer or their ref"
                    className="w-full rounded-full border border-line bg-white py-2.5 pl-9 pr-4 text-sm focus:border-accent focus:outline-none"
                  />
                </span>
              </label>
            )}
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-52"
              />
            )}
            {can(Permission.SalesOrders) ? (
              <PrimaryButton onClick={() => setCreating(true)}>
                <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> New order
              </PrimaryButton>
            ) : null}
          </div>
          {error ? (
            <div className="w-full">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
        {view === "backorders" ? (
          <DataTable
            aria-label="Backorders"
            variant="flush"
            minWidth="880px"
            columns={backorderColumns}
            data={backorders}
            getRowId={(row) => `${row.order_id}-${row.product_id}`}
            isLoading={loading && backorders.length === 0}
            emptyState={{ icon: PackageCheck, title: "Nothing is waiting for stock" }}
          />
        ) : (
          <DataTable
            aria-label="Sales orders"
            variant="flush"
            minWidth="900px"
            columns={columns}
            data={rows ?? []}
            getRowId={(row) => row.id}
            onRowClick={(row) => setOpenId(row.id)}
            isLoading={rows === null && error === null}
            isFetching={loading && rows !== null}
            emptyState={{ icon: Truck, title: "No sales orders here" }}
            pagination={{
              mode: "server",
              currentPage: pager.page,
              pageSize: pager.pageSize,
              totalRecords: total,
              onPageChange: pager.setPage,
              onPageSizeChange: pager.setPageSize,
            }}
          />
        )}
      </div>
      {creating ? (
        <NewOrderModal
          defaultStoreId={storeId || user?.store_id || stores.find((store) => !store.is_warehouse)?.id || ""}
          lockStore={Boolean(user?.store_id)}
          stores={stores}
          currency={currency}
          onClose={() => setCreating(false)}
          onCreated={(order) => {
            setCreating(false);
            setToast(`${order.number} saved${order.status === "DRAFT" ? " as a draft" : " and stock reserved"}.`);
            setOpenId(order.id);
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

interface DraftLine {
  product_id: string;
  name: string;
  sku: string;
  list_cents: number;
  quantity: string;
  price: string;
}

function NewOrderModal({
  defaultStoreId,
  lockStore,
  stores,
  currency,
  onClose,
  onCreated,
}: {
  defaultStoreId: string;
  lockStore: boolean;
  stores: ReturnType<typeof useStores>["stores"];
  currency: string;
  onClose: () => void;
  onCreated: (order: SalesOrder) => void;
}) {
  const { user, can } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [storeId, setStoreId] = useState(defaultStoreId);
  const [customerId, setCustomerId] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [requested, setRequested] = useState("");
  const [reference, setReference] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [confirm, setConfirm] = useState(true);
  const [creditBlocked, setCreditBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canPrice = can(Permission.PosPriceOverride);
  const canCredit = can(Permission.CustomersManage);

  useEffect(() => {
    void customersApi
      .list({})
      .then(setCustomers)
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load customers.")));
  }, []);

  const customer = customers.find((row) => row.id === customerId) ?? null;
  const total = lines.reduce((sum, line) => {
    const quantity = Number(line.quantity) || 0;
    const price = line.price.trim() === "" ? line.list_cents : Math.round(Number(line.price) * 100);
    return sum + quantity * price;
  }, 0);

  const add = (hit: ProductSearchHit) => {
    setLines((current) =>
      current.some((line) => line.product_id === hit.product.id)
        ? current
        : [
            ...current,
            {
              product_id: hit.product.id,
              name: hit.product.name,
              sku: hit.product.sku,
              list_cents: hit.product.price_cents,
              quantity: "1",
              price: "",
            },
          ],
    );
  };

  const save = async (approveCredit: boolean) => {
    if (!storeId || !customerId) return setError("Choose the branch and the customer.");
    if (lines.length === 0) return setError("Add at least one product.");
    const payload = lines.map((line) => ({
      product_id: line.product_id,
      quantity: Number(line.quantity),
      unit_price_cents: line.price.trim() === "" ? null : Math.round(Number(line.price) * 100),
    }));
    if (payload.some((line) => !Number.isInteger(line.quantity) || line.quantity < 1)) {
      return setError("Quantities must be whole numbers of 1 or more.");
    }
    const priced = payload.some((line) => line.unit_price_cents !== null);
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await salesOrdersApi.create({
          id: crypto.randomUUID(),
          store_id: storeId,
          customer_id: customerId,
          sale_type: customer?.customer_type === "WHOLESALE" ? "WHOLESALE" : "RETAIL",
          lines: payload,
          requested_date: requested || null,
          customer_reference: reference.trim() || null,
          delivery_address: address.trim() || null,
          notes: notes.trim() || null,
          confirm,
          price_approved_by_id: priced ? (user?.id ?? null) : null,
          credit_approved_by_id: approveCredit ? (user?.id ?? null) : null,
        }),
      );
    } catch (caught) {
      setCreditBlocked(caught instanceof ApiRequestError && caught.code === "credit_limit");
      setError(errorMessage(caught, "Could not save the order."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      width="lg"
      title="New sales order"
      subtitle="Prices follow the customer's tier. Confirming reserves stock; whatever is short waits as a backorder."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          {creditBlocked && canCredit ? (
            <GhostButton disabled={busy} onClick={() => void save(true)}>
              Approve credit and save
            </GhostButton>
          ) : null}
          <PrimaryButton disabled={busy} onClick={() => void save(false)}>
            {busy ? "Saving…" : confirm ? `Confirm order · ${formatMoney(total, currency)}` : "Save draft"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {lockStore ? null : <SelectField label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} />}
          <SelectField
            label="Customer"
            value={customerId}
            placeholder="Choose a customer"
            options={customers.map((row) => ({
              value: row.id,
              label: row.company_name || row.name,
              hint: row.customer_type === "WHOLESALE" ? `Wholesale · ${row.price_tier}` : "Retail",
            }))}
            onChange={(value) => {
              setCustomerId(value);
              const picked = customers.find((row) => row.id === value);
              if (picked?.address && !address) setAddress(picked.address);
            }}
          />
        </div>
        {customer && customer.customer_type === "WHOLESALE" && customer.credit_limit_cents > 0 ? (
          <p className="rounded-2xl bg-surface px-4 py-3 text-xs tabular-nums text-charcoal/70">
            Owes {formatMoney(customer.current_balance_cents, currency)} of a {formatMoney(customer.credit_limit_cents, currency)} limit.
            {customer.credit_hold ? " On credit hold." : ""}
          </p>
        ) : null}
        <ProductPicker onPick={add} />
        {lines.length ? (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Product</th>
                <th className="pb-2 text-right font-medium">Qty</th>
                <th className="pb-2 text-right font-medium">Unit price</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => (
                <tr key={line.product_id} className="border-t border-line">
                  <td className="py-2">
                    <span className="block font-medium">{line.name}</span>
                    <span className="block font-mono text-xs text-charcoal/50">{line.sku}</span>
                  </td>
                  <td className="py-2 text-right">
                    <input
                      aria-label={`Quantity of ${line.name}`}
                      inputMode="numeric"
                      value={line.quantity}
                      onChange={(event) =>
                        setLines((current) =>
                          current.map((row, at) => (at === index ? { ...row, quantity: event.target.value.replace(/[^\d]/g, "") } : row)),
                        )
                      }
                      className="w-20 rounded-xl border border-line bg-surface px-3 py-1.5 text-right tabular-nums focus:border-accent focus:outline-none"
                    />
                  </td>
                  <td className="py-2 text-right">
                    {canPrice ? (
                      <input
                        aria-label={`Agreed price of ${line.name}`}
                        inputMode="decimal"
                        value={line.price}
                        placeholder="Tier price"
                        onChange={(event) =>
                          setLines((current) =>
                            current.map((row, at) => (at === index ? { ...row, price: event.target.value.replace(/[^\d.]/g, "") } : row)),
                          )
                        }
                        className="w-28 rounded-xl border border-line bg-surface px-3 py-1.5 text-right tabular-nums focus:border-accent focus:outline-none"
                      />
                    ) : (
                      <span className="text-charcoal/60">Tier price</span>
                    )}
                  </td>
                  <td className="py-2 pl-2 text-right">
                    <button
                      type="button"
                      aria-label={`Remove ${line.name}`}
                      onClick={() => setLines((current) => current.filter((_, at) => at !== index))}
                      className={`text-charcoal/40 ${actionHoverClass("danger")}`}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Wanted by (optional)" type="date" value={requested} onChange={(event) => setRequested(event.target.value)} />
          <TextField
            label="Customer's reference (optional)"
            value={reference}
            maxLength={64}
            placeholder="Their PO number"
            onChange={(event) => setReference(event.target.value)}
          />
        </div>
        <TextField label="Deliver to" value={address} maxLength={255} onChange={(event) => setAddress(event.target.value)} />
        <TextField label="Notes (optional)" value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} />
        <Toggle
          checked={confirm}
          onChange={setConfirm}
          label="Confirm now"
          description="Checks the credit limit and reserves stock. Leave off to save a draft to finish later."
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
