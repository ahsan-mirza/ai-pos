import { useMemo, useState, type ReactNode } from "react";
import { floorCounts, matchesFloorFilter, type FloorFilter, type FloorMatch } from "./floorStatus";

export const floorTableGridClass = "grid grid-cols-[repeat(auto-fill,minmax(156px,1fr))] gap-2";

const FILTERS: { id: FloorFilter; label: string; tone: string }[] = [
  { id: "all", label: "All", tone: "var(--table-card-ink)" },
  { id: "available", label: "Available", tone: "var(--table-available-line)" },
  { id: "occupied", label: "Occupied", tone: "var(--table-occupied-line)" },
  { id: "preparing", label: "Preparing", tone: "var(--table-preparing-line)" },
  { id: "partial", label: "Partially ready", tone: "var(--table-partial-line)" },
  { id: "ready", label: "Ready", tone: "var(--table-ready-line)" },
  { id: "served", label: "Served", tone: "var(--table-served-line)" },
  { id: "payment", label: "Payment", tone: "var(--table-payment-line)" },
  { id: "out", label: "Out of service", tone: "var(--table-out-line)" },
];

export interface FloorSection {
  id: string;
  name: string;
}

/** Scrollable light floor: section chips, status filters, search, and a width-based card grid. */
export function FloorBoard<T extends FloorMatch>({
  sections,
  items,
  renderItem,
  empty = "No tables on this floor.",
  showSections = true,
}: {
  sections: FloorSection[];
  items: T[];
  renderItem: (item: T) => ReactNode;
  empty?: string;
  /** When the parent row already shows sections, the board does not repeat them. */
  showSections?: boolean;
}) {
  const [sectionId, setSectionId] = useState("all");
  const [filter, setFilter] = useState<FloorFilter>("all");
  const [query, setQuery] = useState("");
  const section = showSections && sections.some((item) => item.id === sectionId) ? sectionId : "all";
  const inSection = useMemo(
    () => (section === "all" ? items : items.filter((item) => item.areaId === section)),
    [items, section],
  );
  const counts = useMemo(() => floorCounts(inSection), [inSection]);
  const needle = query.trim().toLowerCase();
  const visible = inSection.filter(
    (item) => matchesFloorFilter(filter, item) && (needle === "" || item.search.toLowerCase().includes(needle)),
  );

  return (
    <div className="flex min-h-0 min-w-0 flex-col gap-2">
      <div className="flex w-full min-w-0 flex-nowrap items-center justify-start gap-3 overflow-hidden" data-testid="table-toolbar">
        {showSections ? (
          <div className="flex max-w-[46%] shrink-0 items-center gap-2 overflow-x-auto whitespace-nowrap" role="group" aria-label="Floor">
            <FilterChip pressed={section === "all"} onClick={() => setSectionId("all")}>
              All sections
            </FilterChip>
            {sections.map((item) => (
              <FilterChip key={item.id} pressed={section === item.id} onClick={() => setSectionId(item.id)}>
                {item.name}
              </FilterChip>
            ))}
          </div>
        ) : null}
        <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto whitespace-nowrap" role="group" aria-label="Table summary">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-pressed={filter === item.id}
              onClick={() => setFilter(item.id)}
              className={`inline-flex h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-xs font-semibold ${
                filter === item.id ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--table-card-line)] bg-[var(--table-card-bg)]"
              }`}
              style={filter === item.id ? undefined : { color: "var(--table-card-ink)" }}
            >
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: item.tone }} aria-hidden="true" />
              {item.label}
              <span className="tabular-nums">{counts[item.id]}</span>
            </button>
          ))}
        </div>
        <label className="w-36 shrink-0 sm:w-44">
          <span className="sr-only">Search tables or orders</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Table or order"
            className="h-11 w-full rounded-full border border-[var(--table-card-line)] bg-[var(--table-card-bg)] px-3 text-xs text-[var(--table-card-ink)] placeholder:text-[var(--table-card-muted)] focus:border-[var(--primary)] focus:outline-none"
          />
        </label>
      </div>
      {visible.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--table-card-muted)" }}>
          {empty}
        </p>
      ) : (
        <div
          className={`overflow-x-hidden rounded-2xl border border-[var(--table-card-line)] p-2 ${floorTableGridClass}`}
          style={{ background: "var(--table-floor-bg)" }}
          aria-label="Tables"
        >
          {visible.map((item) => (
            <div key={item.key} className="min-w-0">
              {renderItem(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`h-10 shrink-0 rounded-full px-3 text-xs font-semibold ${
        pressed ? "bg-[var(--primary)] text-white" : "bg-[var(--table-card-bg)] text-[var(--table-card-ink)]"
      }`}
    >
      {children}
    </button>
  );
}
