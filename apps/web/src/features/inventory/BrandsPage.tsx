import { Permission, type Brand } from "@ai-pos/shared-types";
import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, TextField, filterLabel } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { useAutoCode } from "../../lib/codes";
import { brandsApi, message } from "./api";
import { useBrands, useCategories } from "./shared";
import { IconButton } from "./StockPage";

/** Global brand list; each brand shows the sub-categories it sells in. */
export function BrandsPage() {
  const { can, user } = useAuth();
  const manage = can(Permission.PortalInventoryManage) && user?.store_id === null;
  const confirm = useConfirm();
  const { brands, error: loadError, reload } = useBrands();
  const { categories } = useCategories();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Brand | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const subNames = useMemo(() => {
    const names = new Map<string, string>();
    for (const category of categories) {
      for (const sub of category.sub_categories) names.set(sub.id, `${category.name} › ${sub.name}`);
    }
    return names;
  }, [categories]);

  const needle = query.trim().toLowerCase();
  const visible = brands.filter((brand) => needle === "" || `${brand.name} ${brand.code}`.toLowerCase().includes(needle));

  const remove = async (brand: Brand) => {
    const accepted = await confirm({
      title: "Delete brand",
      message: `Delete the ${brand.name} brand?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await brandsApi.remove(brand.id);
      await reload();
    } catch (caught) {
      setError(message(caught, "Could not delete the brand."));
    }
  };

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <h2 className="text-2xl font-semibold">Brands</h2>
            <p className="text-sm text-charcoal/60">One list for the whole catalog. Add models from Categories › sub-category.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="w-64">
            <span className={filterLabel}>Search</span>
            <span className="relative block">
              <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-charcoal/40" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Brand or code"
                className="h-11 w-full rounded-full border border-line bg-white pl-10 pr-4 text-sm font-medium text-charcoal placeholder:font-normal placeholder:text-charcoal/40 hover:border-gray-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
            </span>
          </label>
          {manage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <span className="inline-flex items-center gap-2">
                <Plus size={16} aria-hidden="true" /> New brand
              </span>
            </PrimaryButton>
          ) : null}
        </div>
      </div>
      <ErrorNote message={error ?? loadError} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-3 font-medium">Brand</th>
              <th className="pb-3 font-medium">Sold in</th>
              <th className="pb-3 text-right font-medium">Models</th>
              <th className="pb-3 text-right font-medium">Products</th>
              {manage ? <th className="pb-3 text-right font-medium">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {visible.map((brand) => (
              <tr key={brand.id} className="border-t border-line align-top">
                <td className="py-3">
                  <span className="block font-medium">{brand.name}</span>
                  <span className="block font-mono text-[11px] text-charcoal/50">{brand.code}</span>
                </td>
                <td className="py-3">
                  <div className="flex flex-wrap gap-1.5">
                    {brand.sub_category_ids.map((id) => (
                      <span key={id} className="rounded-full bg-surface px-2.5 py-0.5 text-xs text-charcoal/80">
                        {subNames.get(id) ?? "…"}
                      </span>
                    ))}
                    {brand.sub_category_ids.length === 0 ? <span className="text-charcoal/40">—</span> : null}
                  </div>
                </td>
                <td className="py-3 text-right tabular-nums">{brand.model_count}</td>
                <td className="py-3 text-right tabular-nums">{brand.product_count}</td>
                {manage ? (
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      <IconButton label={`Edit ${brand.name}`} onClick={() => setEditing(brand)}>
                        <Pencil size={14} />
                      </IconButton>
                      <IconButton label={`Delete ${brand.name}`} onClick={() => void remove(brand)}>
                        <Trash2 size={14} />
                      </IconButton>
                    </div>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No brands match.</p> : null}
      </div>
      {editing !== null ? (
        <BrandModal
          brand={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await reload();
          }}
        />
      ) : null}
    </section>
  );
}

function BrandModal({ brand, onClose, onSaved }: { brand: Brand | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(brand?.name ?? "");
  const { code, setCode } = useAutoCode(name, brand?.code ?? "");
  const [description, setDescription] = useState(brand?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (name.trim().length < 2) return setError("Names need at least 2 characters.");
    const body = { name: name.trim(), code: code.replace(/-$/, "") || null, description: description.trim() };
    setBusy(true);
    setError(null);
    try {
      if (brand) await brandsApi.update(brand.id, body);
      else await brandsApi.create(body);
      await onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the brand."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={brand ? `Edit ${brand.name}` : "New brand"}
      subtitle="Link it to sub-categories from Categories › sub-category › Add brand."
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
        <TextField label="Name" value={name} autoFocus placeholder="e.g. OnePlus" onChange={(event) => setName(event.target.value)} />
        <TextField
          label="Code"
          value={code}
          className="font-mono"
          maxLength={32}
          hint="Optional. Generated from the name if empty."
          onChange={(event) => setCode(event.target.value)}
        />
        <TextField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
