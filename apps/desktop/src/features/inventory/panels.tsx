import {
  ADJUSTMENT_NOTE_MIN_LENGTH,
  AdjustmentReason,
  adjustmentReasonLabels,
  formatMoney,
  stockStatusLabel,
  type AdjustmentReason as Reason,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { beginRequest, useDebouncedSearch } from "../../components/shell/posControls";
import { useConfirm } from "../../components/ConfirmDialog";
import { activeStore } from "../checkout/currency";
import {
  inventoryApi,
  inventoryError,
  type BatchDetail,
  type CategoryRow,
  type CountDetail,
  type ProductRow,
  type PurchaseOrder,
  type StockRow,
} from "./api";
import {
  blankLine,
  purchaseOrderLines,
  receiptLines,
  transferLines,
  type DraftLine,
  type ReceiptDraft,
} from "./documentLines";
import { ProductDrawer } from "./productForm";
import { Banner, Drawer, Field, FilterSearch, PosSearchToolbar, PrimaryButton, QuietButton, Table, control } from "./ui";

export interface WorkspaceAccess {
  online: boolean;
  storeId: string | null;
  manage: boolean;
  /** Catalog writes are tenant-wide. A store-bound sign-in can search and select, and the API refuses the write. */
  catalogAdmin: boolean;
  pharmacy: boolean;
  pharmacyCatalogue: boolean;
  canAdjust: boolean;
  canPrice: boolean;
  weighed: boolean;
  serialized: boolean;
  fashion: boolean;
  fnb: boolean;
  recipes: boolean;
  profile: string;
}

function money(cents: number): string {
  return formatMoney(cents, activeStore().currency);
}

function useResource<T>(load: () => Promise<T>, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const gate = useRef({ current: 0 });
  const reload = useCallback(() => {
    const current = beginRequest(gate.current);
    setLoading(true);
    setError(null);
    load()
      .then((value) => {
        if (!current()) return;
        setData(value);
      })
      .catch((caught) => {
        if (!current()) return;
        setError(inventoryError(caught, "Could not load this list."));
      })
      .finally(() => {
        if (current()) setLoading(false);
      });
  }, [load]);
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    reload();
  }, [enabled, reload]);
  return { data, error, loading, reload, setError };
}

function ProductSelect({
  storeId,
  online,
  value,
  onChange,
}: {
  storeId: string | null;
  online: boolean;
  value: string;
  onChange: (id: string) => void;
}) {
  const load = useCallback(() => inventoryApi.products({ limit: 100, store_id: storeId }), [storeId]);
  const { data } = useResource(load, online);
  return (
    <select className={control} aria-label="Product" value={value} onChange={(event) => onChange(event.target.value)} required>
      <option value="">Product</option>
      {(data ?? []).map((product) => (
        <option key={product.id} value={product.id}>{product.sku} · {product.name}</option>
      ))}
    </select>
  );
}

function cents(value: string): number {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return 0;
  return Math.round(amount * 100);
}

export function StockPanel(access: WorkspaceAccess) {
  const confirm = useConfirm();
  const [q, setQ] = useState("");
  const { debounced, flush } = useDebouncedSearch(q);
  const [status, setStatus] = useState("");
  const [adjust, setAdjust] = useState<StockRow | null>(null);
  const [history, setHistory] = useState<StockRow | null>(null);
  const load = useCallback(
    () => inventoryApi.stock({ store_id: access.storeId, q: debounced, status: status || null }),
    [access.storeId, debounced, status],
  );
  const { data, error, loading, reload, setError } = useResource(load, access.online);
  const rows = data?.rows ?? [];
  return (
    <section className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-4">
        <Kpi label="On hand" value={String(data?.units_on_hand ?? "—")} />
        <Kpi label="Low" value={String(data?.low_count ?? "—")} />
        <Kpi label="Out" value={String(data?.out_count ?? "—")} />
        <Kpi label="Scope" value={data?.consolidated ? "All stores" : "This store"} />
      </div>
      <PosSearchToolbar
        query={q}
        onQuery={setQ}
        placeholder="Search product, SKU or barcode"
        statusValue={status}
        onStatus={setStatus}
        statusLabel="Stock status"
        statusOptions={[
          { value: "", label: "All statuses" },
          { value: "low", label: "Low stock" },
          { value: "out", label: "Out of stock" },
          { value: "over", label: "Overstock" },
        ]}
        onRefresh={reload}
        refreshing={loading}
        refreshDisabled={!access.online}
        onCommit={flush}
      />
      {error ? <Banner tone="error">{error}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading stock…</p> : null}
      {!access.online ? <Banner tone="info">Stock figures need the live ledger. The open sale is unchanged.</Banner> : null}
      <Table headers={["Product", "SKU", "Category", "Store", "On hand", "Reserved", "Available", "Reorder", "Status", ""]}>
        {rows.map((row) => (
          <tr key={`${row.product_id}-${row.store_id ?? "all"}`}>
            <td className="px-3 py-2">{row.name}</td>
            <td className="px-3 py-2 font-mono text-xs">{row.sku}</td>
            <td className="px-3 py-2">{row.category}{row.sub_category ? ` / ${row.sub_category}` : ""}</td>
            <td className="px-3 py-2">{row.store_name ?? "All"}</td>
            <td className="px-3 py-2 tabular-nums">{row.quantity_on_hand}</td>
            <td className="px-3 py-2 tabular-nums">{row.quantity_reserved}</td>
            <td className="px-3 py-2 tabular-nums">{row.quantity_available}</td>
            <td className="px-3 py-2 tabular-nums">{row.min_reorder_level}</td>
            <td className="px-3 py-2">{stockStatusLabel(row.status as "ok")}</td>
            <td className="px-3 py-2">
              <button type="button" className="font-semibold text-primary-600" onClick={() => setHistory(row)}>History</button>
              {access.canAdjust && row.store_id ? (
                <button type="button" className="ms-3 font-semibold text-primary-600" onClick={() => setAdjust(row)}>Adjust</button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
      {rows.length === 0 && !loading && access.online ? <p className="text-sm text-zinc-500">No stock rows match these filters.</p> : null}
      {history ? <MovementDrawer row={history} onClose={() => setHistory(null)} /> : null}
      {adjust ? (
        <AdjustDrawer
          row={adjust}
          pharmacy={access.pharmacy}
          online={access.online}
          onClose={() => setAdjust(null)}
          onSaved={() => {
            setAdjust(null);
            reload();
          }}
          onError={setError}
          confirm={confirm}
        />
      ) : null}
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-3 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function MovementDrawer({ row, onClose }: { row: StockRow; onClose: () => void }) {
  const load = useCallback(
    () => inventoryApi.movements({ product_id: row.product_id, store_id: row.store_id, limit: 20 }),
    [row.product_id, row.store_id],
  );
  const { data, error } = useResource(load);
  return (
    <Drawer title={`${row.name} movements`} onClose={onClose}>
      {error ? <Banner tone="error">{error}</Banner> : null}
      <ul className="space-y-2 text-sm">
        {(data ?? []).map((movement) => (
          <li key={movement.id} className="rounded-xl bg-zinc-50 p-2 dark:bg-zinc-900">
            <p className="font-semibold">{movement.movement_type} · {movement.quantity}</p>
            <p className="text-zinc-500">{movement.user_name ?? "System"} · {movement.created_at}</p>
            <p>{movement.note}</p>
          </li>
        ))}
      </ul>
    </Drawer>
  );
}

function AdjustDrawer({
  row,
  pharmacy,
  online,
  onClose,
  onSaved,
  onError,
  confirm,
}: {
  row: StockRow;
  pharmacy: boolean;
  online: boolean;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
  confirm: (options: { title: string; message: string; tone?: "danger" }) => Promise<boolean>;
}) {
  const [mode, setMode] = useState<"add" | "remove" | "set">("remove");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState<Reason>(AdjustmentReason.PhysicalCountAudit);
  const [note, setNote] = useState("");
  const [cost, setCost] = useState("");
  const [busy, setBusy] = useState(false);
  const blocked = pharmacy && row.lot_controlled;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!online || blocked) return;
    if (note.trim().length < ADJUSTMENT_NOTE_MIN_LENGTH) {
      onError(`The note needs at least ${ADJUSTMENT_NOTE_MIN_LENGTH} characters.`);
      return;
    }
    const accepted = await confirm({
      title: "Adjust stock",
      message: `${mode} ${quantity} of ${row.name} at ${row.store_name ?? "this store"}. This writes a ledger movement and does not overwrite the quantity.`,
      tone: "danger",
    });
    if (!accepted || !row.store_id) return;
    setBusy(true);
    try {
      await inventoryApi.adjust({
        adjustment_id: crypto.randomUUID(),
        product_id: row.product_id,
        store_id: row.store_id,
        mode,
        quantity: Number(quantity),
        reason_code: reason,
        note: note.trim(),
        unit_cost_cents: mode === "add" ? cents(cost) : undefined,
      });
      onSaved();
    } catch (caught) {
      onError(inventoryError(caught, "The adjustment was refused."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer title="Adjust stock" onClose={onClose}>
      {blocked ? (
        <Banner tone="info">This medicine is lot controlled. Receive it or record waste on the lot. A generic adjustment is not available here.</Banner>
      ) : (
        <form className="space-y-3" onSubmit={(event) => void submit(event)}>
          <Field label="Direction">
            <select className={control} value={mode} onChange={(event) => setMode(event.target.value as "add" | "remove" | "set")}>
              <option value="add">Add</option>
              <option value="remove">Remove</option>
              <option value="set">Set counted quantity</option>
            </select>
          </Field>
          <Field label="Quantity">
            <input className={control} inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
          </Field>
          <Field label="Reason">
            <select className={control} value={reason} onChange={(event) => setReason(event.target.value as Reason)}>
              {Object.entries(adjustmentReasonLabels).map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
          </Field>
          {mode === "add" ? (
            <Field label="Unit cost">
              <input className={control} inputMode="decimal" value={cost} onChange={(event) => setCost(event.target.value)} required />
            </Field>
          ) : null}
          <Field label="Note">
            <textarea className={`${control} h-24 py-2`} value={note} onChange={(event) => setNote(event.target.value)} />
          </Field>
          <PrimaryButton type="submit" disabled={busy || !online}>{busy ? "Saving…" : "Save adjustment"}</PrimaryButton>
        </form>
      )}
    </Drawer>
  );
}

export function ProductsPanel(access: WorkspaceAccess) {
  const [q, setQ] = useState("");
  const { debounced, flush } = useDebouncedSearch(q);
  const [editing, setEditing] = useState<ProductRow | "new" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (access.pharmacy) return inventoryApi.pharmacyProducts(debounced);
    if (debounced.trim()) {
      const hits = await inventoryApi.searchProducts(debounced.trim(), access.storeId);
      return hits.map((hit) => hit.product);
    }
    return inventoryApi.products({ limit: 100, store_id: access.storeId });
  }, [access.pharmacy, access.storeId, debounced]);
  const { data, error, loading, reload } = useResource(load, access.online);
  return (
    <section className="space-y-3">
      <div className="flex min-w-0 flex-nowrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <PosSearchToolbar query={q} onQuery={setQ} placeholder="Search products" onCommit={flush} />
        </div>
        {access.pharmacyCatalogue ? <PrimaryButton onClick={() => setEditing("new")} disabled={!access.online}>Add product</PrimaryButton> : null}
      </div>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading products…</p> : null}
      <Table headers={["Product", "SKU", "Barcode", "Price", "Status", ""]}>
        {(data ?? []).map((product) => (
          <tr key={product.id}>
            <td className="px-3 py-2">{product.name}</td>
            <td className="px-3 py-2 font-mono text-xs">{product.sku}</td>
            <td className="px-3 py-2">{product.barcode || "—"}</td>
            <td className="px-3 py-2">{money(product.price_cents)}</td>
            <td className="px-3 py-2">{product.is_active === false ? "Archived" : "Active"}</td>
            <td className="px-3 py-2">
              {access.pharmacyCatalogue ? (
                <button type="button" className="font-semibold text-primary-600" onClick={() => setEditing(product)}>Edit</button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
      {editing ? (
        <ProductDrawer
          access={access}
          product={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(text) => {
            setEditing(null);
            setMessage(text);
            reload();
          }}
        />
      ) : null}
    </section>
  );
}


export function CategoriesPanel(access: WorkspaceAccess) {
  return <NamedPanel access={access} title="category" kind="category" />;
}
export function BrandsPanel(access: WorkspaceAccess) {
  return <NamedPanel access={access} title="brand" kind="brand" />;
}

function NamedPanel({ access, title, kind }: { access: WorkspaceAccess; title: string; kind: "category" | "brand" }) {
  const load = useCallback(
    () => (kind === "category" ? inventoryApi.categories() : inventoryApi.brands()) as Promise<CategoryRow[]>,
    [kind],
  );
  const { data, error, loading, reload } = useResource(load, access.online);
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  async function create(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    try {
      if (kind === "category") await inventoryApi.createCategory({ name });
      else await inventoryApi.createBrand({ name });
      setName("");
      setMessage(`${title.charAt(0).toUpperCase()}${title.slice(1)} saved.`);
      reload();
    } catch (caught) {
      setFormError(inventoryError(caught, `Could not save this ${title}.`));
    }
  }
  return (
    <section className="space-y-3">
      {kind === "category" ? (
        <Banner tone="info">Categories are shared by every branch. A store-bound sign-in can view them; changing them stays with a user who is not tied to one store.</Banner>
      ) : null}
      {access.catalogAdmin ? (
        <form className="flex flex-wrap gap-2" onSubmit={(event) => void create(event)}>
          <input className={`${control} max-w-xs`} placeholder={`${title} name`} value={name} onChange={(event) => setName(event.target.value)} required />
          <PrimaryButton type="submit" disabled={!access.online}>Add {title}</PrimaryButton>
        </form>
      ) : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {formError ? <Banner tone="error">{formError}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading…</p> : null}
      <Table headers={["Name", "Code", "Products", ""]}>
        {(data ?? []).map((row) => (
          <tr key={row.id}>
            <td className="px-3 py-2">{row.name}</td>
            <td className="px-3 py-2">{row.code}</td>
            <td className="px-3 py-2">{row.product_count ?? 0}</td>
            <td className="px-3 py-2">
              {access.catalogAdmin ? (
                <button
                  type="button"
                  className="font-semibold text-primary-600"
                  onClick={() => {
                    const next = window.prompt("New name", row.name);
                    if (!next || !access.online) return;
                    const call = kind === "category" ? inventoryApi.updateCategory(row.id, { name: next }) : inventoryApi.updateBrand(row.id, { name: next });
                    void call.then(() => reload()).catch((caught) => setFormError(inventoryError(caught, "The rename was refused.")));
                  }}
                >
                  Rename
                </button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function ModelsPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.models(), []);
  const { data, error, loading, reload } = useResource(load, access.online);
  const [name, setName] = useState("");
  const [brandId, setBrandId] = useState("");
  const [subId, setSubId] = useState("");
  const [brands, setBrands] = useState<{ id: string; name: string }[]>([]);
  const [subs, setSubs] = useState<{ id: string; name: string }[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  useEffect(() => {
    if (!access.online) return;
    void inventoryApi.brands().then(setBrands).catch(() => undefined);
    void inventoryApi.categories().then((rows) => setSubs(rows.flatMap((row) => row.sub_categories))).catch(() => undefined);
  }, [access.online]);
  return (
    <section className="space-y-3">
      {access.catalogAdmin ? (
        <form
          className="grid gap-2 md:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            void inventoryApi.createModel({ name, brand_id: brandId, sub_category_id: subId }).then(() => {
              setName("");
              reload();
            }).catch((caught) => setFormError(inventoryError(caught, "Could not create the model.")));
          }}
        >
          <input className={control} placeholder="Model name" value={name} onChange={(event) => setName(event.target.value)} required />
          <select className={control} value={brandId} onChange={(event) => setBrandId(event.target.value)} required>
            <option value="">Brand</option>
            {brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}
          </select>
          <select className={control} value={subId} onChange={(event) => setSubId(event.target.value)} required>
            <option value="">Sub-category</option>
            {subs.map((sub) => <option key={sub.id} value={sub.id}>{sub.name}</option>)}
          </select>
          <PrimaryButton type="submit" disabled={!access.online}>Add model</PrimaryButton>
        </form>
      ) : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {formError ? <Banner tone="error">{formError}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading models…</p> : null}
      <Table headers={["Model", "Brand", "Code"]}>
        {(data ?? []).map((model) => (
          <tr key={model.id}>
            <td className="px-3 py-2">{model.name}</td>
            <td className="px-3 py-2">{model.brand_name}</td>
            <td className="px-3 py-2">{model.code || "—"}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function UnitsPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.units(), []);
  const { data, error, loading, reload } = useResource(load, access.online);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [factor, setFactor] = useState("10");
  const [formError, setFormError] = useState<string | null>(null);
  return (
    <section className="space-y-3">
      <Banner tone="info">A unit factor is how many pieces it contains. Changing a unit later renames it; it does not rewrite old sales.</Banner>
      {access.manage ? (
        <form
          className="grid gap-2 md:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            void inventoryApi.createUnit({ code, name, short_name: code.slice(0, 8), factor: Number(factor) }).then(() => reload()).catch((caught) => setFormError(inventoryError(caught, "Could not add the unit.")));
          }}
        >
          <input className={control} placeholder="Code, e.g. CASE_24" value={code} onChange={(event) => setCode(event.target.value)} required />
          <input className={control} placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} required />
          <input className={control} inputMode="numeric" aria-label="Pieces per unit" value={factor} onChange={(event) => setFactor(event.target.value)} />
          <PrimaryButton type="submit" disabled={!access.online}>Add unit</PrimaryButton>
        </form>
      ) : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {formError ? <Banner tone="error">{formError}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading units…</p> : null}
      <Table headers={["Unit", "Code", "Factor", "Products"]}>
        {(data ?? []).map((unit) => (
          <tr key={unit.code}>
            <td className="px-3 py-2">{unit.name}</td>
            <td className="px-3 py-2">{unit.code}</td>
            <td className="px-3 py-2">{unit.factor}</td>
            <td className="px-3 py-2">{unit.products}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function PricingPanel(access: WorkspaceAccess) {
  const [q, setQ] = useState("");
  const { debounced, flush } = useDebouncedSearch(q);
  const [price, setPrice] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      return await inventoryApi.pricing(debounced);
    } catch {
      const products = await inventoryApi.products({ limit: 100, store_id: access.storeId, q: debounced || null });
      return { rows: products.map((product) => ({ product_id: product.id, sku: product.sku, name: product.name, retail_price_cents: product.price_cents })) };
    }
  }, [access.storeId, debounced]);
  const { data, error, loading, reload } = useResource(load, access.online);
  return (
    <section className="space-y-3">
      <PosSearchToolbar
        query={q}
        onQuery={setQ}
        placeholder="Search prices"
        onRefresh={reload}
        refreshing={loading}
        refreshDisabled={!access.online}
        onCommit={flush}
      />
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      <Table headers={["Product", "SKU", "Selling price", ""]}>
        {(data?.rows ?? []).map((row) => (
          <tr key={row.product_id}>
            <td className="px-3 py-2">{row.name}</td>
            <td className="px-3 py-2 font-mono text-xs">{row.sku}</td>
            <td className="px-3 py-2">{money(row.retail_price_cents)}</td>
            <td className="px-3 py-2">
              {access.manage || access.canPrice ? (
                <button type="button" className="font-semibold text-primary-600" onClick={() => setSelected(row.product_id)}>Change</button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
      {selected && (access.manage || access.canPrice) ? (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (!access.online) return;
            void inventoryApi.updateProduct(selected, { price_cents: cents(price) }).then(() => {
              setMessage("Selling price updated. Past sales keep the price they were rung up at.");
              setSelected(null);
              reload();
            }).catch((caught) => setMessage(inventoryError(caught, "The price was not changed.")));
          }}
        >
          <input className={`${control} max-w-xs`} aria-label="New selling price" value={price} onChange={(event) => setPrice(event.target.value)} required />
          <PrimaryButton type="submit" disabled={!access.online}>Save price</PrimaryButton>
        </form>
      ) : null}
    </section>
  );
}

export function PriceListsPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.priceLists(), []);
  const { data, error, reload } = useResource(load, access.online && access.canPrice);
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  if (!access.canPrice) return <Banner tone="info">Price lists need pricing permission.</Banner>;
  return (
    <section className="space-y-3">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void inventoryApi.createPriceList({ name, scope: "global", scope_id: null, valid_from: null, valid_to: null, priority: 0, is_active: true }).then(() => {
            setMessage("Price list created.");
            setName("");
            reload();
          }).catch((caught) => setMessage(inventoryError(caught, "Could not create the price list.")));
        }}
      >
        <input className={`${control} max-w-xs`} placeholder="Price list name" value={name} onChange={(event) => setName(event.target.value)} required />
        <PrimaryButton type="submit" disabled={!access.online}>Create list</PrimaryButton>
      </form>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      <Table headers={["List", "Scope", "Status", "From", "To"]}>
        {(data ?? []).map((list) => (
          <tr key={list.id}>
            <td className="px-3 py-2">{list.name}</td>
            <td className="px-3 py-2">{list.scope}</td>
            <td className="px-3 py-2">{list.status ?? (list.is_active ? "active" : "off")}</td>
            <td className="px-3 py-2">{list.valid_from ?? "—"}</td>
            <td className="px-3 py-2">{list.valid_to ?? "—"}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function PriceChangesPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.priceChanges(), []);
  const { data, error } = useResource(load, access.online);
  return (
    <section className="space-y-3">
      <Banner tone="info">A price change is a scheduled record. Completed sales keep the price they used.</Banner>
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Table headers={["Change", "Status", "When", "By", "Lines"]}>
        {(data ?? []).map((change) => (
          <tr key={change.id}>
            <td className="px-3 py-2">{change.name}</td>
            <td className="px-3 py-2">{change.status}</td>
            <td className="px-3 py-2">{change.run_at}</td>
            <td className="px-3 py-2">{change.created_by_name ?? "—"}</td>
            <td className="px-3 py-2">{change.lines.map((line) => `${line.sku} ${money(line.current_retail_cents)} → ${line.retail_price_cents == null ? "—" : money(line.retail_price_cents)}`).join(", ")}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function BatchesPanel({ pharmacyLots, ...access }: WorkspaceAccess & { pharmacyLots?: boolean }) {
  const load = useCallback(() => inventoryApi.batches({ store_id: access.storeId }), [access.storeId]);
  const { data, error, loading } = useResource(load, access.online);
  const [detail, setDetail] = useState<BatchDetail | null>(null);
  return (
    <section className="space-y-3">
      <Banner tone="info">
        {pharmacyLots
          ? "Manufacturer lots stay separate. Release, quarantine and recall use the lot actions, not a grocery quantity edit."
          : "Batches show the received layer, remaining quantity and expiry. Products without a batch are not given a made-up lot."}
      </Banner>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {loading ? <p className="text-sm text-zinc-500">Loading batches…</p> : null}
      <Table headers={["Batch", "Store", "Supplier", "Status", "Remaining", "Sold", ""]}>
        {(data?.rows ?? []).map((batch) => (
          <tr key={batch.id}>
            <td className="px-3 py-2">{batch.batch_number}</td>
            <td className="px-3 py-2">{batch.store_name}</td>
            <td className="px-3 py-2">{batch.supplier_name ?? "—"}</td>
            <td className="px-3 py-2">{batch.status}</td>
            <td className="px-3 py-2">{batch.units_remaining}</td>
            <td className="px-3 py-2">{batch.units_sold}</td>
            <td className="px-3 py-2">
              <button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.batch(batch.id).then(setDetail)}>Lines</button>
            </td>
          </tr>
        ))}
      </Table>
      {detail ? (
        <Drawer title={detail.batch_number} onClose={() => setDetail(null)}>
          <Table headers={["Product", "Remaining", "Expiry", "Lot", "Status"]}>
            {detail.items.map((item) => (
              <tr key={item.id}>
                <td className="px-3 py-2">{item.product_name}</td>
                <td className="px-3 py-2">{item.quantity_remaining}</td>
                <td className="px-3 py-2">{item.expiry_date ?? "—"}</td>
                <td className="px-3 py-2">{item.manufacturer_lot ?? "—"}</td>
                <td className="px-3 py-2">{item.lot_status ?? "—"}</td>
              </tr>
            ))}
          </Table>
        </Drawer>
      ) : null}
    </section>
  );
}

export function ExpiryPanel(access: WorkspaceAccess) {
  const confirm = useConfirm();
  const load = useCallback(() => inventoryApi.expiring(), []);
  const { data, error, reload } = useResource(load, access.online);
  const [message, setMessage] = useState<string | null>(null);
  return (
    <section className="space-y-3">
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      <Table headers={["Product", "Store", "Expiry", "Days", "Remaining", ""]}>
        {(data ?? []).map((row) => (
          <tr key={row.batch_item_id}>
            <td className="px-3 py-2">{row.product_name}</td>
            <td className="px-3 py-2">{row.store_code}</td>
            <td className="px-3 py-2">{row.expiry_date}</td>
            <td className="px-3 py-2">{row.days_left}</td>
            <td className="px-3 py-2">{row.quantity_remaining}</td>
            <td className="px-3 py-2">
              {access.canAdjust ? (
                <button
                  type="button"
                  className="font-semibold text-primary-600"
                  onClick={() => {
                    void confirm({ title: "Write off expired stock", message: `Remove the remaining ${row.quantity_remaining} of ${row.product_name} through the expiry ledger.`, tone: "danger" }).then((accepted) => {
                      if (!accepted || !access.online) return;
                      void inventoryApi.writeOff({ batch_item_id: row.batch_item_id }).then(() => {
                        setMessage("Expired quantity was written off through the stock ledger.");
                        reload();
                      }).catch((caught) => setMessage(inventoryError(caught, "The write-off was refused.")));
                    });
                  }}
                >
                  Write off
                </button>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function RecipesPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.recipes(), []);
  const { data, error } = useResource(load, access.online);
  return (
    <section className="space-y-3">
      <Banner tone="info">Recipes deduct ingredients when the dish is sold. Adjusting a raw material here is not a substitute for that consumption.</Banner>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {(data ?? []).map((recipe) => (
        <article key={recipe.product_id} className="rounded-xl bg-white p-3 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
          <h3 className="font-semibold">{recipe.product_name}</h3>
          <ul className="mt-2 text-sm">
            {recipe.lines.map((line) => (
              <li key={line.ingredient_name}>{line.ingredient_name}: {line.quantity}{line.sold_by_weight ? " g" : ""}</li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
}

export function ReplenishmentPanel(access: WorkspaceAccess) {
  const storeId = access.storeId;
  const load = useCallback(() => (storeId ? inventoryApi.replenishment(storeId) : Promise.resolve(null)), [storeId]);
  const { data, error, reload } = useResource(load, access.online && Boolean(storeId));
  const [message, setMessage] = useState<string | null>(null);
  if (!storeId) return <Banner tone="info">Replenishment runs for one store. This sign-in is not tied to a branch.</Banner>;
  return (
    <section className="space-y-3">
      <PrimaryButton
        disabled={!access.online}
        onClick={() => {
          void inventoryApi.runReplenishment(storeId).then(() => reload()).catch((caught) => setMessage(inventoryError(caught, "Could not calculate replenishment.")));
        }}
      >
        Calculate from current stock
      </PrimaryButton>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="info">{message}</Banner> : null}
      <Table headers={["Product", "On hand", "Suggested", "Supplier", ""]}>
        {(data?.suggestions ?? []).map((line) => (
          <tr key={line.id}>
            <td className="px-3 py-2">{line.product_name}</td>
            <td className="px-3 py-2">{line.on_hand}</td>
            <td className="px-3 py-2">{line.suggested_qty}</td>
            <td className="px-3 py-2">{line.supplier_name ?? "—"}</td>
            <td className="px-3 py-2">
              {line.status === "PENDING" && data ? (
                <button
                  type="button"
                  className="font-semibold text-primary-600"
                  onClick={() => {
                    void inventoryApi.acceptReplenishment(data.id, [{ id: line.id, quantity: line.suggested_qty }]).then(() => {
                      setMessage("Accepted through the existing replenishment service. Stock rises only when the resulting order is received.");
                      reload();
                    }).catch((caught) => setMessage(inventoryError(caught, "Could not accept the suggestion.")));
                  }}
                >
                  Accept
                </button>
              ) : line.status}
            </td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function CountsPanel(access: WorkspaceAccess) {
  const storeId = access.storeId;
  const load = useCallback(() => inventoryApi.counts(storeId), [storeId]);
  const { data, error, reload } = useResource(load, access.online);
  const [open, setOpen] = useState<CountDetail | null>(null);
  const [qty, setQty] = useState("");
  const [productId, setProductId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  return (
    <section className="space-y-3">
      {access.canAdjust && storeId ? (
        <PrimaryButton
          disabled={!access.online}
          onClick={() => {
            void inventoryApi.createCount({ store_id: storeId, blind: true, note: "Register count" }).then((count) => {
              setOpen(count);
              reload();
            }).catch((caught) => setMessage(inventoryError(caught, "Could not start a count.")));
          }}
        >
          Start stock count
        </PrimaryButton>
      ) : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {message ? <Banner tone="info">{message}</Banner> : null}
      <Table headers={["Count", "Store", "Status", ""]}>
        {(data ?? []).map((count) => (
          <tr key={count.id}>
            <td className="px-3 py-2">{count.number}</td>
            <td className="px-3 py-2">{count.store_name}</td>
            <td className="px-3 py-2">{count.status}</td>
            <td className="px-3 py-2"><button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.count(count.id).then(setOpen)}>Open</button></td>
          </tr>
        ))}
      </Table>
      {open ? (
        <Drawer title={open.number} onClose={() => setOpen(null)}>
          <p className="mb-2 text-sm">Status {open.status}. Variances post through the stock ledger when the count is approved.</p>
          <Table headers={["Product", "Counted", "Expected", "Variance"]}>
            {open.lines.map((line) => (
              <tr key={line.product_id}>
                <td className="px-3 py-2">{line.name}</td>
                <td className="px-3 py-2">{line.counted_qty ?? "—"}</td>
                <td className="px-3 py-2">{line.expected_qty ?? "Hidden"}</td>
                <td className="px-3 py-2">{line.variance ?? "—"}</td>
              </tr>
            ))}
          </Table>
          {open.status === "OPEN" ? (
            <form
              className="mt-3 space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                void inventoryApi.recordCount(open.id, [{ product_id: productId, counted_qty: Number(qty) }]).then(setOpen).catch((caught) => setMessage(inventoryError(caught, "Could not save the count.")));
              }}
            >
              <ProductSelect storeId={storeId} online={access.online} value={productId} onChange={setProductId} />
              <Field label="Counted quantity"><input className={control} inputMode="numeric" value={qty} onChange={(event) => setQty(event.target.value)} required /></Field>
              <PrimaryButton type="submit" disabled={!access.online}>Save draft line</PrimaryButton>
              <QuietButton onClick={() => void inventoryApi.submitCount(open.id).then(setOpen)}>Submit</QuietButton>
            </form>
          ) : null}
          {open.can_review && access.canAdjust ? (
            <div className="mt-3">
              <PrimaryButton disabled={!access.online} onClick={() => void inventoryApi.reviewCount(open.id, "post").then(setOpen)}>Approve and post</PrimaryButton>
            </div>
          ) : null}
        </Drawer>
      ) : null}
    </section>
  );
}

function nextLineKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `line-${Date.now()}`;
}

function DocumentLines({
  lines,
  onChange,
  storeId,
  online,
  showCost,
}: {
  lines: DraftLine[];
  onChange: (lines: DraftLine[]) => void;
  storeId: string | null;
  online: boolean;
  showCost: boolean;
}) {
  return (
    <div className="space-y-2">
      {lines.map((line) => (
        <div key={line.key} className="grid gap-2 md:grid-cols-[minmax(0,1fr)_8rem_8rem_auto]">
          <ProductSelect
            storeId={storeId}
            online={online}
            value={line.productId}
            onChange={(productId) => onChange(lines.map((item) => (item.key === line.key ? { ...item, productId } : item)))}
          />
          <input
            className={control}
            aria-label="Quantity"
            inputMode="numeric"
            value={line.quantity}
            onChange={(event) => onChange(lines.map((item) => (item.key === line.key ? { ...item, quantity: event.target.value } : item)))}
          />
          {showCost ? (
            <input
              className={control}
              aria-label="Unit cost"
              inputMode="decimal"
              value={line.cost}
              onChange={(event) => onChange(lines.map((item) => (item.key === line.key ? { ...item, cost: event.target.value } : item)))}
            />
          ) : (
            <span />
          )}
          <QuietButton onClick={() => onChange(lines.filter((item) => item.key !== line.key))} disabled={lines.length === 1}>
            Remove
          </QuietButton>
        </div>
      ))}
      <QuietButton onClick={() => onChange([...lines, blankLine(nextLineKey())])}>Add line</QuietButton>
    </div>
  );
}

export function PurchaseOrdersPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.purchaseOrders(access.storeId), [access.storeId]);
  const { data, error, reload } = useResource(load, access.online);
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [supplier, setSupplier] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>(() => [blankLine(nextLineKey())]);
  const [receipts, setReceipts] = useState<Record<string, ReceiptDraft>>({});
  const [draftQty, setDraftQty] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const storeId = access.storeId;
  const receiving = order?.status === "ordered" || order?.status === "partially_received";
  return (
    <section className="space-y-3">
      <Banner tone="info">Creating or approving an order does not increase stock. Stock moves when the goods are received. One order can hold many products.</Banner>
      {access.manage && storeId ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            setFormError(null);
            if (supplier.trim().length < 2) {
              setFormError("Enter the supplier name.");
              return;
            }
            const payload = purchaseOrderLines(lines);
            if ("error" in payload) {
              setFormError(payload.error);
              return;
            }
            void inventoryApi.createPurchaseOrder({
              supplier_name: supplier.trim(),
              destination_store_id: storeId,
              notes: notes.trim(),
              lines: payload.lines,
            }).then(() => {
              setSupplier("");
              setNotes("");
              setLines([blankLine(nextLineKey())]);
              setMessage("Draft purchase order saved.");
              reload();
            }).catch((caught) => setFormError(inventoryError(caught, "Could not create the order.")));
          }}
        >
          <div className="grid gap-2 md:grid-cols-2">
            <input className={control} placeholder="Supplier" value={supplier} onChange={(event) => setSupplier(event.target.value)} required />
            <input className={control} placeholder="Reference or note" value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>
          <DocumentLines lines={lines} onChange={setLines} storeId={storeId} online={access.online} showCost />
          <PrimaryButton type="submit" disabled={!access.online}>Create order</PrimaryButton>
        </form>
      ) : null}
      {error ? <Banner tone="error">{error}</Banner> : null}
      {formError ? <Banner tone="error">{formError}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      <Table headers={["Order", "Supplier", "Store", "Lines", "Status", ""]}>
        {(data?.rows ?? []).map((row) => (
          <tr key={row.id}>
            <td className="px-3 py-2">{row.number}</td>
            <td className="px-3 py-2">{row.supplier_name}</td>
            <td className="px-3 py-2">{row.destination_store_name}</td>
            <td className="px-3 py-2 tabular-nums">{row.lines?.length ?? 0}</td>
            <td className="px-3 py-2">{row.status}</td>
            <td className="px-3 py-2"><button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.purchaseOrder(row.id).then((next) => { setOrder(next); setReceipts({}); setDraftQty({}); })}>Open</button></td>
          </tr>
        ))}
      </Table>
      {order ? (
        <Drawer title={order.number} onClose={() => setOrder(null)}>
          <p className="mb-2 text-sm">Status {order.status}. {order.lines.length} lines.</p>
          <Table headers={["Product", "Ordered", "Received", receiving ? "Receive now" : ""]}>
            {order.lines.map((line) => {
              const outstanding = line.quantity_ordered - line.quantity_received;
              const draft = receipts[line.id] ?? { quantity: outstanding > 0 ? String(outstanding) : "0", lot: "", expiry: "" };
              return (
                <tr key={line.id}>
                  <td className="px-3 py-2">{line.name}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {order.status === "draft" ? (
                      <input
                        className={control}
                        aria-label={`Quantity for ${line.name}`}
                        inputMode="numeric"
                        value={draftQty[line.id] ?? String(line.quantity_ordered)}
                        onChange={(event) => setDraftQty({ ...draftQty, [line.id]: event.target.value })}
                      />
                    ) : line.quantity_ordered}
                  </td>
                  <td className="px-3 py-2 tabular-nums">{line.quantity_received}</td>
                  <td className="px-3 py-2">
                    {receiving && outstanding > 0 ? (
                      <div className="space-y-1">
                        <input
                          className={control}
                          aria-label={`Receive ${line.name}`}
                          inputMode="numeric"
                          value={draft.quantity}
                          onChange={(event) => setReceipts({ ...receipts, [line.id]: { ...draft, quantity: event.target.value } })}
                        />
                        {access.pharmacy && line.lot_controlled ? (
                          <>
                            <input className={control} aria-label={`Lot for ${line.name}`} placeholder="Manufacturer lot" value={draft.lot} onChange={(event) => setReceipts({ ...receipts, [line.id]: { ...draft, lot: event.target.value } })} />
                            <input className={control} aria-label={`Expiry for ${line.name}`} type="date" value={draft.expiry} onChange={(event) => setReceipts({ ...receipts, [line.id]: { ...draft, expiry: event.target.value } })} />
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </Table>
          <div className="mt-3 flex flex-wrap gap-2">
            {order.status === "draft" ? (
              <>
                <QuietButton
                  disabled={!access.online}
                  onClick={() => {
                    const lines = order.lines.map((line) => {
                      const quantity = Number(draftQty[line.id] ?? line.quantity_ordered);
                      return { product_id: line.product_id, quantity_ordered: quantity, unit_cost_cents: line.unit_cost_cents };
                    });
                    if (lines.some((line) => !Number.isInteger(line.quantity_ordered) || line.quantity_ordered < 1)) {
                      setFormError("Each line needs a whole quantity of at least 1.");
                      return;
                    }
                    void inventoryApi.updatePurchaseOrder(order.id, {
                      supplier_name: order.supplier_name,
                      destination_store_id: order.destination_store_id,
                      notes: order.notes,
                      lines,
                    }).then((next) => {
                      setOrder(next);
                      setDraftQty({});
                      setMessage("Draft purchase order updated.");
                      reload();
                    }).catch((caught) => setFormError(inventoryError(caught, "Could not update the draft.")));
                  }}
                >
                  Save draft
                </QuietButton>
                <PrimaryButton disabled={!access.online} onClick={() => void inventoryApi.placePurchaseOrder(order.id).then(setOrder)}>Submit</PrimaryButton>
              </>
            ) : null}
            {receiving ? (
              <PrimaryButton
                disabled={!access.online}
                onClick={() => {
                  const payload = receiptLines(order.lines, receipts, access.pharmacy);
                  if ("error" in payload) {
                    setFormError(payload.error);
                    return;
                  }
                  void inventoryApi.receivePurchaseOrder(order.id, { lines: payload.lines }).then((next) => {
                    setOrder(next);
                    setReceipts({});
                    setFormError(null);
                    setMessage("Goods received through the existing receiving service.");
                    reload();
                  }).catch((caught) => setFormError(inventoryError(caught, "Receiving was refused.")));
                }}
              >
                Post receipt
              </PrimaryButton>
            ) : null}
            {order.status !== "cancelled" && order.status !== "received" ? (
              <QuietButton onClick={() => void inventoryApi.cancelPurchaseOrder(order.id).then(setOrder)} disabled={!access.online}>Cancel</QuietButton>
            ) : null}
          </div>
        </Drawer>
      ) : null}
    </section>
  );
}

export function TransfersPanel(access: WorkspaceAccess) {
  const load = useCallback(() => inventoryApi.transfers(access.storeId), [access.storeId]);
  const orders = useResource(load, access.online);
  const stores = useResource(useCallback(() => inventoryApi.stores(), []), access.online);
  const [source, setSource] = useState(access.storeId ?? "");
  const [destination, setDestination] = useState("");
  const [lines, setLines] = useState<DraftLine[]>(() => [blankLine(nextLineKey())]);
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [open, setOpen] = useState<Awaited<ReturnType<typeof inventoryApi.transfer>> | null>(null);
  return (
    <section className="space-y-3">
      {access.pharmacy ? <Banner tone="info">A pharmacy transfer arrives unreleased. It cannot be sold until an authorized pharmacist releases that destination lot. Only eligible released stock can leave the source.</Banner> : null}
      {access.manage ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            setFormError(null);
            const payload = transferLines(source, destination, lines);
            if ("error" in payload) {
              setFormError(payload.error);
              return;
            }
            void inventoryApi.createTransfer({
              source_store_id: source,
              destination_store_id: destination,
              lines: payload.lines,
            }).then(() => {
              setLines([blankLine(nextLineKey())]);
              setMessage("Transfer created. Stock leaves the source when it ships and arrives when it is received.");
              orders.reload();
            }).catch((caught) => setFormError(inventoryError(caught, "Could not create the transfer.")));
          }}
        >
          <div className="grid gap-2 md:grid-cols-2">
            <select className={control} aria-label="Source store" value={source} onChange={(event) => setSource(event.target.value)}>
              {(stores.data ?? []).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
            </select>
            <select className={control} aria-label="Destination store" value={destination} onChange={(event) => setDestination(event.target.value)} required>
              <option value="">Destination</option>
              {(stores.data ?? []).map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
            </select>
          </div>
          <DocumentLines lines={lines} onChange={setLines} storeId={access.storeId} online={access.online} showCost={false} />
          <PrimaryButton type="submit" disabled={!access.online}>Create transfer</PrimaryButton>
        </form>
      ) : null}
      {orders.error ? <Banner tone="error">{orders.error}</Banner> : null}
      {formError ? <Banner tone="error">{formError}</Banner> : null}
      {message ? <Banner tone="ok">{message}</Banner> : null}
      <Table headers={["Transfer", "From", "To", "Status", ""]}>
        {(orders.data?.rows ?? []).map((transfer) => (
          <tr key={transfer.id}>
            <td className="px-3 py-2">{transfer.number}</td>
            <td className="px-3 py-2">{transfer.source_store_code}</td>
            <td className="px-3 py-2">{transfer.destination_store_code}</td>
            <td className="px-3 py-2">{transfer.status}</td>
            <td className="px-3 py-2 space-x-2">
              <button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.transfer(transfer.id).then(setOpen)}>Lines</button>
              {transfer.status === "requested" ? <button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.shipTransfer(transfer.id).then(() => orders.reload())}>Ship</button> : null}
              {transfer.status === "in_transit" ? <button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.receiveTransfer(transfer.id).then(() => orders.reload())}>Receive</button> : null}
              <button type="button" className="font-semibold text-primary-600" onClick={() => void inventoryApi.cancelTransfer(transfer.id).then(() => orders.reload()).catch((caught) => setFormError(inventoryError(caught, "This transfer can no longer be cancelled.")))}>Cancel</button>
            </td>
          </tr>
        ))}
      </Table>
      {open ? (
        <Drawer title={open.number} onClose={() => setOpen(null)}>
          <p className="mb-2 text-sm">{open.source_store_code} to {open.destination_store_code}. Status {open.status}.</p>
          <Table headers={["Product", "SKU", "Quantity"]}>
            {open.lines.map((line) => (
              <tr key={line.id}>
                <td className="px-3 py-2">{line.name}</td>
                <td className="px-3 py-2">{line.sku}</td>
                <td className="px-3 py-2 tabular-nums">{line.quantity}</td>
              </tr>
            ))}
          </Table>
        </Drawer>
      ) : null}
    </section>
  );
}

export function SerialsPanel(access: WorkspaceAccess) {
  const [q, setQ] = useState("");
  const { debounced, flush } = useDebouncedSearch(q);
  const [result, setResult] = useState<Awaited<ReturnType<typeof inventoryApi.serials>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const query = debounced.trim();
    if (query.length < 4) {
      setResult(null);
      return;
    }
    if (!access.online) return;
    let cancelled = false;
    void inventoryApi.serials(query).then((rows) => {
      if (!cancelled) setResult(rows);
    }).catch((caught) => {
      if (!cancelled) setError(inventoryError(caught, "No serial matched."));
    });
    return () => {
      cancelled = true;
    };
  }, [access.online, debounced]);
  return (
    <section className="space-y-3">
      <FilterSearch className="max-w-md" placeholder="IMEI or serial" value={q} onChange={setQ} onCommit={flush} />
      {error ? <Banner tone="error">{error}</Banner> : null}
      {result?.hint ? <Banner tone="info">{result.hint}</Banner> : null}
      <Table headers={["Identifier", "Product", "Store", "Status"]}>
        {(result?.rows ?? []).map((row) => (
          <tr key={row.id}>
            <td className="px-3 py-2 font-mono text-xs">{row.value}</td>
            <td className="px-3 py-2">{row.product_name ?? row.sku}</td>
            <td className="px-3 py-2">{row.store_code}</td>
            <td className="px-3 py-2">{row.status}</td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

export function LotsPanel({ mode, ...access }: WorkspaceAccess & { mode: string }) {
  const [lotId, setLotId] = useState("");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [productId, setProductId] = useState("");
  const [manufacturerLot, setManufacturerLot] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [events, setEvents] = useState<string | null>(null);
  async function run(work: () => Promise<unknown>, done: string) {
    if (!access.online || !access.manage) return;
    try {
      await work();
      setMessage(done);
    } catch (caught) {
      setMessage(inventoryError(caught, "The lot action was refused."));
    }
  }
  let form: ReactNode = null;
  if (mode === "release") {
    form = (
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(() => inventoryApi.releaseLot(lotId, reason), "Release was sent to the pharmacist check. A cashier permission does not release a lot."); }}>
        <Field label="Lot id"><input className={control} value={lotId} onChange={(event) => setLotId(event.target.value)} required /></Field>
        <Field label="Reason"><input className={control} value={reason} onChange={(event) => setReason(event.target.value)} required /></Field>
        <PrimaryButton type="submit" disabled={!access.online}>Release</PrimaryButton>
      </form>
    );
  } else if (mode === "quarantine") {
    form = (
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(() => inventoryApi.quarantineLot(lotId, reason), "Lot quarantined through the pharmacy service."); }}>
        <Field label="Lot id"><input className={control} value={lotId} onChange={(event) => setLotId(event.target.value)} required /></Field>
        <Field label="Reason"><input className={control} value={reason} onChange={(event) => setReason(event.target.value)} required /></Field>
        <PrimaryButton type="submit" disabled={!access.online}>Quarantine</PrimaryButton>
        <QuietButton onClick={() => void run(() => inventoryApi.clearQuarantine(lotId, reason), "Clearance was sent to the pharmacist check.")}>Clear quarantine</QuietButton>
      </form>
    );
  } else if (mode === "supplier-returns") {
    form = (
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(() => inventoryApi.supplierReturn({ reference, reason, lines: [{ batch_item_id: lotId, quantity: Number(quantity) }] }), "Supplier return recorded. That quantity cannot be sold."); }}>
        <Field label="Reference"><input className={control} value={reference} onChange={(event) => setReference(event.target.value)} required /></Field>
        <Field label="Lot id"><input className={control} value={lotId} onChange={(event) => setLotId(event.target.value)} required /></Field>
        <Field label="Quantity"><input className={control} value={quantity} onChange={(event) => setQuantity(event.target.value)} /></Field>
        <Field label="Reason"><input className={control} value={reason} onChange={(event) => setReason(event.target.value)} required /></Field>
        <PrimaryButton type="submit" disabled={!access.online}>Return to supplier</PrimaryButton>
      </form>
    );
  } else {
    form = (
      <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void run(() => inventoryApi.recall({ reference, source_text: reason, severity: "HIGH", reason, lots: [{ product_id: productId, manufacturer_lot: manufacturerLot }] }), "Recall opened. Sale and release of that lot stay blocked."); }}>
        <Field label="Reference"><input className={control} value={reference} onChange={(event) => setReference(event.target.value)} required /></Field>
        <ProductSelect storeId={access.storeId} online={access.online} value={productId} onChange={setProductId} />
        <Field label="Manufacturer lot"><input className={control} value={manufacturerLot} onChange={(event) => setManufacturerLot(event.target.value)} required /></Field>
        <Field label="Source and reason"><input className={control} value={reason} onChange={(event) => setReason(event.target.value)} required /></Field>
        <PrimaryButton type="submit" disabled={!access.online}>Open recall</PrimaryButton>
      </form>
    );
  }
  return (
    <section className="space-y-3">
      <Banner tone="info">These actions call the pharmacy lot service. They do not set a quantity on the product, and they still require the existing pharmacist authorization where the service demands it.</Banner>
      {form}
      {lotId ? (
        <QuietButton onClick={() => void inventoryApi.lotEvents(lotId).then((rows) => setEvents(rows.map((row) => `${row.created_at} ${row.action}`).join("\n"))).catch((caught) => setEvents(inventoryError(caught, "No events.")))}>
          Show lot events
        </QuietButton>
      ) : null}
      {message ? <Banner tone="info">{message}</Banner> : null}
      {events ? <pre className="whitespace-pre-wrap text-sm">{events}</pre> : null}
    </section>
  );
}
