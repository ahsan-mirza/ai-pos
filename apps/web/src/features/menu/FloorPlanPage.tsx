import type { DiningArea, DiningTable, Floor } from "@ai-pos/shared-types";
import { DiningTableShape, tableFootprint } from "@ai-pos/ui";
import { LayoutGrid, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { message } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";

const CELL = 44;
const COLS = 20;
const ROWS = 12;
const PREVIEW_CELL = 34;

type TableDraft = Pick<DiningTable, "label" | "seats" | "shape" | "x" | "y" | "w" | "h" | "is_active">;

/** Floor plan editor: dining areas and their tables on a grid; registers show live table status on the same plan. */
export function FloorPlanPage() {
  const { user } = useAuth();
  const { stores } = useStores();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [floor, setFloor] = useState<Floor | null>(null);
  const [areaId, setAreaId] = useState<string | null>(null);
  const [selected, setSelected] = useState<DiningTable | null>(null);
  const [draft, setDraft] = useState<TableDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const drag = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const [dragPos, setDragPos] = useState<{ id: string; x: number; y: number } | null>(null);

  useEffect(() => {
    if (storeId === "" && stores.length > 0) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [stores, storeId]);

  const load = useCallback(async () => {
    if (storeId === "") return;
    try {
      const next = await apiGet<Floor>(`/api/v1/dining/floor?store_id=${storeId}`);
      setFloor(next);
      setAreaId((current) => (current && next.areas.some((area) => area.id === current) ? current : (next.areas[0]?.id ?? null)));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the floor plan."));
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const area: DiningArea | null = floor?.areas.find((item) => item.id === areaId) ?? null;
  // The side panel is ~240px wide: long tables shrink to fit their preview.
  const previewCell = draft ? Math.min(PREVIEW_CELL, Math.floor(240 / draft.w)) : PREVIEW_CELL;

  async function run(action: () => Promise<Floor>) {
    setBusy(true);
    setError(null);
    try {
      setFloor(await action());
    } catch (caught) {
      setError(message(caught, "Could not save the floor plan."));
    } finally {
      setBusy(false);
    }
  }

  async function addArea() {
    const name = window.prompt("Name the dining area", floor?.areas.length ? "Terrace" : "Main room");
    if (!name?.trim()) return;
    await run(() => apiPost<Floor>("/api/v1/dining/areas", { store_id: storeId, name: name.trim(), position: floor?.areas.length ?? 0 }));
  }

  function freeCell(): { x: number; y: number } {
    const taken = (x: number, y: number) =>
      area?.tables.some((table) => x < table.x + table.w && x + 2 > table.x && y < table.y + table.h && y + 2 > table.y) ?? false;
    for (let y = 0; y < ROWS - 1; y += 2) for (let x = 0; x < COLS - 1; x += 2) if (!taken(x, y)) return { x, y };
    return { x: 0, y: 0 };
  }

  async function addTable() {
    if (!area) return;
    const label = `T${(area.tables.length + 1).toString()}`;
    const cell = freeCell();
    await run(() =>
      apiPost<Floor>("/api/v1/dining/tables", { area_id: area.id, label, seats: 4, shape: "square", ...cell, w: 2, h: 2 }),
    );
  }

  async function saveTable(table: DiningTable, changes: Partial<TableDraft>) {
    const body = { area_id: table.area_id, label: table.label, seats: table.seats, shape: table.shape, x: table.x, y: table.y, w: table.w, h: table.h, is_active: table.is_active, ...changes };
    await run(() => apiPut<Floor>(`/api/v1/dining/tables/${table.id}`, body));
  }

  function onPointerDown(event: React.PointerEvent, table: DiningTable) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    drag.current = { id: table.id, dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    setSelected(table);
    setDraft({ label: table.label, seats: table.seats, shape: table.shape, x: table.x, y: table.y, w: table.w, h: table.h, is_active: table.is_active });
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const grid = event.currentTarget.getBoundingClientRect();
    const x = Math.round((event.clientX - grid.left - drag.current.dx) / CELL);
    const y = Math.round((event.clientY - grid.top - drag.current.dy) / CELL);
    setDragPos({ id: drag.current.id, x: Math.max(0, Math.min(COLS - 1, x)), y: Math.max(0, Math.min(ROWS - 1, y)) });
  }

  function onPointerUp() {
    const moved = dragPos;
    const table = area?.tables.find((item) => item.id === drag.current?.id);
    drag.current = null;
    setDragPos(null);
    if (moved && table && (moved.x !== table.x || moved.y !== table.y)) void saveTable(table, { x: moved.x, y: moved.y });
  }

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
              <LayoutGrid size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Floor plan</h2>
              <p className="text-sm text-charcoal/60">Drag tables into place. Registers show them live: free, seated, ordered, bill.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <SelectField label="Store" value={storeId} disabled={user?.store_id != null} options={storeOptions(stores)} onChange={setStoreId} />
            <GhostButton disabled={busy || storeId === ""} onClick={() => void addArea()}>
              <Plus size={15} aria-hidden="true" /> Area
            </GhostButton>
            <PrimaryButton disabled={busy || !area} onClick={() => void addTable()}>
              <Plus size={15} aria-hidden="true" /> Table
            </PrimaryButton>
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="mb-3 flex flex-wrap gap-1.5">
          {(floor?.areas ?? []).map((item) => (
            <button key={item.id} type="button" aria-pressed={item.id === areaId} onClick={() => setAreaId(item.id)}
              className={`h-9 rounded-full px-4 text-sm font-semibold ${item.id === areaId ? "bg-accent text-white" : "bg-surface"}`}>
              {item.name} <span className="font-normal opacity-70">· {item.tables.length}</span>
            </button>
          ))}
          {floor && floor.areas.length === 0 ? <p className="text-sm text-charcoal/60">Add a dining area to start, e.g. Main room or Terrace.</p> : null}
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
          <div className="overflow-auto rounded-2xl border border-line bg-surface p-2">
            <div
              role="application"
              aria-label="Floor plan grid"
              className="relative"
              style={{
                width: COLS * CELL,
                height: ROWS * CELL,
                backgroundImage: "linear-gradient(to right, rgba(0,0,0,.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(0,0,0,.06) 1px, transparent 1px)",
                backgroundSize: `${CELL}px ${CELL}px`,
              }}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            >
              {(area?.tables ?? []).map((table) => {
                const position = dragPos?.id === table.id ? dragPos : table;
                return (
                  <div
                    key={table.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Table ${table.label}, ${table.seats} seats`}
                    onPointerDown={(event) => onPointerDown(event, table)}
                    className={`group absolute cursor-grab touch-none select-none rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                      table.is_active ? "" : "opacity-40"
                    }`}
                    style={{ left: position.x * CELL + 2, top: position.y * CELL + 2, width: table.w * CELL - 4, height: table.h * CELL - 4 }}
                  >
                    <DiningTableShape
                      shape={table.shape}
                      seats={table.seats}
                      width={table.w * CELL - 4}
                      height={table.h * CELL - 4}
                      topClassName={`border-2 bg-white shadow-sm transition-colors ${
                        selected?.id === table.id ? "border-accent bg-accent/5" : "border-charcoal/25 group-hover:border-charcoal/40"
                      }`}
                      chairClassName={selected?.id === table.id ? "bg-accent/45" : "bg-charcoal/25"}
                    >
                      <span className="text-sm font-bold leading-tight">{table.label}</span>
                      <span className="text-[10px] leading-tight text-charcoal/60">{table.seats} seats</span>
                    </DiningTableShape>
                  </div>
                );
              })}
            </div>
          </div>

          <aside className="rounded-2xl border border-line p-4">
            {selected && draft ? (
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveTable(selected, draft);
                }}
              >
                <h3 className="font-semibold">Table {selected.label}</h3>
                <div className="relative mx-auto" style={{ width: draft.w * previewCell, height: draft.h * previewCell }} aria-hidden="true">
                  <DiningTableShape
                    shape={draft.shape}
                    seats={draft.seats}
                    width={draft.w * previewCell}
                    height={draft.h * previewCell}
                    topClassName="border-2 border-accent bg-accent/5"
                    chairClassName="bg-accent/45"
                  >
                    <span className="text-sm font-bold">{draft.label || "?"}</span>
                    <span className="text-[10px] text-charcoal/60">{draft.seats} seats</span>
                  </DiningTableShape>
                </div>
                <TextField label="Label" value={draft.label} maxLength={16} onChange={(event) => setDraft({ ...draft, label: event.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <TextField
                    label="Seats"
                    type="number"
                    min={1}
                    max={24}
                    value={String(draft.seats)}
                    onChange={(event) => {
                      const seats = Math.min(24, Math.max(1, Number(event.target.value) || 1));
                      setDraft({ ...draft, seats, ...tableFootprint(draft.shape, seats) });
                    }}
                  />
                  <SelectField<DiningTable["shape"]>
                    label="Shape"
                    value={draft.shape}
                    options={[
                      { value: "square", label: "Square" },
                      { value: "round", label: "Round" },
                      { value: "rect", label: "Long" },
                    ]}
                    onChange={(shape) => setDraft({ ...draft, shape, ...tableFootprint(shape, draft.seats) })}
                  />
                  <TextField label="Width (cells)" type="number" min={1} value={String(draft.w)} onChange={(event) => setDraft({ ...draft, w: Number(event.target.value) || 1 })} />
                  <TextField label="Depth (cells)" type="number" min={1} value={String(draft.h)} onChange={(event) => setDraft({ ...draft, h: Number(event.target.value) || 1 })} />
                </div>
                <Toggle label="In use" description="Retired tables stay in history but leave the register's plan." checked={draft.is_active} onChange={(is_active) => setDraft({ ...draft, is_active })} />
                <PrimaryButton type="submit" disabled={busy}>
                  Save table
                </PrimaryButton>
              </form>
            ) : (
              <p className="text-sm text-charcoal/60">Select a table to rename it, change its seats or shape. Drag to move.</p>
            )}
          </aside>
        </div>
      </div>
    </section>
  );
}
