import { useEffect, useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton } from "../../components/ui";
import { api, consoleUpload, errorText } from "../../lib/api";
import { useSession } from "../../lib/session";
import type { CatalogCategory } from "./types";

const empty = { id: "", name: "", description: "", display_order: 0, is_active: true, reason: "Catalogue update" };

export function HardwareCategoriesPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [rows, setRows] = useState<CatalogCategory[]>([]);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<typeof empty | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    api
      .get<CatalogCategory[]>("/hardware-catalog/categories")
      .then(setRows)
      .catch((caught) => setError(errorText(caught, "Categories could not be loaded.")));
  }

  useEffect(load, []);

  const visible = rows.filter((row) => row.name.toLowerCase().includes(query.trim().toLowerCase()));

  async function save() {
    if (!editing || editing.name.trim().length < 1 || editing.reason.trim().length < 3) {
      setError("Enter a category name and a short reason.");
      return;
    }
    setSaving(true);
    setError("");
    const body = {
      name: editing.name.trim(),
      description: editing.description,
      display_order: Number(editing.display_order) || 0,
      is_active: editing.is_active,
      reason: editing.reason.trim(),
    };
    try {
      if (editing.id) await api.put(`/hardware-catalog/categories/${editing.id}`, body);
      else await api.post("/hardware-catalog/categories", body);
      setEditing(null);
      load();
    } catch (caught) {
      setError(errorText(caught, "The category could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Categories"
        description="Groups on the public hardware page."
        controls={admin ? <PrimaryButton onClick={() => setEditing({ ...empty })}>New category</PrimaryButton> : null}
      />
      <ErrorNote message={error} />
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search categories"
        aria-label="Search categories"
        className="mb-4 h-10 w-full max-w-sm rounded-xl border border-line px-3 text-sm"
      />
      <ul className="divide-y divide-line rounded-2xl border border-line bg-card">
        {visible.map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            {row.thumb_url ? <img src={row.thumb_url} alt="" className="h-12 w-12 rounded-lg object-cover" /> : null}
            <div className="min-w-0 flex-1">
              <p className="font-medium text-charcoal">{row.name}</p>
              <p className="text-sm text-charcoal/60">{row.is_active ? "Active" : "Inactive"} · order {row.display_order}</p>
            </div>
            {admin ? (
              <GhostButton
                onClick={() =>
                  setEditing({
                    id: row.id,
                    name: row.name,
                    description: row.description,
                    display_order: row.display_order,
                    is_active: row.is_active,
                    reason: "Catalogue update",
                  })
                }
              >
                Edit
              </GhostButton>
            ) : null}
          </li>
        ))}
        {visible.length === 0 ? <li className="px-4 py-8 text-sm text-charcoal/60">No categories yet.</li> : null}
      </ul>
      {editing ? (
        <Modal
          title={editing.id ? "Edit category" : "New category"}
          onClose={() => setEditing(null)}
          footer={
            <>
              <GhostButton onClick={() => setEditing(null)}>Cancel</GhostButton>
              <PrimaryButton loading={saving} onClick={save}>
                Save
              </PrimaryButton>
            </>
          }
        >
          <div className="space-y-3">
            <Field label="Name" value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} required />
            <Field label="Description" multiline value={editing.description} onChange={(event) => setEditing({ ...editing, description: event.target.value })} />
            <Field label="Display order" value={String(editing.display_order)} onChange={(event) => setEditing({ ...editing, display_order: Number(event.target.value) || 0 })} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} />
              Active on the website
            </label>
            <Field label="Reason" value={editing.reason} onChange={(event) => setEditing({ ...editing, reason: event.target.value })} required />
            {editing.id ? (
              <label className="block text-sm">
                Category image
                <input
                  className="mt-1 block text-sm"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={async (event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    try {
                      await consoleUpload(`/hardware-catalog/categories/${editing.id}/image`, file, { reason: editing.reason || "Catalogue update" });
                      load();
                    } catch (caught) {
                      setError(errorText(caught, "The image could not be uploaded."));
                    }
                  }}
                />
              </label>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
