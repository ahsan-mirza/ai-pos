import { Permission, type Category, type SubCategory } from "@ai-pos/shared-types";
import { ChevronRight, FolderPlus, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useAuth } from "../../lib/auth";
import { useAutoCode } from "../../lib/codes";
import { categoriesApi, message } from "./api";
import { CatalogDrilldown, type CatalogPath } from "./CatalogDrilldown";
import { useCategories } from "./shared";
import { IconButton } from "./StockPage";

type Editing =
  | { kind: "category"; category: Category | null }
  | { kind: "sub"; category: Category; sub: SubCategory | null }
  | null;

export function CategoriesPage() {
  const { can, user } = useAuth();
  const { categories, setCategories, error: loadError, reload } = useCategories();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drill, setDrill] = useState<({ subId: string } & CatalogPath) | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [error, setError] = useState<string | null>(null);
  const manage = can(Permission.PortalInventoryManage) && user?.store_id === null;
  const confirm = useConfirm();
  const selected = categories.find((item) => item.id === selectedId) ?? categories[0];
  const drillSub = drill ? selected?.sub_categories.find((sub) => sub.id === drill.subId) : undefined;

  const replace = (next: Category) => {
    setCategories((current) => {
      const exists = current.some((item) => item.id === next.id);
      const merged = exists ? current.map((item) => (item.id === next.id ? next : item)) : [...current, next];
      return merged.sort((a, b) => a.name.localeCompare(b.name));
    });
    setSelectedId(next.id);
    setEditing(null);
  };

  const removeCategory = async (category: Category) => {
    const accepted = await confirm({
      title: "Delete category",
      message: `Delete ${category.name} and its sub-categories?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await categoriesApi.remove(category.id);
      setSelectedId(null);
      await reload();
    } catch (caught) {
      setError(message(caught, "Could not delete the category."));
    }
  };

  const removeSub = async (sub: SubCategory) => {
    const accepted = await confirm({
      title: "Delete sub-category",
      message: `Delete the ${sub.name} sub-category?`,
      confirmLabel: "Delete",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await categoriesApi.removeSub(sub.id);
      await reload();
    } catch (caught) {
      setError(message(caught, "Could not delete the sub-category."));
    }
  };

  const subColumns: DataTableColumn<SubCategory>[] = [
    { id: "code", header: "Code", width: 110, className: "font-mono text-xs text-charcoal/60", accessorKey: "code" },
    {
      id: "name",
      header: "Sub-category",
      cell: (sub) => (
        <>
          <span className="block font-semibold group-hover:text-accent">{sub.name}</span>
          <span className="block max-w-[360px] truncate text-xs text-charcoal/50">{sub.description || "—"}</span>
        </>
      ),
    },
    { id: "products", header: "Products", align: "right", className: "font-semibold", accessorKey: "product_count" },
    {
      id: "drill",
      header: <span className="sr-only">Brands & models</span>,
      align: "right",
      cell: () => (
        <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold text-charcoal/50 group-hover:text-accent">
          Brands & models <ChevronRight size={14} aria-hidden="true" />
        </span>
      ),
    },
    ...(manage && selected
      ? [
          {
            id: "actions",
            header: <span className="sr-only">Actions</span>,
            align: "right" as const,
            width: 96,
            cell: (sub: SubCategory) => (
              <div className="flex justify-end gap-1">
                <IconButton label="Edit sub-category" onClick={() => setEditing({ kind: "sub", category: selected, sub })}>
                  <Pencil size={14} />
                </IconButton>
                <IconButton label="Delete sub-category" onClick={() => void removeSub(sub)}>
                  <Trash2 size={14} />
                </IconButton>
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <section className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="rounded-card bg-charcoal p-5 text-white">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Categories</h2>
          {manage ? (
            <button
              type="button"
              onClick={() => setEditing({ kind: "category", category: null })}
              className="inline-flex h-9 items-center gap-1 rounded-full bg-accent px-3 text-sm font-semibold"
            >
              <Plus size={15} aria-hidden="true" /> New
            </button>
          ) : null}
        </div>
        <ul className="space-y-2">
          {categories.map((category) => {
            const active = selected?.id === category.id;
            return (
              <li key={category.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(category.id);
                    setDrill(null);
                  }}
                  className={`w-full rounded-2xl p-3 text-left transition ${active ? "bg-accent" : "bg-white/5 hover:bg-white/10"}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">{category.name}</span>
                    <span className="font-mono text-[11px] text-white/60">{category.code}</span>
                  </span>
                  <span className={`mt-1 block text-xs tabular-nums ${active ? "text-white/80" : "text-white/50"}`}>
                    {category.sub_categories.length} sub-categories · {category.product_count} products
                  </span>
                </button>
              </li>
            );
          })}
          {categories.length === 0 ? <li className="text-sm text-white/60">No categories yet.</li> : null}
        </ul>
      </aside>

      <div className="rounded-card border border-line bg-white p-6">
        <ErrorNote message={error ?? loadError} />
        {selected && drillSub && drill ? (
          <CatalogDrilldown
            key={drillSub.id}
            category={selected}
            sub={drillSub}
            path={drill}
            manage={manage}
            onNavigate={(path) => setDrill({ subId: drillSub.id, ...path })}
            onExit={() => setDrill(null)}
          />
        ) : selected ? (
          <>
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-mono text-xs text-charcoal/50">{selected.code}</p>
                <h2 className="text-2xl font-semibold">{selected.name}</h2>
                <p className="text-sm text-charcoal/60">{selected.description || "No description."}</p>
              </div>
              {manage ? (
                <div className="flex gap-2">
                  <GhostButton onClick={() => setEditing({ kind: "category", category: selected })}>Edit</GhostButton>
                  <GhostButton onClick={() => void removeCategory(selected)}>Delete</GhostButton>
                  <PrimaryButton onClick={() => setEditing({ kind: "sub", category: selected, sub: null })}>
                    <span className="inline-flex items-center gap-2">
                      <FolderPlus size={16} aria-hidden="true" /> Add sub-category
                    </span>
                  </PrimaryButton>
                </div>
              ) : null}
            </div>
            <DataTable
              aria-label={`${selected.name} sub-categories`}
              columns={subColumns}
              data={selected.sub_categories}
              getRowId={(sub) => sub.id}
              onRowClick={(sub) => setDrill({ subId: sub.id })}
              rowClassName={() => "group"}
              emptyState={{ icon: FolderPlus, title: `No sub-categories under ${selected.name} yet` }}
              pagination={{ mode: "client", pageSize: 10, resetKey: selected.id }}
            />
          </>
        ) : (
          <p className="text-sm text-charcoal/60">Create a category to start organising the catalog.</p>
        )}
        {!manage ? (
          <p className="mt-6 text-xs text-charcoal/50">Categories are shared by every branch; a Super Admin manages them.</p>
        ) : null}
      </div>

      {editing ? <CategoryModal editing={editing} onClose={() => setEditing(null)} onSaved={replace} /> : null}
    </section>
  );
}

function CategoryModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: NonNullable<Editing>;
  onClose: () => void;
  onSaved: (category: Category) => void;
}) {
  const current = editing.kind === "category" ? editing.category : editing.sub;
  const [name, setName] = useState(current?.name ?? "");
  const { code, setCode } = useAutoCode(name, current?.code ?? "");
  const [description, setDescription] = useState(current?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isSub = editing.kind === "sub";

  const save = async () => {
    if (name.trim().length < 2) return setError("Names need at least 2 characters.");
    setBusy(true);
    setError(null);
    const body = { name: name.trim(), code: code.replace(/-$/, "") || null, description: description.trim() };
    try {
      if (editing.kind === "category") {
        onSaved(editing.category ? await categoriesApi.update(editing.category.id, body) : await categoriesApi.create(body));
      } else {
        onSaved(
          editing.sub
            ? await categoriesApi.updateSub(editing.sub.id, body)
            : await categoriesApi.createSub(editing.category.id, body),
        );
      }
    } catch (caught) {
      setError(message(caught, "Could not save."));
    } finally {
      setBusy(false);
    }
  };

  const title = `${current ? "Edit" : "New"} ${isSub ? "sub-category" : "category"}`;
  return (
    <Modal
      title={title}
      subtitle={isSub ? `Under ${editing.category.name}` : "Top-level catalog group, e.g. Computers or Audio."}
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
        <TextField
          label="Name"
          value={name}
          autoFocus
          placeholder={isSub ? "e.g. Laptops" : "e.g. Computers"}
          onChange={(event) => setName(event.target.value)}
        />
        <TextField
          label="Code"
          value={code}
          placeholder={isSub ? "LAPTOPS" : "COMPUTERS"}
          className="font-mono"
          maxLength={32}
          spellCheck={false}
          autoComplete="off"
          hint="Optional. Letters, digits and dashes; generated from the name if empty."
          onChange={(event) => setCode(event.target.value)}
        />
        <TextField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
