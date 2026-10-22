import type { Category, KitchenStation, KitchenStationInput } from "@ai-pos/shared-types";
import { ChefHat, ExternalLink, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { message } from "../customers/api";
import { categoriesApi } from "../inventory/api";
import { storeOptions, useStores } from "../inventory/shared";

type Draft = Omit<KitchenStationInput, "store_id">;

const EMPTY: Draft = { name: "", category_ids: [], is_default: false, print_tickets: false, position: 0, is_active: true };

/** Kitchen and bar stations: which categories fire to each screen, and which also print a ticket. */
export function KitchenStationsPage() {
  const { user } = useAuth();
  const { stores } = useStores();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [stations, setStations] = useState<KitchenStation[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (storeId === "" && stores.length > 0) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [stores, storeId]);

  useEffect(() => {
    categoriesApi
      .list()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  const load = useCallback(async () => {
    if (storeId === "") return;
    try {
      setStations(await apiGet<KitchenStation[]>(`/api/v1/kds/stations?store_id=${storeId}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the kitchen stations."));
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  function edit(station: KitchenStation | null) {
    if (station === null) {
      setEditing("new");
      setDraft({ ...EMPTY, is_default: stations.length === 0, position: stations.length });
      return;
    }
    setEditing(station.id);
    setDraft({
      name: station.name,
      category_ids: station.category_ids,
      is_default: station.is_default,
      print_tickets: station.print_tickets,
      position: station.position,
      is_active: station.is_active,
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body = { ...draft, store_id: storeId, name: draft.name.trim() };
      if (editing === "new") await apiPost<KitchenStation>("/api/v1/kds/stations", body);
      else if (editing) await apiPut<KitchenStation>(`/api/v1/kds/stations/${editing}`, body);
      setEditing(null);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not save the station."));
    } finally {
      setBusy(false);
    }
  }

  function toggleCategory(id: string, on: boolean) {
    setDraft((current) => ({
      ...current,
      category_ids: on ? [...current.category_ids, id] : current.category_ids.filter((item) => item !== id),
    }));
  }

  const claimedBy = (categoryId: string) =>
    stations.find((station) => station.id !== editing && station.category_ids.includes(categoryId))?.name;
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? "Removed category";

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <ChefHat size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-xl font-semibold">Kitchen stations</h2>
            <p className="text-sm text-charcoal/60">
              Sent orders fire to the station that lists the item&apos;s category, or to the default station.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <SelectField label="Store" value={storeId} disabled={user?.store_id != null} options={storeOptions(stores)} onChange={setStoreId} />
          <PrimaryButton disabled={busy || storeId === ""} onClick={() => edit(null)}>
            <Plus size={15} aria-hidden="true" /> Station
          </PrimaryButton>
        </div>
      </div>
      <ErrorNote message={error} />

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-2">
          {stations.length === 0 ? (
            <p className="rounded-2xl bg-surface p-5 text-sm text-charcoal/60">
              No stations yet. Add a Kitchen station (default) and, if you have one, a Bar station for drinks.
            </p>
          ) : null}
          {stations.map((station) => (
            <div key={station.id} className={`flex flex-wrap items-center gap-3 rounded-2xl border border-line p-4 ${station.is_active ? "" : "opacity-50"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {station.name}
                  {station.is_default ? <span className="ml-2 rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent">default</span> : null}
                  {station.print_tickets ? <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-xs">prints</span> : null}
                </p>
                <p className="truncate text-xs text-charcoal/60">
                  {station.category_ids.length > 0 ? station.category_ids.map(categoryName).join(", ") : "No categories of its own"}
                </p>
              </div>
              <a
                href={`/kds/${station.id}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm hover:bg-surface"
              >
                <ExternalLink size={14} aria-hidden="true" /> Open screen
              </a>
              <GhostButton onClick={() => edit(station)}>Edit</GhostButton>
            </div>
          ))}
          <p className="pt-2 text-xs text-charcoal/60">
            To run a screen, add a register for it under Registers, issue an activation key, and enter the key on the
            screen at <span className="font-mono">/kds</span>.
          </p>
        </div>

        {editing ? (
          <form
            className="space-y-3 rounded-2xl border border-line p-4"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <h3 className="font-semibold">{editing === "new" ? "New station" : `Edit ${draft.name}`}</h3>
            <TextField label="Name" value={draft.name} maxLength={40} required onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            <fieldset>
              <legend className="mb-1.5 text-sm font-medium">Categories</legend>
              <div className="max-h-56 space-y-1 overflow-auto rounded-xl border border-line p-2">
                {categories.map((category) => {
                  const other = claimedBy(category.id);
                  return (
                    <label key={category.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.category_ids.includes(category.id)}
                        onChange={(event) => toggleCategory(category.id, event.target.checked)}
                      />
                      {category.name}
                      {other ? <span className="text-xs text-charcoal/50">(also {other})</span> : null}
                    </label>
                  );
                })}
                {categories.length === 0 ? <p className="text-xs text-charcoal/60">No categories yet.</p> : null}
              </div>
            </fieldset>
            <Toggle label="Default station" description="Takes every item whose category no station lists." checked={draft.is_default} onChange={(is_default) => setDraft({ ...draft, is_default })} />
            <Toggle label="Print tickets" description="The register that sends the order also prints this station's ticket." checked={draft.print_tickets} onChange={(print_tickets) => setDraft({ ...draft, print_tickets })} />
            <Toggle label="In use" checked={draft.is_active} onChange={(is_active) => setDraft({ ...draft, is_active })} />
            <div className="flex gap-2">
              <PrimaryButton type="submit" disabled={busy || draft.name.trim() === ""}>
                Save station
              </PrimaryButton>
              <GhostButton onClick={() => setEditing(null)}>Cancel</GhostButton>
            </div>
          </form>
        ) : null}
      </div>
    </section>
  );
}
