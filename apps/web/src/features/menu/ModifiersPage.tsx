import { formatMoney, type ModifierGroup, type ModifierGroupInput, type Product } from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { ChefHat, Copy, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";

interface OptionDraft {
  id?: string;
  name: string;
  price: string;
  is_default: boolean;
}

function toCents(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return 0;
  if (!/^-?\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

function GroupModal({
  group,
  products,
  groups,
  onClose,
  onSaved,
}: {
  group: ModifierGroup | null;
  products: Product[];
  groups: ModifierGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(group?.name ?? "");
  const [min, setMin] = useState(String(group?.min_select ?? 0));
  const [max, setMax] = useState(String(group?.max_select ?? 1));
  const [options, setOptions] = useState<OptionDraft[]>(
    group?.options
      .filter((option) => option.is_active)
      .map((option) => ({ id: option.id, name: option.name, price: (option.price_delta_cents / 100).toFixed(2), is_default: option.is_default })) ?? [
      { name: "", price: "", is_default: false },
    ],
  );
  const [linked, setLinked] = useState<Set<string>>(new Set(group?.product_ids ?? []));
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return products
      .filter((product) => !product.is_serialized && !product.sold_by_weight)
      .filter((product) => needle === "" || `${product.name} ${product.sku}`.toLowerCase().includes(needle))
      .slice(0, 60);
  }, [products, filter]);

  async function save() {
    const priced = options.map((option) => ({ ...option, cents: toCents(option.price) }));
    if (name.trim() === "") return setError("Name the group, e.g. Milk or Size.");
    if (priced.some((option) => option.name.trim() === "")) return setError("Every option needs a name.");
    if (priced.some((option) => option.cents === null)) return setError("Enter option prices like 2.50 or -1.00.");
    const body: ModifierGroupInput = {
      name: name.trim(),
      min_select: Number(min) || 0,
      max_select: Math.max(1, Number(max) || 1),
      options: priced.map((option) => ({
        ...(option.id ? { id: option.id } : {}),
        name: option.name.trim(),
        price_delta_cents: option.cents ?? 0,
        is_default: option.is_default,
      })),
    };
    setBusy(true);
    setError(null);
    try {
      const saved = group
        ? await apiPut<ModifierGroup>(`/api/v1/menu/modifier-groups/${group.id}`, body)
        : await apiPost<ModifierGroup>("/api/v1/menu/modifier-groups", body);
      // Product links are stored per product: recompute each changed product's ordered group list.
      const before = new Set(group?.product_ids ?? []);
      const changed = [...new Set([...before, ...linked])].filter((id) => before.has(id) !== linked.has(id));
      for (const productId of changed) {
        const current = groups.filter((item) => item.id !== saved.id && item.product_ids?.includes(productId)).map((item) => item.id);
        await apiPut(`/api/v1/menu/products/${productId}/modifier-groups`, {
          group_ids: linked.has(productId) ? [...current, saved.id] : current,
        });
      }
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the modifier group."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={group ? `Edit ${group.name}` : "New modifier group"}
      subtitle="Options the cashier picks when ringing up an item, each with its own price change."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save group"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label="Group name" value={name} placeholder="Milk" onChange={(event) => setName(event.target.value)} />
        <TextField label="Must pick at least" type="number" min={0} value={min} hint="0 = optional" onChange={(event) => setMin(event.target.value)} />
        <TextField label="Can pick up to" type="number" min={1} value={max} onChange={(event) => setMax(event.target.value)} />
      </div>

      <h3 className="mb-2 mt-6 text-sm font-semibold">Options</h3>
      <div className="space-y-2">
        {options.map((option, index) => (
          <div key={option.id ?? `new-${index}`} className="grid grid-cols-[1fr_120px_auto_auto] items-end gap-2">
            <TextField
              label={index === 0 ? "Option" : ""}
              value={option.name}
              placeholder="Oat milk"
              onChange={(event) => setOptions(options.map((item, at) => (at === index ? { ...item, name: event.target.value } : item)))}
            />
            <TextField
              label={index === 0 ? "Price change" : ""}
              inputMode="decimal"
              value={option.price}
              placeholder="0.00"
              onChange={(event) => setOptions(options.map((item, at) => (at === index ? { ...item, price: event.target.value } : item)))}
            />
            <label className="mb-3 flex items-center gap-1.5 text-xs font-medium text-charcoal/70">
              <input
                type="checkbox"
                checked={option.is_default}
                onChange={(event) =>
                  setOptions(options.map((item, at) => (at === index ? { ...item, is_default: event.target.checked } : item)))
                }
                className="h-4 w-4 accent-accent"
              />
              Default
            </label>
            <button
              type="button"
              aria-label={`Remove ${option.name || "option"}`}
              disabled={options.length === 1}
              onClick={() => setOptions(options.filter((_, at) => at !== index))}
              className={`mb-2 flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 disabled:opacity-30 ${actionHoverClass("danger")}`}
            >
              <Trash2 size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setOptions([...options, { name: "", price: "", is_default: false }])}
        className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-accent"
      >
        <Plus size={15} aria-hidden="true" /> Add option
      </button>

      <h3 className="mb-2 mt-6 text-sm font-semibold">Offered on</h3>
      <TextField label="Find products" value={filter} placeholder="Search by name or SKU" onChange={(event) => setFilter(event.target.value)} />
      <div className="mt-2 grid max-h-56 gap-1 overflow-y-auto rounded-2xl border border-line p-2 sm:grid-cols-2">
        {visible.map((product) => (
          <label key={product.id} className="flex items-center gap-2 rounded-xl px-2 py-1.5 text-sm hover:bg-surface">
            <input
              type="checkbox"
              checked={linked.has(product.id)}
              onChange={(event) => {
                const next = new Set(linked);
                if (event.target.checked) next.add(product.id);
                else next.delete(product.id);
                setLinked(next);
              }}
              className="h-4 w-4 accent-accent"
            />
            <span className="min-w-0 truncate">{product.name}</span>
          </label>
        ))}
      </div>
      <div className="mt-6 rounded-2xl border border-line bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">POS preview</p>
        <p className="mt-1 text-base font-semibold">{name.trim() || "Modifier group"}</p>
        <p className="text-xs text-charcoal/60">
          {Number(min) > 0 ? "Required" : "Optional"}
          {Math.max(1, Number(max) || 1) === 1 ? " · one choice" : ` · up to ${Math.max(1, Number(max) || 1)}`}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {options
            .filter((option) => option.name.trim() !== "")
            .map((option, index) => (
              <span key={option.id ?? index} className="inline-flex min-h-11 items-center rounded-2xl border border-line bg-white px-3 text-sm font-semibold">
                {option.name.trim()}
                {option.is_default ? " · default" : ""}
                {option.price && option.price !== "0" && option.price !== "0.00" ? ` · ${option.price}` : ""}
              </span>
            ))}
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

interface ModifierTemplate {
  key: string;
  name: string;
  min_select: number;
  max_select: number;
  options: string[];
  present: boolean;
}

function groupPayload(group: ModifierGroup, active = group.is_active): ModifierGroupInput {
  return {
    name: group.name,
    min_select: group.min_select,
    max_select: group.max_select,
    position: group.position,
    is_active: active,
    options: group.options
      .filter((option) => option.is_active)
      .map((option) => ({
        id: option.id,
        name: option.name,
        price_delta_cents: option.price_delta_cents,
        is_default: option.is_default,
        is_active: true,
      })),
  };
}

/** Menu modifiers: groups of options (size, milk, extras) and the menu items that offer them. */
export function ModifiersPage() {
  const { currency } = useCurrency();
  const [groups, setGroups] = useState<ModifierGroup[] | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [editing, setEditing] = useState<ModifierGroup | "new" | null>(null);
  const [templates, setTemplates] = useState<ModifierTemplate[]>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextGroups, nextProducts, nextTemplates] = await Promise.all([
        apiGet<ModifierGroup[]>("/api/v1/menu/modifier-groups"),
        apiGet<Product[]>("/api/v1/products?limit=500"),
        apiGet<ModifierTemplate[]>("/api/v1/menu/modifier-templates"),
      ]);
      setGroups(nextGroups);
      setProducts(nextProducts);
      setTemplates(nextTemplates);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the menu."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const names = new Map(products.map((product) => [product.id, product.name]));

  async function toggle(group: ModifierGroup) {
    setBusyId(group.id);
    try {
      await apiPut(`/api/v1/menu/modifier-groups/${group.id}`, groupPayload(group, !group.is_active));
      await load();
    } catch (caught) {
      setError(message(caught, "Could not update the group."));
    } finally {
      setBusyId(null);
    }
  }

  async function copy(group: ModifierGroup) {
    setBusyId(group.id);
    try {
      await apiPost(`/api/v1/menu/modifier-groups/${group.id}/duplicate`, {});
      await load();
    } catch (caught) {
      setError(message(caught, "Could not copy the group."));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(group: ModifierGroup) {
    const linked = (group.product_ids ?? []).length;
    const confirmed = linked
      ? window.confirm(`${group.name} is offered on ${linked} product${linked === 1 ? "" : "s"}. Remove those links and delete the group?`)
      : window.confirm(`Delete ${group.name}? Past sales keep the choices already printed.`);
    if (!confirmed) return;
    setBusyId(group.id);
    try {
      await apiDelete(`/api/v1/menu/modifier-groups/${group.id}${linked ? "?detach=true" : ""}`);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not delete the group."));
    } finally {
      setBusyId(null);
    }
  }

  async function addTemplate(key: string) {
    setBusyId(key);
    try {
      await apiPost("/api/v1/menu/modifier-groups/from-template", { key });
      await load();
    } catch (caught) {
      setError(message(caught, "Could not add that template."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
              <ChefHat size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Menu modifiers</h2>
              <p className="text-sm text-charcoal/60">Sizes, milk choices and add-ons. Registers price them at the till and offline.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <GhostButton onClick={() => setShowTemplates(true)}>Add from template</GhostButton>
            <PrimaryButton onClick={() => setEditing("new")}>New group</PrimaryButton>
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(groups ?? []).map((group) => {
            const activeOptions = group.options.filter((option) => option.is_active);
            return (
            <article
              key={group.id}
              className={`rounded-2xl border p-4 text-left ${group.is_active ? "border-line" : "border-dashed border-line opacity-70"}`}
            >
              <span className="flex items-baseline justify-between gap-2">
                <span className="font-semibold">{group.name}</span>
                <span className="text-xs text-charcoal/50">
                  {group.is_active ? "Active" : "Inactive"} · {group.max_select === 1 ? "Single" : "Multiple"} ·{" "}
                  {group.min_select > 0 ? "Required" : "Optional"} · {activeOptions.length} options
                </span>
              </span>
              <span className="mt-2 flex flex-wrap gap-1.5">
                {group.options
                  .filter((option) => option.is_active)
                  .map((option) => (
                    <span key={option.id} className="rounded-full bg-surface px-2 py-0.5 text-xs tabular-nums">
                      {option.name}
                      {option.price_delta_cents ? ` ${option.price_delta_cents > 0 ? "+" : "−"}${formatMoney(Math.abs(option.price_delta_cents), currency)}` : ""}
                    </span>
                  ))}
              </span>
              <span className="mt-3 block truncate text-xs text-charcoal/50">
                {(group.product_ids ?? []).length === 0
                  ? "Not offered on any item yet"
                  : (group.product_ids ?? []).map((id) => names.get(id) ?? "Item").join(", ")}
              </span>
              <span className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={busyId === group.id} onClick={() => setEditing(group)} className={`rounded-full px-3 py-1 text-xs font-semibold ${actionHoverClass("primary")}`}>
                  Edit
                </button>
                <button type="button" disabled={busyId === group.id} onClick={() => void copy(group)} className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${actionHoverClass("info")}`}>
                  <Copy size={12} aria-hidden="true" /> Copy
                </button>
                <button type="button" disabled={busyId === group.id} onClick={() => void toggle(group)} className={`rounded-full px-3 py-1 text-xs font-semibold ${actionHoverClass("warning")}`}>
                  {group.is_active ? "Deactivate" : "Activate"}
                </button>
                <button type="button" disabled={busyId === group.id} onClick={() => void remove(group)} className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${actionHoverClass("danger")}`}>
                  <Trash2 size={12} aria-hidden="true" /> Delete
                </button>
              </span>
            </article>
            );
          })}
        </div>
        {groups !== null && groups.length === 0 ? (
          <p className="py-6 text-sm text-charcoal/60">
            Every default group has been removed. Add one back from a template, or create your own.
          </p>
        ) : null}
      </div>
      {showTemplates ? (
        <Modal title="Add a template" subtitle="Starter groups for this business. Prices stay at zero until you set them." onClose={() => setShowTemplates(false)}>
          <div className="space-y-2">
            {templates.map((template) => (
              <div key={template.key} className="flex items-center justify-between gap-3 rounded-2xl border border-line px-3 py-3">
                <div>
                  <p className="font-semibold">{template.name}</p>
                  <p className="text-xs text-charcoal/60">
                    {template.max_select === 1 ? "Single" : "Multiple"} · {template.min_select > 0 ? "Required" : "Optional"} · {template.options.join(", ")}
                  </p>
                </div>
                <GhostButton disabled={template.present || busyId === template.key} onClick={() => void addTemplate(template.key)}>
                  {template.present ? "Added" : "Add"}
                </GhostButton>
              </div>
            ))}
          </div>
        </Modal>
      ) : null}
      {editing ? (
        <GroupModal
          group={editing === "new" ? null : editing}
          products={products}
          groups={groups ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      ) : null}
    </section>
  );
}
