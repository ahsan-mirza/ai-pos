import type { TableStatus } from "@ai-pos/shared-types";
import { tableFootprint, type TableShape } from "@ai-pos/ui";
import { FloorTableCard, floorTableGridClass } from "../../../components/FloorTableCard";
import { useBusinessCurrency } from "../currency";

export interface TableChoice {
  id: string | null;
  label: string;
  seats: number;
  busy: boolean;
  shape: TableShape;
  x: number;
  y: number;
  w: number;
  h: number;
  status: TableStatus;
  covers: number;
  seatedAt: string | null;
  openCents: number;
  orderId: string | null;
}

/** Places unnamed fallback tables on a floor so they use the same shape as a real floor plan. */
export function layoutFallback(labels: string[]): TableChoice[] {
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  return labels.map((label) => {
    const footprint = tableFootprint("square", 4);
    if (x > 0 && x + footprint.w > 8) {
      x = 0;
      y += rowHeight;
      rowHeight = 0;
    }
    const table: TableChoice = {
      id: null,
      label,
      seats: 4,
      busy: false,
      shape: "square",
      x,
      y,
      w: footprint.w,
      h: footprint.h,
      status: "free",
      covers: 0,
      seatedAt: null,
      openCents: 0,
      orderId: null,
    };
    x += footprint.w;
    rowHeight = Math.max(rowHeight, footprint.h);
    return table;
  });
}

/** Floor-plan tables for dine-in. Occupied tables stay tappable so a second register can join the tab. */
export function TableSelectorGrid({
  tables,
  selected,
  onSelect,
}: {
  tables: TableChoice[];
  selected: string | null;
  onSelect: (table: TableChoice) => void;
}) {
  const currency = useBusinessCurrency();
  if (tables.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No tables on this floor.</p>;
  }

  return (
    <div className={`overflow-visible rounded-3xl border border-zinc-200 bg-zinc-950/40 dark:border-white/10 ${floorTableGridClass}`} aria-label="Tables">
      {tables.map((table) => (
        <FloorTableCard
          key={table.id ?? table.label}
          tableId={table.id}
          label={table.label}
          seats={table.seats}
          covers={table.covers}
          seatedAt={table.seatedAt}
          openCents={table.openCents}
          currency={currency}
          status={table.status}
          selected={selected === table.label}
          onClick={() => onSelect(table)}
        />
      ))}
    </div>
  );
}
