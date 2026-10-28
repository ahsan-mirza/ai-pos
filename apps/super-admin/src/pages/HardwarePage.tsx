import type { HardwareItem } from "@ai-pos/shared-types";
import { DataTable, Select, type DataTableColumn } from "@ai-pos/ui";
import { useCallback, useEffect, useState } from "react";
import { FilterSearch, FilterSlot, PageHeader } from "../components/PageHeader";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money } from "../lib/format";
import { useSession } from "../lib/session";

interface Category {
  id: string;
  name: string;
  sort_order: number;
  active: boolean;
}

interface OrderLine {
  id: string;
  sku: string;
  name: string;
  store_label: string;
  mode: string;
  quantity: number;
  monthly_fils: number;
  deposit_fils: number;
  fee_fils: number;
  purchase_fils: number;
  delivery_fils: number;
  fulfilled_qty: number;
  serials: string[];
}

interface Assignment {
  id: string;
  order_line_id: string;
  store_label: string;
  serial: string;
  quantity: number;
  deposit_fils: number;
  status: string;
  deposit_decision: string;
  condition_note: string;
}

interface HardwareOrder {
  id: string;
  reference: string;
  tenant_name: string;
  payment_status: string;
  fulfillment_status: string;
  monthly_fils: number;
  deposit_fils: number;
  one_time_fils: number;
  currency: string;
  line_count: number;
  created_at: string;
  lines: OrderLine[];
  assignments: Assignment[];
}

function aed(fils: number): string {
  return money(fils, "AED");
}

function filsOf(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return Math.round(parsed * 100);
}

function blankItem(categoryId: string): HardwareItem & { reason: string } {
  return {
    id: "",
    sku: "",
    name: "",
    category_id: categoryId,
    category_name: "",
    description: "",
    image_url: "",
    manufacturer: "",
    model: "",
    lease_available: true,
    purchase_available: false,
    monthly_fils: 0,
    deposit_fils: 0,
    fee_fils: 0,
    purchase_fils: null,
    delivery_fils: 0,
    currency: "AED",
    min_qty: 1,
    max_qty: 20,
    stock_qty: null,
    counts_as_register: false,
    compatibility: "",
    active: true,
    archived: false,
    available: false,
    internal_notes: "",
    reason: "",
  };
}

export function HardwarePage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [tab, setTab] = useState<"catalogue" | "orders">("catalogue");
  const [query, setQuery] = useState("");
  const [payment, setPayment] = useState("");
  const [fulfillment, setFulfillment] = useState("");
  return (
    <section>
      <PageHeader
        title="Hardware"
        description="Optional products a store can lease or buy. A refundable deposit is not monthly revenue."
        controls={
          <>
            <div className="inline-flex gap-2" role="group" aria-label="Hardware section">
              <GhostButton aria-pressed={tab === "catalogue"} onClick={() => setTab("catalogue")}>
                Catalogue
              </GhostButton>
              <GhostButton aria-pressed={tab === "orders"} onClick={() => setTab("orders")}>
                Orders
              </GhostButton>
            </div>
            {tab === "orders" ? (
              <>
                <FilterSearch label="Search orders" value={query} onChange={setQuery} placeholder="Search orders" />
                <FilterSlot>
                  <Select
                    aria-label="Payment"
                    value={payment}
                    onChange={setPayment}
                    options={[
                      { value: "", label: "Any payment" },
                      { value: "awaiting_payment", label: "Awaiting payment" },
                      { value: "under_review", label: "Under review" },
                      { value: "paid", label: "Paid" },
                      { value: "canceled", label: "Canceled" },
                    ]}
                  />
                </FilterSlot>
                <FilterSlot wide>
                  <Select
                    aria-label="Fulfillment"
                    value={fulfillment}
                    onChange={setFulfillment}
                    options={[
                      { value: "", label: "Any fulfillment" },
                      { value: "awaiting_payment", label: "Awaiting payment" },
                      { value: "awaiting_fulfillment", label: "Awaiting fulfillment" },
                      { value: "partial", label: "Partially fulfilled" },
                      { value: "fulfilled", label: "Fulfilled" },
                      { value: "canceled", label: "Canceled" },
                      { value: "returned", label: "Returned" },
                    ]}
                  />
                </FilterSlot>
              </>
            ) : null}
          </>
        }
      />
      {tab === "catalogue" ? <Catalogue admin={admin} /> : <Orders admin={admin} query={query} payment={payment} fulfillment={fulfillment} />}
    </section>
  );
}

function Catalogue({ admin }: { admin: boolean }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [items, setItems] = useState<HardwareItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<(HardwareItem & { reason: string }) | null>(null);
  const [viewing, setViewing] = useState<HardwareItem | null>(null);
  const [categoryEdit, setCategoryEdit] = useState<Category | null>(null);
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [reason, setReason] = useState("");
  const load = useCallback(async () => {
    try {
      const [foundCategories, foundItems] = await Promise.all([
        api.get<Category[]>("/hardware/categories"),
        api.get<HardwareItem[]>("/hardware/items"),
      ]);
      setCategories(foundCategories);
      setItems(foundItems);
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the hardware catalogue."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const needle = query.trim().toLowerCase();
  const visible = items.filter((item) => {
    if (categoryId !== "" && item.category_id !== categoryId) return false;
    if (needle === "") return true;
    return `${item.name} ${item.sku} ${item.category_name} ${item.description}`.toLowerCase().includes(needle);
  });
  return (
    <div className="mt-6">
      <ErrorNote message={error} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <FilterSearch label="Search hardware" value={query} onChange={setQuery} placeholder="Search name or SKU" />
        <FilterSlot>
          <Select
            aria-label="Category"
            value={categoryId}
            onChange={setCategoryId}
            options={[{ value: "", label: "All categories" }, ...categories.map((category) => ({ value: category.id, label: category.name }))]}
          />
        </FilterSlot>
        {admin ? <PrimaryButton onClick={() => setEditing(blankItem(categories.find((category) => category.active)?.id ?? ""))}>New item</PrimaryButton> : null}
      </div>
      <h2 className="text-sm font-semibold">Categories</h2>
      <ul className="mt-2 overflow-hidden rounded-2xl border border-line bg-white">
        {categories.map((category) => {
          const count = items.filter((item) => item.category_id === category.id).length;
          return (
            <li key={category.id} className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-b-0">
              <span className="min-w-0 flex-1">
                <span className="font-medium">{category.name}</span>
                <span className="mt-0.5 block text-xs text-charcoal/50">
                  {count} {count === 1 ? "product" : "products"} · {category.active ? "Visible" : "Hidden"}
                </span>
              </span>
              {admin ? <GhostButton onClick={() => setCategoryEdit(category)}>Edit</GhostButton> : null}
            </li>
          );
        })}
      </ul>
      {admin ? (
        <form
          className="mt-3 flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .post("/hardware/categories", { name: categoryName, sort_order: categories.length, active: true, reason })
              .then(() => {
                setCategoryName("");
                setReason("");
                return load();
              })
              .catch((caught) => setError(errorText(caught, "Could not add the category.")));
          }}
        >
          <Field label="New category" value={categoryName} onChange={(event) => setCategoryName(event.target.value)} />
          <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          <PrimaryButton type="submit">Add category</PrimaryButton>
        </form>
      ) : null}
      <p className="mt-2 text-xs text-charcoal/50">Categories that contain products stay in the catalogue. Hiding a category does not delete its products.</p>
      {visible.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-dashed border-line bg-white px-4 py-8 text-center text-sm text-charcoal/60">No hardware matches.</p>
      ) : null}
      <ul className="mt-4 grid gap-3 md:grid-cols-2">
        {visible.map((item) => (
          <li key={item.id} className="flex gap-4 rounded-2xl border border-line bg-white p-4 shadow-sm">
            {item.image_url ? (
              <img src={item.image_url} alt="" className="h-20 w-20 shrink-0 rounded-xl object-cover" />
            ) : (
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-xl bg-[#f8fafc] text-[10px] text-charcoal/40">No photo</div>
            )}
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{item.name}</p>
              <p className="font-mono text-xs text-charcoal/50">{item.sku} · {item.category_name}</p>
              <p className="mt-2 text-sm text-charcoal/70">
                {item.lease_available ? `${aed(item.monthly_fils)} / month lease` : "No lease"}
                {item.purchase_available && item.purchase_fils != null ? ` · buy ${aed(item.purchase_fils)}` : ""}
              </p>
              {item.deposit_fils > 0 ? <p className="text-xs text-charcoal/50">Refundable deposit {aed(item.deposit_fils)}, charged once</p> : null}
              <p className="mt-1 text-xs text-charcoal/50">
                {item.active ? "Published" : "Unpublished"}
                {item.available ? "" : " · not available to order"}
                {item.archived ? " · archived" : ""}
              </p>
              <div className="mt-3 flex gap-2">
                <GhostButton onClick={() => setViewing(item)}>View</GhostButton>
                {admin ? <GhostButton onClick={() => setEditing({ ...item, reason: "" })}>Edit</GhostButton> : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {viewing ? <ItemDetail item={viewing} onClose={() => setViewing(null)} onEdit={admin ? () => { setEditing({ ...viewing, reason: "" }); setViewing(null); } : undefined} /> : null}
      {categoryEdit ? (
        <CategoryEditor
          category={categoryEdit}
          onClose={() => setCategoryEdit(null)}
          onSaved={() => {
            setCategoryEdit(null);
            void load();
          }}
        />
      ) : null}
      {editing ? (
        <ItemEditor
          item={editing}
          categories={categories}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function ItemDetail({ item, onClose, onEdit }: { item: HardwareItem; onClose: () => void; onEdit?: () => void }) {
  return (
    <Modal
      wide
      title={item.name}
      subtitle={item.sku}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Close</GhostButton>
          {onEdit ? <PrimaryButton onClick={onEdit}>Edit</PrimaryButton> : null}
        </>
      }
    >
      <div className="grid gap-3 text-sm">
        {item.image_url ? <img src={item.image_url} alt="" className="h-40 w-full rounded-2xl object-cover" /> : null}
        <p className="text-charcoal/70">{item.description || "No public description."}</p>
        <p>Category: {item.category_name}</p>
        <p>{item.lease_available ? `Lease ${aed(item.monthly_fils)} / month` : "Lease is not offered"}</p>
        <p>{item.purchase_available && item.purchase_fils != null ? `Purchase ${aed(item.purchase_fils)}` : "Purchase is not offered"}</p>
        <p>{item.deposit_fils > 0 ? `Refundable deposit ${aed(item.deposit_fils)}, charged once` : "No refundable deposit"}</p>
        <p>{item.fee_fils > 0 ? `One-time fee ${aed(item.fee_fils)}` : "No one-time fee"}</p>
        <p>{item.delivery_fils > 0 ? `Delivery ${aed(item.delivery_fils)}` : "No delivery charge"}</p>
        <p>Publication: {item.active && !item.archived ? "Published when it is also available to order" : "Hidden from the public catalogue"}</p>
        <p>Availability: {item.available ? "Can be ordered" : "Not available"}</p>
        {item.internal_notes ? <p className="text-charcoal/50">Internal: {item.internal_notes}</p> : null}
      </div>
    </Modal>
  );
}

function CategoryEditor({ category, onClose, onSaved }: { category: Category; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(category.name);
  const [active, setActive] = useState(category.active);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title={category.name}
      onClose={onClose}
      footer={
        <PrimaryButton
          loading={busy}
          disabled={reason.trim().length < 3}
          onClick={() => {
            setBusy(true);
            void api
              .patch(`/hardware/categories/${category.id}`, { name, sort_order: category.sort_order, active, reason: reason.trim() })
              .then(onSaved)
              .catch((caught) => {
                setBusy(false);
                setError(errorText(caught, "Could not save the category."));
              });
          }}
        >
          Save
        </PrimaryButton>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Visible
        </label>
        <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

function ItemEditor({
  item,
  categories,
  onClose,
  onSaved,
}: {
  item: HardwareItem & { reason: string };
  categories: Category[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState(item);
  const [monthly, setMonthly] = useState((item.monthly_fils / 100).toFixed(2));
  const [deposit, setDeposit] = useState((item.deposit_fils / 100).toFixed(2));
  const [fee, setFee] = useState((item.fee_fils / 100).toFixed(2));
  const [purchase, setPurchase] = useState(item.purchase_fils == null ? "" : (item.purchase_fils / 100).toFixed(2));
  const [delivery, setDelivery] = useState((item.delivery_fils / 100).toFixed(2));
  const [stock, setStock] = useState(item.stock_qty == null ? "" : String(item.stock_qty));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<typeof draft>) => setDraft({ ...draft, ...patch });
  return (
    <Modal
      wide
      title={item.id ? "Edit hardware" : "New hardware"}
      onClose={onClose}
      footer={
        <PrimaryButton
          loading={busy}
          onClick={() => {
            setBusy(true);
            const body = {
              ...draft,
              image_url: draft.image_url || null,
              monthly_fils: filsOf(monthly),
              deposit_fils: filsOf(deposit),
              fee_fils: filsOf(fee),
              purchase_fils: purchase.trim() === "" ? null : filsOf(purchase),
              delivery_fils: filsOf(delivery),
              stock_qty: stock.trim() === "" ? null : Number(stock),
              currency: "AED",
            };
            const request = item.id
              ? api.patch(`/hardware/items/${item.id}`, body)
              : api.post("/hardware/items", body);
            void request
              .then(() => onSaved())
              .catch((caught) => {
                setBusy(false);
                setError(errorText(caught, "Could not save the hardware item."));
              });
          }}
        >
          Save
        </PrimaryButton>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" required value={draft.name} onChange={(event) => set({ name: event.target.value })} />
        <Field label="SKU" required value={draft.sku} onChange={(event) => set({ sku: event.target.value.toUpperCase() })} />
        <label className="text-sm">
          Category
          <select
            className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2"
            value={draft.category_id}
            onChange={(event) => set({ category_id: event.target.value })}
          >
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <Field label="Manufacturer" value={draft.manufacturer} onChange={(event) => set({ manufacturer: event.target.value })} />
        <Field label="Model" value={draft.model} onChange={(event) => set({ model: event.target.value })} />
        <Field label="Image URL" value={draft.image_url ?? ""} onChange={(event) => set({ image_url: event.target.value })} />
        <Field label="Monthly lease (AED)" value={monthly} onChange={(event) => setMonthly(event.target.value)} />
        <Field label="Refundable deposit (AED)" value={deposit} onChange={(event) => setDeposit(event.target.value)} />
        <Field label="Non-refundable fee (AED)" value={fee} onChange={(event) => setFee(event.target.value)} />
        <Field label="Purchase price (AED)" value={purchase} onChange={(event) => setPurchase(event.target.value)} />
        <Field label="Delivery or installation (AED)" value={delivery} onChange={(event) => setDelivery(event.target.value)} />
        <Field label="Minimum quantity" value={String(draft.min_qty)} onChange={(event) => set({ min_qty: Number(event.target.value) || 1 })} />
        <Field label="Maximum quantity" value={String(draft.max_qty)} onChange={(event) => set({ max_qty: Number(event.target.value) || 1 })} />
        <Field label="Stock (blank if untracked)" value={stock} onChange={(event) => setStock(event.target.value)} />
        <Field label="Compatibility" value={draft.compatibility} onChange={(event) => set({ compatibility: event.target.value })} />
        <Field label="Internal notes" value={draft.internal_notes ?? ""} onChange={(event) => set({ internal_notes: event.target.value })} />
        <Field label="Reason" required value={draft.reason} onChange={(event) => set({ reason: event.target.value })} />
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.lease_available} onChange={(event) => set({ lease_available: event.target.checked })} />
        Available to lease
      </label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.purchase_available} onChange={(event) => set({ purchase_available: event.target.checked })} />
        Available to purchase
      </label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.counts_as_register} onChange={(event) => set({ counts_as_register: event.target.checked })} />
        Counts as a register
      </label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.active} onChange={(event) => set({ active: event.target.checked })} />
        Active
      </label>
      <label className="mt-2 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.archived} onChange={(event) => set({ archived: event.target.checked })} />
        Archived
      </label>
      <Field className="mt-3" label="Description" multiline value={draft.description} onChange={(event) => set({ description: event.target.value })} />
      <ErrorNote message={error} />
    </Modal>
  );
}

function Orders({
  admin,
  query,
  payment,
  fulfillment,
}: {
  admin: boolean;
  query: string;
  payment: string;
  fulfillment: string;
}) {
  const [rows, setRows] = useState<HardwareOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [error, setError] = useState<string | null>(null);
  const filterKey = `${query}\0${payment}\0${fulfillment}`;
  const [seenFilters, setSeenFilters] = useState(filterKey);
  if (seenFilters !== filterKey) {
    setSeenFilters(filterKey);
    setPage(1);
  }
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<HardwareOrder | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      offset: String((page - 1) * pageSize),
      limit: String(pageSize),
    });
    if (query.trim()) params.set("q", query.trim());
    if (payment) params.set("payment", payment);
    if (fulfillment) params.set("fulfillment", fulfillment);
    try {
      const found = await api.page<HardwareOrder>(`/hardware/orders?${params.toString()}`);
      setRows(found.rows);
      setTotal(found.total);
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load hardware orders."));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, query, payment, fulfillment]);
  useEffect(() => {
    void load();
  }, [load]);
  const columns: DataTableColumn<HardwareOrder>[] = [
    { header: "Order", cell: (row) => row.reference },
    { header: "Tenant", cell: (row) => row.tenant_name },
    { header: "Items", align: "right", cell: (row) => row.line_count },
    { header: "Monthly lease", align: "right", cell: (row) => aed(row.monthly_fils) },
    { header: "Deposit", align: "right", cell: (row) => aed(row.deposit_fils) },
    { header: "Payment", cell: (row) => row.payment_status.replaceAll("_", " ") },
    { header: "Fulfillment", cell: (row) => row.fulfillment_status.replaceAll("_", " ") },
    {
      header: "",
      cell: (row) => (
        <GhostButton
          onClick={() => {
            void api
              .get<HardwareOrder>(`/hardware/orders/${row.id}`)
              .then(setOpen)
              .catch((caught) => setError(errorText(caught, "Could not open the order.")));
          }}
        >
          Open
        </GhostButton>
      ),
    },
  ];
  return (
    <div>
      <ErrorNote message={error} />
      <DataTable
        aria-label="Hardware orders"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        isLoading={loading && rows.length === 0}
        isFetching={loading && rows.length > 0}
        minWidth="980px"
        emptyState={{ title: "No hardware orders", description: "Orders appear when a tenant selects hardware at checkout." }}
        pagination={{
          mode: "server",
          currentPage: page,
          pageSize,
          totalRecords: total,
          onPageChange: setPage,
          onPageSizeChange: (size) => {
            setPageSize(size);
            setPage(1);
          },
        }}
      />
      {open ? (
        <OrderDetail
          order={open}
          admin={admin}
          onClose={() => setOpen(null)}
          onChanged={(next) => {
            setOpen(next);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function OrderDetail({
  order,
  admin,
  onClose,
  onChanged,
}: {
  order: HardwareOrder;
  admin: boolean;
  onClose: () => void;
  onChanged: (order: HardwareOrder) => void;
}) {
  const [lineId, setLineId] = useState(order.lines[0]?.id ?? "");
  const [qty, setQty] = useState(String(order.lines[0]?.quantity ?? 0));
  const [serials, setSerials] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal wide title={order.reference} subtitle={`${order.tenant_name} · ${order.payment_status} · ${order.fulfillment_status}`} onClose={onClose}>
      <p className="text-sm text-charcoal/70">
        Lease {aed(order.monthly_fils)} / month · refundable deposit {aed(order.deposit_fils)} · other one-time {aed(order.one_time_fils)}
      </p>
      <ul className="mt-3 grid gap-2">
        {order.lines.map((line) => (
          <li key={line.id} className="rounded-2xl bg-surface px-3 py-2 text-sm">
            <span className="font-medium">{line.name}</span> · {line.sku} · {line.store_label || "Store"} · {line.mode} · qty {line.quantity}
            <span className="block text-charcoal/60">
              {aed(line.monthly_fils)} / month · deposit {aed(line.deposit_fils)} · fulfilled {line.fulfilled_qty}
              {line.serials.length ? ` · ${line.serials.join(", ")}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {order.assignments.map((row) => (
        <DepositForm key={row.id} assignment={row} admin={admin} onError={setError} onSaved={() => {
          void api.get<HardwareOrder>(`/hardware/orders/${order.id}`).then(onChanged);
        }} />
      ))}
      {admin ? (
        <form
          className="mt-4 grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .post(`/hardware/orders/${order.id}/fulfill`, {
                line_id: lineId,
                fulfilled_qty: Number(qty) || 0,
                serials: serials.split(",").map((value) => value.trim()).filter(Boolean),
                reason,
              })
              .then((next) => onChanged(next as HardwareOrder))
              .catch((caught) => setError(errorText(caught, "Could not update fulfillment.")));
          }}
        >
          <label className="text-sm">
            Line
            <select className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2" value={lineId} onChange={(event) => setLineId(event.target.value)}>
              {order.lines.map((line) => (
                <option key={line.id} value={line.id}>
                  {line.name} · {line.store_label}
                </option>
              ))}
            </select>
          </label>
          <Field label="Fulfilled quantity" value={qty} onChange={(event) => setQty(event.target.value)} />
          <Field label="Serial numbers" hint="Comma separated" value={serials} onChange={(event) => setSerials(event.target.value)} />
          <Field label="Reason" required value={reason} onChange={(event) => setReason(event.target.value)} />
          <PrimaryButton type="submit">Record fulfillment</PrimaryButton>
        </form>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}

function DepositForm({
  assignment,
  admin,
  onError,
  onSaved,
}: {
  assignment: Assignment;
  admin: boolean;
  onError: (message: string) => void;
  onSaved: () => void;
}) {
  const [decision, setDecision] = useState(assignment.deposit_decision);
  const [condition, setCondition] = useState(assignment.condition_note);
  const [reason, setReason] = useState("");
  if (!admin) {
    return (
      <p className="mt-2 text-sm text-charcoal/60">
        {assignment.store_label}: deposit {aed(assignment.deposit_fils)} · {assignment.deposit_decision}
      </p>
    );
  }
  return (
    <form
      className="mt-3 grid gap-2 rounded-2xl border border-line p-3"
      onSubmit={(event) => {
        event.preventDefault();
        void api
          .post("/hardware/deposits", {
            assignment_id: assignment.id,
            decision,
            condition_note: condition,
            reason,
          })
          .then(() => onSaved())
          .catch((caught) => onError(errorText(caught, "Could not save the deposit decision.")));
      }}
    >
      <p className="text-sm font-medium">
        Deposit {aed(assignment.deposit_fils)} · {assignment.store_label} · {assignment.status}
      </p>
      <label className="text-sm">
        Decision
        <select className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2" value={decision} onChange={(event) => setDecision(event.target.value)}>
          <option value="held">Held</option>
          <option value="refund_approved">Refund approved</option>
          <option value="refunded">Refunded</option>
          <option value="forfeited">Forfeited</option>
        </select>
      </label>
      <Field label="Condition on return" value={condition} onChange={(event) => setCondition(event.target.value)} />
      <Field label="Reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      <GhostButton type="submit">Save deposit decision</GhostButton>
    </form>
  );
}
