import { LanguageSwitch, useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronRight, FlaskConical, Moon, MoreHorizontal, Store as StoreIcon, Sun } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { store } from "../../features/checkout/catalog";
import { useCapabilities } from "../../lib/capabilities";
import { useRegisterLayout } from "../RegisterLayout";

export interface SyncState {
  tone: "synced" | "pending" | "offline" | "live";
  label: string;
  title: string;
}

const syncStyles: Record<SyncState["tone"], { className: string; dot: string }> = {
  synced: { className: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
  live: { className: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
  pending: { className: "text-amber-700 dark:text-amber-300", dot: "bg-amber-500" },
  offline: { className: "text-red-700 dark:text-red-300", dot: "bg-red-500" },
};

const themeEase: [number, number, number, number] = [0.22, 1, 0.36, 1];

function ThemeToggle() {
  const { theme, setTheme } = useRegisterLayout();
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const options = [
    { id: "light", label: t("Light theme"), icon: Sun },
    { id: "dark", label: t("Dark theme"), icon: Moon },
  ] as const;

  return (
    <div
      role="group"
      aria-label={t("Colour theme")}
      dir="ltr"
      className="flex h-10 shrink-0 items-center rounded-full bg-zinc-100 p-0.5 ring-1 ring-zinc-200 dark:bg-zinc-800 dark:ring-zinc-700"
    >
      {options.map(({ id, label, icon: Icon }) => {
        const active = theme === id;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={active}
            aria-label={label}
            title={label}
            onClick={() => {
              if (!active) setTheme(id);
            }}
            className="relative flex h-9 w-9 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/60"
          >
            {active ? (
              <motion.span
                layoutId="pos-theme-active"
                className="absolute inset-0 rounded-full bg-white shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-600"
                transition={reduced ? { duration: 0 } : { duration: 0.18, ease: themeEase }}
              />
            ) : null}
            <Icon
              size={16}
              aria-hidden="true"
              className={`relative ${active ? "text-primary-500" : "text-zinc-400 dark:text-zinc-500"}`}
            />
          </button>
        );
      })}
    </div>
  );
}

/**
 * One-row workspace header shared by every register page. Checkout actions stay on the right, after
 * connection, language, and theme. The signed-in cashier stays in the sidebar.
 */
export function HeaderBar({ title, sync, actions }: { title: string; sync: SyncState; actions?: ReactNode }) {
  const { t } = useLocale();
  const { practice } = useCapabilities();
  const reduced = useReducedMotion() === true;
  const [more, setMore] = useState(false);
  const moreId = useId();
  const { className: syncClass, dot } = syncStyles[sync.tone];
  const branch = /^restur[ae]nt$/i.test(store.name.trim()) ? t("Restaurant") : store.name;

  useEffect(() => {
    if (!more) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("[data-header-actions]")) return;
      setMore(false);
    };
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, [more]);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-zinc-200 bg-white px-3 dark:border-zinc-800 dark:bg-zinc-900 min-[1280px]:gap-3 min-[1280px]:px-4">
      <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
        <StoreIcon size={16} aria-hidden="true" className="shrink-0 text-zinc-400" />
        <nav aria-label={t("Breadcrumb")} className="flex min-w-0 items-center gap-1.5 overflow-hidden text-sm">
          <span className="max-w-[5.5rem] truncate font-medium text-zinc-500 min-[1366px]:max-w-[9rem] dark:text-zinc-400" dir="auto" title={branch}>
            {branch}
          </span>
          <ChevronRight size={14} aria-hidden="true" className="shrink-0 text-zinc-300 rtl:scale-x-[-1] dark:text-zinc-600" />
          <span aria-current="page" className="shrink-0 font-semibold text-zinc-950 dark:text-white">
            {t(title)}
          </span>
        </nav>
      </div>

      <div className="flex shrink-0 items-center gap-1.5 min-[1366px]:gap-2">
        {practice ? (
          <span
            title={t("Practice mode")}
            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-500/25 dark:text-amber-300"
          >
            <FlaskConical size={14} aria-hidden="true" />
            <span className="hidden min-[1440px]:inline">{t("Practice mode")}</span>
          </span>
        ) : null}
        <span
          title={sync.title}
          className={`inline-flex h-10 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-zinc-50 px-2.5 text-xs font-semibold ring-1 ring-zinc-200 dark:bg-zinc-800/70 dark:ring-zinc-700 ${syncClass}`}
        >
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
          {t(sync.label)}
        </span>
        <LanguageSwitch compact />
        <ThemeToggle />
        {actions ? (
          <div data-header-actions className="relative flex items-center">
            <button
              type="button"
              aria-expanded={more}
              aria-controls={moreId}
              aria-label={t("More actions")}
              title={t("More actions")}
              onClick={() => setMore((open) => !open)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 md:hidden dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <MoreHorizontal size={18} aria-hidden="true" />
            </button>
            <AnimatePresence initial={false}>
              {more ? (
                <motion.div
                  id={moreId}
                  className="absolute end-0 top-12 z-30 flex w-max max-w-[16rem] flex-col gap-1 rounded-2xl border border-zinc-200 bg-white p-2 shadow-lg md:hidden dark:border-zinc-700 dark:bg-zinc-900"
                  initial={reduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduced ? undefined : { opacity: 0, y: 4 }}
                  transition={{ duration: reduced ? 0 : 0.16 }}
                >
                  {actions}
                </motion.div>
              ) : null}
            </AnimatePresence>
            <div className="hidden items-center gap-1.5 md:flex">{actions}</div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
