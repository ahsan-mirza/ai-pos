import { BATCH_STATUS_LABELS, type BatchStatus } from "@ai-pos/shared-types";

const statusStyles: Record<BatchStatus, { pill: string; dot: string }> = {
  ACTIVE: { pill: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  PARTIALLY_SOLD: { pill: "bg-orange-50 text-orange-700 ring-orange-600/20", dot: "bg-accent" },
  EXHAUSTED: { pill: "bg-zinc-100 text-zinc-600 ring-zinc-500/20", dot: "bg-zinc-400" },
  REVERSED: { pill: "bg-red-50 text-red-700 ring-red-600/20", dot: "bg-red-500" },
};

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const style = statusStyles[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${style.pill}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {BATCH_STATUS_LABELS[status]}
    </span>
  );
}

export function SoldMeter({
  percent,
  reversed = false,
  label,
}: {
  percent: number;
  reversed?: boolean;
  /** Accessible summary, e.g. "12 of 40 units sold". */
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div className="flex min-w-[128px] items-center gap-2.5" title={label}>
      <div
        role="meter"
        aria-label={label ?? "Sold through FIFO"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-200/80"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            reversed ? "bg-zinc-400" : clamped >= 100 ? "bg-emerald-500" : "bg-accent"
          }`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-11 text-right text-xs font-semibold tabular-nums text-charcoal/70">
        {clamped.toFixed(clamped % 1 ? 1 : 0)}%
      </span>
    </div>
  );
}

export function formatDay(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
