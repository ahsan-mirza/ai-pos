import type { ReactNode } from "react";

export const drawerShell =
  "flex min-h-0 flex-col border-zinc-200 bg-white font-sans text-zinc-900 dark:border-zinc-800 dark:bg-charcoal dark:text-zinc-100";

/** Drawer title row shared by the cart and the refund summary. */
export function DrawerHeader({ title, count, badge, children }: { title: string; count?: string; badge?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex h-16 shrink-0 items-center gap-3 border-b border-zinc-200 px-5 dark:border-zinc-800">
      <h2 className="text-base font-semibold">{title}</h2>
      {count ? (
        <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-semibold tabular-nums text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {count}
        </span>
      ) : null}
      <span className="ml-auto flex items-center gap-2">
        {badge}
        {children}
      </span>
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
