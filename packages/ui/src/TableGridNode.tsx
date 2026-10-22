import type { ReactNode } from "react";
import { DiningTableShape } from "./DiningTableShape";

export type TableNodeTone = "available" | "occupied" | "billed";

const FILL: Record<TableNodeTone, { top: string; chair: string }> = {
  available: {
    top: "border border-emerald-500/40 bg-emerald-500/10",
    chair: "border border-slate-500/70 bg-slate-600/80",
  },
  occupied: {
    top: "border border-amber-500 bg-amber-500/20",
    chair: "border border-amber-500 bg-amber-500/20",
  },
  billed: {
    top: "border border-blue-500 bg-blue-500/20",
    chair: "border border-blue-500 bg-blue-500/20",
  },
};

const BADGE: Record<TableNodeTone, { label: string; className: string }> = {
  available: { label: "Available", className: "bg-emerald-500/15 text-emerald-300" },
  occupied: { label: "Occupied", className: "bg-amber-500/15 text-amber-200" },
  billed: { label: "Billed", className: "bg-blue-500/15 text-blue-300" },
};

const TOTAL: Record<TableNodeTone, string> = {
  available: "text-emerald-300",
  occupied: "text-amber-300",
  billed: "text-blue-300",
};

/** Maps a floor status onto the three table-node colours. */
export function tableNodeTone(status: string): TableNodeTone {
  if (status === "free") return "available";
  if (status === "bill") return "billed";
  return "occupied";
}

/** "4" and "T4" become "T-04". Named tables keep their label. */
export function tableDisplayNumber(label: string): string {
  const digits = /^(?:t-?)?(\d+)$/i.exec(label.trim());
  if (digits?.[1]) return `T-${digits[1].padStart(2, "0")}`;
  return label.trim();
}

/** Size band plus seat count, e.g. "Medium · 6 Person". */
export function tableCapacityLabel(seats: number): string {
  const count = Math.max(0, Math.round(seats));
  const size = count <= 4 ? "Small" : count <= 6 ? "Medium" : "Large";
  return `${size} · ${count} Person`;
}

function graphicSeats(seats: number): 2 | 4 | 6 | 8 {
  if (seats <= 2) return 2;
  if (seats <= 4) return 4;
  if (seats <= 6) return 6;
  return 8;
}

/** Miniature top-down table with a seat pill for each snapped capacity (2, 4, 6, or 8). */
export function TableSeatGraphic({ seats, tone, size = 76 }: { seats: number; tone: TableNodeTone; size?: number }) {
  const shown = graphicSeats(seats);
  const fill = FILL[tone];
  return (
    <span className="relative block shrink-0" style={{ width: size, height: size }} aria-hidden="true">
      <DiningTableShape
        shape={shown <= 4 ? "round" : "rect"}
        seats={shown}
        width={size}
        height={size}
        topClassName={fill.top}
        chairClassName={fill.chair}
      />
    </span>
  );
}

/** Dark POS table card: graphic, status pill, number, capacity, elapsed time, and running total. */
export function TableGridNode({
  label,
  seats,
  status,
  minutes,
  total,
  selected = false,
  disabled = false,
  className = "",
  badgeLabel,
  badgeClassName,
  ariaLabel,
  onClick,
  children,
}: {
  label: string;
  seats: number;
  status: string;
  minutes: number | null;
  total: string | null;
  selected?: boolean;
  disabled?: boolean;
  className?: string;
  badgeLabel?: string;
  badgeClassName?: string;
  ariaLabel?: string;
  onClick: () => void;
  children?: ReactNode;
}) {
  const tone = tableNodeTone(status);
  const badge = BADGE[tone];
  const title = tableDisplayNumber(label);
  const capacity = tableCapacityLabel(seats);
  const busy = status !== "free";
  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      aria-pressed={selected}
      aria-label={ariaLabel ?? `${title}, ${badgeLabel ?? badge.label}, ${capacity}`}
      onClick={() => {
        if (!disabled) onClick();
      }}
      onKeyDown={(event) => {
        if (disabled || event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      className={`flex min-h-[188px] w-full cursor-pointer flex-col bg-[#121824] border border-slate-800/80 rounded-2xl p-4 text-left text-white shadow-lg transition-all hover:border-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 ${className} ${
        selected ? "ring-2 ring-amber-300" : ""
      } ${disabled ? "opacity-60" : ""}`}
    >
      <span className="flex items-start justify-between gap-2">
        <TableSeatGraphic seats={seats} tone={tone} />
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${badgeClassName ?? badge.className}`}>
          {badgeLabel ?? badge.label}
        </span>
      </span>
      <span className="mt-3 flex flex-col gap-0.5">
        <span className="text-lg font-bold leading-tight text-white">{title}</span>
        <span className="text-xs font-medium text-slate-400">{capacity}</span>
      </span>
      <span className="mt-auto flex items-end justify-between gap-2 pt-3">
        <span className="text-sm text-slate-300">{busy && minutes !== null ? `${minutes} min` : ""}</span>
        {busy && total ? <span className={`text-sm font-bold tabular-nums ${TOTAL[tone]}`}>{total}</span> : <span />}
      </span>
      {children}
    </div>
  );
}
