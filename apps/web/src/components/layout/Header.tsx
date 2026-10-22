import type { InsightItem } from "@ai-pos/shared-types";
import { Bell, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type RefObject } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { useCanManageSettings, useCurrency } from "../../lib/currency";
import { useCapabilities } from "../../lib/capabilities";
import { crumbsFor, settingsLabel } from "./navigation";
import { StoreSwitcher } from "./StoreSwitcher";

const iconButton =
  "relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-charcoal/60 outline-none transition-colors hover:bg-charcoal/[0.05] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40";

function useDismiss(ref: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [ref, open, close]);
}

const FEED_REFRESH_MS = 5 * 60 * 1000;
const SEEN_KEY = "ai-pos.insights.seen";

const signature = (item: InsightItem) => `${item.kind}:${item.title}:${item.body}`;

function Notifications() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<InsightItem[]>([]);
  const [seen, setSeen] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, open, () => setOpen(false));

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      void apiGet<{ items: InsightItem[] }>("/api/v1/insights/feed")
        .then((feed) => {
          if (!cancelled) setItems(feed.items);
        })
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, FEED_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const unread = items.filter((item) => !seen.includes(signature(item))).length;
  const markAllRead = () => {
    const next = items.map(signature);
    setSeen(next);
    localStorage.setItem(SEEN_KEY, JSON.stringify(next));
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((value) => !value)}
        className={`${iconButton} ${open ? "bg-charcoal/[0.05] text-charcoal" : ""}`}
      >
        <Bell size={18} strokeWidth={1.75} aria-hidden="true" />
        {unread ? (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold tabular-nums leading-none text-white ring-2 ring-white">
            {unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Notifications"
          className="popover-in absolute right-0 top-11 z-40 w-[min(360px,calc(100vw-1.5rem))] overflow-hidden rounded-xl border border-line bg-white shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-semibold">Notifications</span>
            <button
              type="button"
              disabled={unread === 0}
              onClick={markAllRead}
              className="text-xs font-semibold text-accent hover:underline disabled:text-charcoal/30 disabled:no-underline"
            >
              Mark all read
            </button>
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-charcoal/55">Nothing needs your attention right now.</p>
          ) : null}
          <ul className="divide-y divide-line">
            {items.map((note) => (
              <li key={signature(note)}>
                <Link
                  to={note.to}
                  onClick={() => setOpen(false)}
                  className="flex gap-3 px-4 py-3 transition-colors hover:bg-[#f8fafc]"
                >
                  <span
                    aria-hidden="true"
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                      seen.includes(signature(note)) ? "bg-transparent" : note.severity === "HIGH" ? "bg-red-500" : "bg-accent"
                    }`}
                  />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-semibold">{note.title}</span>
                    <span className="mt-0.5 block text-xs text-charcoal/55">{note.body}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function Header({
  collapsed,
  onToggleCollapsed,
  onOpenMobile,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onOpenMobile: () => void;
}) {
  const { pathname } = useLocation();
  const { currency } = useCurrency();
  const canManageSettings = useCanManageSettings();
  const capabilities = useCapabilities();
  const crumbs = crumbsFor(pathname, capabilities);
  const settingsName = settingsLabel(capabilities);
  const badge =
    "hidden h-7 items-center rounded-md border border-line bg-[#f8fafc] px-2 font-mono text-[11px] font-bold tracking-wider text-charcoal/70 sm:inline-flex";

  return (
    <header className="relative z-30 flex h-16 shrink-0 items-center gap-2 border-b border-line bg-white/90 px-3 backdrop-blur supports-[backdrop-filter]:bg-white/75 md:px-4 lg:px-6">
      <button
        type="button"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-keyshortcuts="["
        title={collapsed ? "Expand sidebar  [" : "Collapse sidebar  ["}
        className={`${iconButton} -ml-1.5 hidden lg:flex`}
      >
        {collapsed ? <PanelLeftOpen size={18} strokeWidth={1.75} /> : <PanelLeftClose size={18} strokeWidth={1.75} />}
      </button>
      <button
        type="button"
        onClick={onOpenMobile}
        aria-label="Open navigation"
        className={`${iconButton} -ml-1 lg:hidden`}
      >
        <PanelLeftOpen size={18} strokeWidth={1.75} />
      </button>

      <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line lg:block" />

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-1.5 text-[13px]">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <Fragment key={`${crumb.label}-${index}`}>
                {index ? (
                  <li aria-hidden="true" className="hidden text-charcoal/25 sm:block">
                    /
                  </li>
                ) : null}
                <li className={`min-w-0 ${last ? "" : "hidden sm:block"}`}>
                  {last ? (
                    <span aria-current="page" className="block truncate font-semibold text-charcoal">
                      {crumb.label}
                    </span>
                  ) : crumb.to ? (
                    <Link to={crumb.to} className="block truncate text-charcoal/50 transition-colors hover:text-charcoal">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="block truncate text-charcoal/50">{crumb.label}</span>
                  )}
                </li>
              </Fragment>
            );
          })}
        </ol>
      </nav>

      <div className="flex shrink-0 items-center gap-1.5 md:gap-2">
        <StoreSwitcher className="hidden !w-[230px] md:block" />
        {canManageSettings ? (
          <Link
            to="/settings"
            title={`Business currency. Change it in ${settingsName}`}
            aria-label={`Business currency ${currency}. Change in ${settingsName}`}
            className={`${badge} transition-colors hover:border-charcoal/30 hover:text-charcoal`}
          >
            {currency}
          </Link>
        ) : (
          <span title="Business currency" aria-label={`Business currency ${currency}`} className={badge}>
            {currency}
          </span>
        )}
        <Notifications />
      </div>
    </header>
  );
}
