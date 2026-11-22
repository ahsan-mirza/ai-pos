import type { ReactNode } from "react";

export const drawerShell =
  "flex min-h-0 flex-col border-zinc-200 bg-white font-sans text-zinc-900 dark:border-zinc-800 dark:bg-charcoal dark:text-zinc-100";

/** Drawer title row shared by the cart, open orders, and the refund summary. */
export function DrawerHeader({
  title,
  count,
  badge,
  toolbar,
  children,
  className = "h-16 px-5",
  compact = false,
}: {
  title: string;
  count?: string;
  badge?: ReactNode;
  /** Right-side controls that stay beside the title until the header is on a narrow phone. */
  toolbar?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** Tighter title and item count for the register's current-sale column. */
  compact?: boolean;
}) {
  return (
    <div
      className={`drawer-header flex w-full min-w-0 shrink-0 items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 ${
        compact ? "drawer-header-compact" : ""
      } ${className}`}
    >
      <div className={`drawer-header-lead flex min-w-0 items-center ${compact ? "shrink-0 gap-1.5" : "gap-3"}`}>
        <h2 className={`font-semibold leading-tight ${compact ? "whitespace-nowrap text-sm" : "min-w-0 truncate text-base"}`}>
          {title}
        </h2>
        {count ? (
          <span
            className={`shrink-0 whitespace-nowrap rounded-full bg-zinc-100 font-semibold tabular-nums text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 ${
              compact ? "px-2 py-0.5 text-[0.6875rem] leading-4" : "px-2.5 py-1 text-xs"
            }`}
          >
            {count}
          </span>
        ) : null}
      </div>
      {toolbar != null ? <div className="drawer-header-toolbar">{toolbar}</div> : null}
      {badge || children ? (
        <div className="drawer-header-end flex shrink-0 items-center gap-1.5">
          {badge}
          {children}
        </div>
      ) : null}
    </div>
  );
}

export interface BreakdownRow {
  label: string;
  value: string;
  tone?: "default" | "accent";
}

/** Subtotal / tax / fee rows and the live total, identical on every drawer. */
export function TotalsBreakdown({ rows, totalLabel, total }: { rows: BreakdownRow[]; totalLabel: string; total: string }) {
  return (
    <dl className="space-y-2 text-sm">
      {rows.map((row) => (
        <div key={row.label} className="flex justify-between gap-3">
          <dt className="text-zinc-500 dark:text-zinc-400">{row.label}</dt>
          <dd
            className={`font-medium tabular-nums ${
              row.tone === "accent" ? "text-primary-600 dark:text-primary-400" : "text-zinc-900 dark:text-zinc-100"
            }`}
          >
            {row.value}
          </dd>
        </div>
      ))}
      <div className="flex items-baseline justify-between gap-3 border-t border-zinc-200 pt-3 dark:border-zinc-800">
        <dt className="text-sm font-semibold">{totalLabel}</dt>
        <dd className="text-3xl font-bold tracking-tight tabular-nums text-primary-600 dark:text-primary-500">{total}</dd>
      </div>
    </dl>
  );
}

/** Sticky action area at the bottom of a drawer. */
export function DrawerFooter({ children }: { children: ReactNode }) {
  return (
    <div className="shrink-0 space-y-2 border-t border-zinc-200 bg-white px-5 pb-[max(0.875rem,env(safe-area-inset-bottom))] pt-3 dark:border-zinc-800 dark:bg-charcoal">
      {children}
    </div>
  );
}
