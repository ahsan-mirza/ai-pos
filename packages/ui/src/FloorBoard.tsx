import { Search, X } from "lucide-react";
import { useMemo, useRef, useState, type MouseEvent, type PointerEvent, type ReactNode } from "react";
import { floorCounts, matchesFloorFilter, type FloorFilter, type FloorMatch } from "./floorStatus";
import { useLocale } from "./LocaleSwitch";

export const floorTableGridClass = "grid grid-cols-[repeat(auto-fill,minmax(156px,1fr))] gap-2";

const FILTERS: { id: FloorFilter; label: string; tone: string; active: string }[] = [
  { id: "all", label: "All", tone: "var(--primary)", active: "border-transparent bg-primary text-white" },
  { id: "available", label: "Available", tone: "var(--table-available-line)", active: "border-transparent bg-emerald-600 text-white" },
  { id: "occupied", label: "Occupied", tone: "var(--table-occupied-line)", active: "border-transparent bg-violet-600 text-white" },
  { id: "preparing", label: "Preparing", tone: "var(--primary)", active: "border-transparent bg-orange-500 text-white" },
  { id: "partial", label: "Partially ready", tone: "var(--table-partial-line)", active: "border-transparent bg-[var(--table-partial-line)] text-white" },
  { id: "ready", label: "Ready", tone: "var(--table-ready-line)", active: "border-transparent bg-[var(--table-ready-line)] text-white" },
  { id: "served", label: "Served", tone: "var(--table-served-line)", active: "border-transparent bg-[var(--table-served-line)] text-white" },
  { id: "payment", label: "Payment", tone: "var(--table-payment-line)", active: "border-transparent bg-[var(--table-payment-line)] text-white" },
  { id: "out", label: "Out of service", tone: "var(--table-out-line)", active: "border-transparent bg-[var(--table-out-line)] text-white" },
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
  const { t } = useLocale();
  const sectionScroll = useDragScroll();
  const statusScroll = useDragScroll();
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
      <div className="flex h-11 w-full min-w-0 flex-nowrap items-center gap-2 overflow-hidden" data-testid="table-toolbar">
        {showSections ? (
          <div
            role="group"
            aria-label={t("Floor")}
            className={`${scrollClass} flex h-10 max-w-[46%] min-w-[8.5rem] shrink items-center gap-0.5 overflow-x-auto rounded-xl bg-zinc-100 p-0.5 touch-pan-x dark:bg-zinc-800`}
            {...sectionScroll}
          >
            <SectionChip pressed={section === "all"} onClick={() => setSectionId("all")}>
              {t("All sections")}
            </SectionChip>
            {sections.map((item) => (
              <SectionChip key={item.id} pressed={section === item.id} onClick={() => setSectionId(item.id)}>
                {item.name}
              </SectionChip>
            ))}
          </div>
        ) : null}
        <div
          role="group"
          aria-label={t("Table summary")}
          className={`${scrollClass} flex h-10 min-w-0 flex-1 items-center gap-1 overflow-x-auto touch-pan-x`}
          {...statusScroll}
        >
          {FILTERS.map((item) => {
            const selected = filter === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-pressed={selected}
                onClick={() => setFilter(item.id)}
                className={`inline-flex h-10 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/40 ${
                  selected
                    ? `${item.active} font-semibold`
                    : "border-[var(--table-card-line)] bg-[var(--table-card-bg)] font-medium text-[var(--table-card-ink)]"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${selected ? "bg-white" : ""}`}
                  style={selected ? undefined : { background: item.tone }}
                  aria-hidden="true"
                />
                {t(item.label)}
                <span className="tabular-nums">{counts[item.id]}</span>
              </button>
            );
          })}
        </div>
        <label className="relative ms-auto h-10 w-36 shrink-0 sm:w-44">
          <span className="sr-only">{t("Search table or order...")}</span>
          <Search size={15} aria-hidden="true" className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--table-card-muted)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("Search table or order...")}
            className={`h-10 w-full rounded-xl border border-[var(--table-card-line)] bg-[var(--table-floor-bg)] ps-9 text-sm text-[var(--table-card-ink)] placeholder:text-[var(--table-card-muted)] focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 dark:bg-zinc-900 ${query ? "pe-9" : "pe-3"}`}
          />
          {query ? (
            <button
              type="button"
              aria-label={t("Clear search")}
              onClick={() => setQuery("")}
              className="absolute end-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-[var(--table-card-muted)] hover:bg-black/5 hover:text-[var(--table-card-ink)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:hover:bg-white/10"
            >
              <X size={14} aria-hidden="true" />
            </button>
          ) : null}
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

const scrollClass = "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden";

/** Drag-scroll a chip row, and ignore the click that ends a flick so it does not change the filter. */
function useDragScroll() {
  const origin = useRef(0);
  const start = useRef(0);
  const dragged = useRef(false);
  const active = useRef(false);
  return {
    onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      origin.current = event.clientX;
      start.current = event.currentTarget.scrollLeft;
      dragged.current = false;
      active.current = true;
    },
    onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
      if (!active.current) return;
      const dx = event.clientX - origin.current;
      if (!dragged.current && Math.abs(dx) <= 8) return;
      dragged.current = true;
      if (event.pointerType === "touch") return;
      event.currentTarget.setPointerCapture(event.pointerId);
      event.currentTarget.scrollLeft = start.current - dx;
    },
    onPointerUp: () => {
      active.current = false;
    },
    onPointerCancel: () => {
      active.current = false;
    },
    onClickCapture: (event: MouseEvent<HTMLDivElement>) => {
      if (!dragged.current) return;
      event.preventDefault();
      event.stopPropagation();
      dragged.current = false;
    },
  };
}

function SectionChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex h-9 shrink-0 items-center whitespace-nowrap rounded-lg px-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/40 ${
        pressed ? "bg-primary font-semibold text-white" : "bg-transparent font-medium text-[var(--table-card-ink)]"
      }`}
    >
      {children}
    </button>
  );
}
