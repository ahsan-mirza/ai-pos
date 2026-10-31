import { ChevronRight, CloudOff, FlaskConical, Moon, RefreshCw, Store as StoreIcon, Sun, Wifi } from "lucide-react";
import type { ReactNode } from "react";
import { store } from "../../features/checkout/catalog";
import { useCapabilities } from "../../lib/capabilities";
import { useRegisterLayout } from "../RegisterLayout";

export interface SyncState {
  tone: "synced" | "pending" | "offline" | "live";
  label: string;
  title: string;
}

const syncStyles: Record<SyncState["tone"], { className: string; icon: typeof Wifi }> = {
  synced: { className: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300", icon: RefreshCw },
  live: { className: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300", icon: Wifi },
  pending: { className: "bg-amber-500/10 text-amber-700 ring-amber-500/25 dark:text-amber-300", icon: RefreshCw },
  offline: { className: "bg-red-500/10 text-red-700 ring-red-500/20 dark:text-red-300", icon: CloudOff },
};

/**
 * Workspace header shared by every register page: breadcrumb, page actions, sync and theme. The signed-in cashier
 * appears only in the sidebar's profile card.
 */
export function HeaderBar({ title, sync, actions }: { title: string; sync: SyncState; actions?: ReactNode }) {
  const { theme, setTheme } = useRegisterLayout();
  const { practice } = useCapabilities();
  const { className: syncClass, icon: SyncIcon } = syncStyles[sync.tone];

  return (
    <header className="flex min-h-16 shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-zinc-200 bg-white px-5 py-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="min-w-[12rem] flex-1">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          <StoreIcon size={13} aria-hidden="true" />
          <span className="truncate">{/^restur[ae]nt$/i.test(store.name.trim()) ? "Restaurant" : store.name}</span>
          <ChevronRight size={13} aria-hidden="true" className="shrink-0 text-zinc-300 dark:text-zinc-600" />
          <span aria-current="page" className="truncate text-zinc-900 dark:text-zinc-100">
            {title}
          </span>
        </nav>
        <h1 className="mt-0.5 truncate text-lg font-semibold tracking-tight">{title}</h1>
      </div>

      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}

      <div className="flex items-center gap-2">
        {practice ? (
          <span
            title="This store has not gone live. Sales rung up now are practice and are cleared when the owner goes live."
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-amber-500/10 px-3 text-xs font-semibold text-amber-800 ring-1 ring-amber-500/25 dark:text-amber-300"
          >
            <FlaskConical size={13} aria-hidden="true" />
            Practice mode
          </span>
        ) : null}
        <span
          title={sync.title}
          className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-semibold tabular-nums ring-1 ${syncClass}`}
        >
          <SyncIcon size={13} aria-hidden="true" />
          {sync.label}
        </span>
        <div role="group" aria-label="Colour theme" className="flex h-12 items-center rounded-full bg-zinc-100 p-1 ring-1 ring-zinc-200 dark:bg-zinc-800/60 dark:ring-zinc-800">
          {(
            [
              { id: "light", label: "Light", icon: Sun },
              { id: "dark", label: "Dark", icon: Moon },
            ] as const
          ).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-pressed={theme === id}
              onClick={() => setTheme(id)}
              className={`flex h-10 items-center gap-1.5 rounded-full px-3 text-sm font-medium transition-colors ${
                theme === id
                  ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white"
                  : "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              }`}
            >
              <Icon size={13} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
