/** Shared register design tokens: one class string per role so every page renders identically. */
export const ui = {
  page: "bg-slate-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100",
  panel: "bg-white dark:bg-zinc-900",
  surface: "bg-zinc-50 dark:bg-zinc-800/40",
  input:
    "border border-zinc-200 bg-white text-zinc-900 placeholder:text-zinc-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-100 dark:placeholder:text-zinc-500",
  border: "border-zinc-200 dark:border-zinc-800",
  divide: "divide-zinc-200 dark:divide-zinc-800",
  muted: "text-zinc-500 dark:text-zinc-400",
  label: "text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400",
  card: "rounded-2xl border border-zinc-200 bg-white transition-colors hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-800/40 dark:hover:border-zinc-700",
  primaryAction:
    "flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-primary-500 px-5 text-base font-bold tabular-nums text-white shadow-lg shadow-primary-500/25 transition-colors hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary-500/30 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500 disabled:shadow-none dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500",
  secondaryAction:
    "flex items-center justify-center gap-1.5 rounded-xl border border-zinc-200 bg-white text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 disabled:opacity-40 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-200 dark:hover:bg-zinc-800 dark:hover:text-white",
  ghostAction:
    "h-11 w-full rounded-xl text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
  iconButton:
    "inline-flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-200 bg-white text-zinc-600 transition-colors hover:border-primary-500 hover:text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 active:scale-[0.98] disabled:opacity-40 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:text-primary-400",
} as const;

export type StockTone = "in" | "low" | "out";

export const stockPill: Record<StockTone, string> = {
  in: "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20 dark:text-emerald-300",
  low: "bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/25 dark:text-amber-300",
  out: "bg-red-500/10 text-red-700 ring-1 ring-red-500/20 dark:text-red-300",
};
