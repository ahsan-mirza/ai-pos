import {
  formatMoney,
  Permission,
  PRICE_LIST_SCOPE_LABELS,
  PRICE_TIER_LABELS,
  PAYMENT_TERMS_LABELS,
  type Customer,
  type CustomerGroup,
  type PaymentTerms,
  type PriceList,
  type PriceListRow,
  type PriceListScope,
  type PriceListStatus,
  type PriceTier,
} from "@ai-pos/shared-types";
import { ArrowLeft, Download, Plus, Tags, Trash2, Upload, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ProductPicker } from "../../components/ui/ProductPicker";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { customersApi } from "../customers/api";
import { errorMessage } from "../users/api";
import { priceListsApi } from "./priceListsApi";
import { formatDate, storeOptions, useStores } from "./shared";

const STATUS_TONE: Record<PriceListStatus, string> = {
  active: "bg-accent text-white",
  scheduled: "bg-charcoal text-white",
  expired: "bg-surface text-charcoal/50 ring-1 ring-line",
  off: "bg-white text-charcoal/50 ring-1 ring-line",
};

function ListStatus({ status }: { status: PriceListStatus }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ${STATUS_TONE[status]}`}>{status}</span>;
}

/** <input type="datetime-local"> value for an ISO time, and back. */
function toLocal(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function fromLocal(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

const percent = (bps: number | null) => (bps === null ? "" : String(bps / 100));

export function PriceListsPage() {
  const { can } = useAuth();
  const [lists, setLists] = useState<PriceListRow[] | null>(null);
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [editing, setEditing] = useState<PriceListRow | "new" | null>(null);
  const [editingGroup, setEditingGroup] = useState<CustomerGroup | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const manage = can(Permission.PortalPricingManage);

  const load = useCallback(async () => {
    try {
      const [rows, found] = await Promise.all([priceListsApi.list(), priceListsApi.groups()]);
      setLists(rows);
      setGroups(found);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load price lists."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (openId) {
    return (
      <ListEditor
        listId={openId}
        manage={manage}
        groups={groups}
        onBack={() => {
          setOpenId(null);
          void load();
        }}
      />
    );
  }

  const listColumns: DataTableColumn<PriceListRow>[] = [
    { id: "name", header: "Price list", cell: (row) => <span className="font-medium">{row.name}</span> },
    {
      id: "scope",
      header: "Applies to",
      cell: (row) => (
        <>
          <span className="block">{row.scope_name ?? PRICE_LIST_SCOPE_LABELS[row.scope]}</span>
          <span className="block text-xs text-charcoal/50">{PRICE_LIST_SCOPE_LABELS[row.scope]}</span>
        </>
      ),
    },
    { id: "items", header: "Products", align: "right", cell: (row) => row.items },
    {
      id: "window",
      header: "Valid",
      className: "pl-6",
      cell: (row) =>
        row.valid_from || row.valid_to
          ? `${row.valid_from ? formatDate(row.valid_from) : "now"} → ${row.valid_to ? formatDate(row.valid_to) : "open"}`
          : "Always",
    },
    { id: "priority", header: "Priority", align: "right", cell: (row) => row.priority },
    { id: "status", header: "Status", className: "pl-6", cell: (row) => <ListStatus status={row.status} /> },
  ];

  const groupColumns: DataTableColumn<CustomerGroup>[] = [
    { id: "name", header: "Group", cell: (row) => <span className="font-medium">{row.name}</span> },
    { id: "tier", header: "Default tier", cell: (row) => (row.default_tier ? PRICE_TIER_LABELS[row.default_tier] : "—") },
    {
      id: "discount",
      header: "Blanket discount",
      align: "right",
      cell: (row) => (row.default_discount_bps ? `${row.default_discount_bps / 100}%` : "—"),
    },
    { id: "terms", header: "Terms", cell: (row) => (row.payment_terms ? PAYMENT_TERMS_LABELS[row.payment_terms] : "—") },
    { id: "members", header: "Members", align: "right", cell: (row) => row.members },
    { id: "lists", header: "Lists", align: "right", cell: (row) => row.price_lists },
  ];

  return (
    <section className="space-y-4">
      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end justify-between gap-3 p-6 pb-5">
          <div>
            <h2 className="text-xl font-semibold">Price lists</h2>
            <p className="text-sm text-charcoal/60">
              Contract prices for a customer, a group, a branch or the whole business. The lowest valid price wins at
              the till; registers carry the lists offline.
            </p>
          </div>
          {manage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> New price list
            </PrimaryButton>
          ) : null}
          {error ? (
            <div className="w-full">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
        <DataTable
          aria-label="Price lists"
          variant="flush"
          minWidth="820px"
          columns={listColumns}
          data={lists ?? []}
          getRowId={(row) => row.id}
          onRowClick={(row) => setOpenId(row.id)}
          isLoading={lists === null && error === null}
          emptyState={{ icon: Tags, title: "No price lists yet" }}
        />
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end justify-between gap-3 p-6 pb-5">
          <div>
            <h2 className="text-xl font-semibold">Customer groups</h2>
            <p className="text-sm text-charcoal/60">Group dealers or contract customers for a shared tier, discount and price lists.</p>
          </div>
          {manage ? (
            <GhostButton onClick={() => setEditingGroup("new")}>
              <Plus size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> New group
            </GhostButton>
          ) : null}
        </div>
        <DataTable
          aria-label="Customer groups"
          variant="flush"
          minWidth="760px"
          columns={groupColumns}
          data={groups}
          getRowId={(row) => row.id}
          onRowClick={manage ? (row) => setEditingGroup(row) : undefined}
          emptyState={{ icon: Users, title: "No customer groups" }}
        />
      </div>

      {editing ? (
        <ListModal
          initial={editing === "new" ? null : editing}
          groups={groups}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            setToast(`${saved.name} saved.`);
            setOpenId(saved.id);
          }}
        />
      ) : null}
      {editingGroup ? (
        <GroupModal
          initial={editingGroup === "new" ? null : editingGroup}
          onClose={() => setEditingGroup(null)}
          onSaved={(saved) => {
            setEditingGroup(null);
            setToast(`Group ${saved.name} saved.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function ListModal({
  initial,
  groups,
  onClose,
  onSaved,
}: {
  initial: PriceListRow | null;
  groups: CustomerGroup[];
  onClose: () => void;
  onSaved: (list: PriceList) => void;
}) {
  const { stores } = useStores();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [name, setName] = useState(initial?.name ?? "");
  const [scope, setScope] = useState<PriceListScope>(initial?.scope ?? "global");
  const [target, setTarget] = useState(initial?.scope_id ?? "");
  const [from, setFrom] = useState(toLocal(initial?.valid_from ?? null));
  const [to, setTo] = useState(toLocal(initial?.valid_to ?? null));
  const [priority, setPriority] = useState(String(initial?.priority ?? 0));
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (scope === "customer" && customers.length === 0) {
      void customersApi.list({}).then(setCustomers).catch(() => undefined);
    }
  }, [scope, customers.length]);

  const targets =
    scope === "customer"
      ? customers.map((row) => ({ value: row.id, label: row.company_name || row.name, hint: row.code }))
      : scope === "group"
        ? groups.map((row) => ({ value: row.id, label: row.name }))
        : scope === "store"
          ? storeOptions(stores)
          : [];

  const save = async () => {
    if (!name.trim()) return setError("Name the price list.");
    if (scope !== "global" && !target) return setError(`Choose the ${scope}.`);
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      scope,
      scope_id: scope === "global" ? null : target,
      valid_from: fromLocal(from),
      valid_to: fromLocal(to),
      priority: Number(priority) || 0,
      is_active: active,
    };
    try {
      onSaved(initial ? await priceListsApi.update(initial.id, body) : await priceListsApi.create(body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the price list."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={initial ? `Edit ${initial.name}` : "New price list"}
      subtitle="Leave the dates empty for a list that always applies."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        <SelectField
          label="Applies to"
          value={scope}
          options={(Object.keys(PRICE_LIST_SCOPE_LABELS) as PriceListScope[]).map((value) => ({
            value,
            label: PRICE_LIST_SCOPE_LABELS[value],
          }))}
          onChange={(value) => {
            setScope(value);
            setTarget("");
          }}
        />
        {scope === "global" ? null : (
          <SelectField label={scope === "store" ? "Branch" : scope === "group" ? "Group" : "Customer"} value={target} placeholder="Choose…" options={targets} onChange={setTarget} />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Valid from" type="datetime-local" value={from} onChange={(event) => setFrom(event.target.value)} />
          <TextField label="Valid until" type="datetime-local" value={to} onChange={(event) => setTo(event.target.value)} />
        </div>
        <TextField
          label="Priority"
          inputMode="numeric"
          value={priority}
          hint="Breaks ties between lists of the same kind that offer the same price."
          onChange={(event) => setPriority(event.target.value.replace(/[^\d-]/g, ""))}
        />
        <Toggle checked={active} onChange={setActive} label="Active" description="Inactive lists are kept but never priced." />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function GroupModal({
  initial,
  onClose,
  onSaved,
}: {
  initial: CustomerGroup | null;
  onClose: () => void;
  onSaved: (group: CustomerGroup) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [tier, setTier] = useState<PriceTier | "">(initial?.default_tier ?? "");
  const [discount, setDiscount] = useState(percent(initial?.default_discount_bps || null));
  const [terms, setTerms] = useState<PaymentTerms | "">(initial?.payment_terms ?? "");
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      default_tier: tier || null,
      default_discount_bps: Math.round((Number(discount) || 0) * 100),
      payment_terms: terms || null,
      is_active: active,
    };
    try {
      onSaved(initial ? await priceListsApi.updateGroup(initial.id, body) : await priceListsApi.createGroup(body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the group."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={initial ? `Edit ${initial.name}` : "New customer group"}
      subtitle="Assign customers to a group on their customer record."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || !name.trim()} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
        <SelectField
          label="Default tier"
          hint="For members who have no tier of their own, on wholesale sales."
          value={tier}
          options={[{ value: "", label: "None" }, ...(Object.keys(PRICE_TIER_LABELS) as PriceTier[]).map((value) => ({ value, label: PRICE_TIER_LABELS[value] }))]}
          onChange={setTier}
        />
        <TextField
          label="Blanket discount (%)"
          inputMode="decimal"
          value={discount}
          hint="Off the tier price on every product; specific price lists still win when lower."
          onChange={(event) => setDiscount(event.target.value.replace(/[^\d.]/g, ""))}
        />
        <SelectField
          label="Payment terms"
          value={terms}
          options={[{ value: "", label: "Customer's own" }, ...(Object.keys(PAYMENT_TERMS_LABELS) as PaymentTerms[]).map((value) => ({ value, label: PAYMENT_TERMS_LABELS[value] }))]}
          onChange={setTerms}
        />
        <Toggle checked={active} onChange={setActive} label="Active" />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

interface DraftItem {
  product_id: string;
  sku: string;
  name: string;
  retail: number;
  mode: "price" | "discount";
  value: string;
  min_qty: string;
}

function ListEditor({
  listId,
  manage,
  groups,
  onBack,
}: {
  listId: string;
  manage: boolean;
  groups: CustomerGroup[];
  onBack: () => void;
}) {
  const { currency } = useCurrency();
  const [list, setList] = useState<PriceList | null>(null);
  const [draft, setDraft] = useState<DraftItem[]>([]);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const confirm = useConfirm();

  const adopt = (next: PriceList) => {
    setList(next);
    setDraft(
      next.lines.map((line) => ({
        product_id: line.product_id,
        sku: line.sku,
        name: line.name,
        retail: line.retail_price_cents,
        mode: line.price_cents !== null ? "price" : "discount",
        value: line.price_cents !== null ? (line.price_cents / 100).toFixed(2) : percent(line.discount_bps),
        min_qty: String(line.min_qty),
      })),
    );
    setDirty(false);
  };

  const load = useCallback(async () => {
    try {
      adopt(await priceListsApi.get(listId));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load the price list."));
    }
  }, [listId]);

  useEffect(() => {
    void load();
  }, [load]);

  const change = (index: number, patch: Partial<DraftItem>) => {
    setDraft((current) => current.map((row, at) => (at === index ? { ...row, ...patch } : row)));
    setDirty(true);
  };

  const save = async () => {
    const items = [];
    for (const row of draft) {
      const value = Number(row.value);
      if (!row.value.trim() || !Number.isFinite(value) || value < 0) return setError(`${row.name}: enter a price or a discount.`);
      items.push({
        product_id: row.product_id,
        price_cents: row.mode === "price" ? Math.round(value * 100) : null,
        discount_bps: row.mode === "discount" ? Math.round(value * 100) : null,
        min_qty: Math.max(1, Number(row.min_qty) || 1),
        volume_breaks: [],
      });
    }
    setBusy(true);
    try {
      adopt(await priceListsApi.putItems(listId, items));
      setError(null);
      setToast(`${items.length} prices saved.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the prices."));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!list) return;
    const accepted = await confirm({
      title: "Delete price list",
      message: `Delete ${list.name}? Its prices stop applying straight away.`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await priceListsApi.remove(list.id);
      onBack();
    } catch (caught) {
      setError(errorMessage(caught, "Could not delete the list."));
    }
  };

  return (
    <section className="space-y-4">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-medium text-charcoal/60 hover:text-accent">
        <ArrowLeft size={15} aria-hidden="true" /> All price lists
      </button>
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex flex-wrap items-center gap-3 text-xl font-semibold">
              {list?.name ?? "…"} {list ? <ListStatus status={list.status} /> : null}
            </h2>
            {list ? (
              <p className="text-sm text-charcoal/60">
                {list.scope_name ? `${list.scope_name} · ` : ""}
                {PRICE_LIST_SCOPE_LABELS[list.scope]} · {list.currency}
              </p>
            ) : null}
          </div>
          {list ? (
            <div className="flex flex-wrap gap-2">
              <GhostButton onClick={() => void priceListsApi.exportCsv(list.id, list.name).catch((caught: unknown) => setError(errorMessage(caught, "Export failed.")))}>
                <Download size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> CSV
              </GhostButton>
              {manage ? (
                <>
                  <GhostButton onClick={() => setImporting(true)}>
                    <Upload size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Import
                  </GhostButton>
                  <GhostButton onClick={() => setEditing(true)}>Settings</GhostButton>
                  <button
                    type="button"
                    aria-label="Delete list"
                    onClick={() => void remove()}
                    className="flex h-10 w-10 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                  <PrimaryButton disabled={busy || !dirty} onClick={() => void save()}>
                    {busy ? "Saving…" : "Save prices"}
                  </PrimaryButton>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
        <ErrorNote message={error} />
        {manage ? (
          <div className="mb-4 max-w-md">
            <ProductPicker
              onPick={(hit) => {
                if (draft.some((row) => row.product_id === hit.product.id)) return;
                setDraft((current) => [
                  ...current,
                  {
                    product_id: hit.product.id,
                    sku: hit.product.sku,
                    name: hit.product.name,
                    retail: hit.product.price_cents,
                    mode: "price",
                    value: (hit.product.price_cents / 100).toFixed(2),
                    min_qty: "1",
                  },
                ]);
                setDirty(true);
              }}
            />
          </div>
        ) : null}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Product</th>
                <th className="pb-3 text-right font-medium">Retail</th>
                <th className="pb-3 pl-6 font-medium">Price as</th>
                <th className="pb-3 text-right font-medium">Value</th>
                <th className="pb-3 text-right font-medium">From qty</th>
                <th className="pb-3" />
              </tr>
            </thead>
            <tbody>
              {draft.map((row, index) => (
                <tr key={row.product_id} className="border-t border-line">
                  <td className="py-2.5">
                    <span className="block font-medium">{row.name}</span>
                    <span className="block font-mono text-xs text-charcoal/50">{row.sku}</span>
                  </td>
                  <td className="py-2.5 text-right tabular-nums text-charcoal/60">{formatMoney(row.retail, currency)}</td>
                  <td className="py-2.5 pl-6">
                    <select
                      aria-label={`How ${row.name} is priced`}
                      disabled={!manage}
                      value={row.mode}
                      onChange={(event) => change(index, { mode: event.target.value as DraftItem["mode"], value: "" })}
                      className="rounded-xl border border-line bg-surface px-3 py-1.5 text-sm"
                    >
                      <option value="price">Fixed price</option>
                      <option value="discount">% off tier price</option>
                    </select>
                  </td>
                  <td className="py-2.5 text-right">
                    <input
                      aria-label={`${row.name} ${row.mode === "price" ? "price" : "discount"}`}
                      disabled={!manage}
                      inputMode="decimal"
                      value={row.value}
                      onChange={(event) => change(index, { value: event.target.value.replace(/[^\d.]/g, "") })}
                      className="w-28 rounded-xl border border-line bg-surface px-3 py-1.5 text-right tabular-nums focus:border-accent focus:outline-none"
                    />
                  </td>
                  <td className="py-2.5 text-right">
                    <input
                      aria-label={`${row.name} minimum quantity`}
                      disabled={!manage}
                      inputMode="numeric"
                      value={row.min_qty}
                      onChange={(event) => change(index, { min_qty: event.target.value.replace(/[^\d]/g, "") })}
                      className="w-20 rounded-xl border border-line bg-surface px-3 py-1.5 text-right tabular-nums focus:border-accent focus:outline-none"
                    />
                  </td>
                  <td className="py-2.5 pl-2 text-right">
                    {manage ? (
                      <button
                        type="button"
                        aria-label={`Remove ${row.name}`}
                        onClick={() => {
                          setDraft((current) => current.filter((_, at) => at !== index));
                          setDirty(true);
                        }}
                        className="text-charcoal/40 hover:text-accent"
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {list && draft.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No products on this list yet.</p> : null}
        </div>
      </div>
      {editing && list ? (
        <ListModal
          initial={list}
          groups={groups}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            adopt(saved);
            setToast("List settings saved.");
          }}
        />
      ) : null}
      {importing && list ? (
        <ImportModal
          listId={list.id}
          onClose={() => setImporting(false)}
          onDone={(message) => {
            setImporting(false);
            setToast(message);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function ImportModal({ listId, onClose, onDone }: { listId: string; onClose: () => void; onDone: (message: string) => void }) {
  const [csv, setCsv] = useState("");
  const [replace, setReplace] = useState(false);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await priceListsApi.importCsv(listId, csv, replace);
      if (result.skipped.length) setSkipped(result.skipped);
      else onDone(`${result.imported} prices imported.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not import the file."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      width="lg"
      title="Import prices from CSV"
      subtitle="Columns: sku, then price (e.g. 12.50) or discount_percent, and optionally min_qty."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>{skipped.length ? "Done" : "Cancel"}</GhostButton>
          <PrimaryButton disabled={busy || !csv.trim()} onClick={() => void run()}>
            {busy ? "Importing…" : "Import"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void file.text().then(setCsv);
          }}
          className="block text-sm"
        />
        <textarea
          aria-label="CSV"
          rows={8}
          value={csv}
          onChange={(event) => setCsv(event.target.value)}
          placeholder={"sku,price,min_qty\nACC-CABLE-USBC,12.50,10"}
          className="w-full rounded-xl border border-transparent bg-surface px-4 py-3 font-mono text-xs focus:border-accent focus:bg-white focus:outline-none"
        />
        <Toggle checked={replace} onChange={setReplace} label="Replace the list" description="Remove products the file does not mention." />
        {skipped.length ? (
          <ul className="max-h-40 overflow-y-auto rounded-2xl bg-surface px-4 py-3 text-xs text-charcoal/70">
            {skipped.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
