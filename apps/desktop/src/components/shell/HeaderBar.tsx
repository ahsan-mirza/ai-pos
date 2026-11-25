import { LanguageSwitch, useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FlaskConical, Moon, MoreHorizontal, Sun } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { OpenDrawerButton } from "../../features/audit/OpenDrawerButton";
import { useCapabilities } from "../../lib/capabilities";
import { useRegisterLayout } from "../RegisterLayout";
import { ScreenToggle } from "./ScreenToggle";
import { drawerButtonClass } from "./settingsEntry";
import { useShell } from "./ShellContext";
import type { SyncState } from "./syncState";

export type { SyncState };

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
              aria-hidden="true"
              className={`relative h-4 w-4 ${active ? "text-primary-500" : "text-zinc-400 dark:text-zinc-500"}`}
            />
          </button>
        );
      })}
    </div>
  );
}

/**
 * One-row workspace header shared by every register page. Checkout actions stay on the right, after
 * language and theme. Connection, sync, and activation stay in the bottom status bar.
 * The signed-in cashier stays in the sidebar.
 */
export function HeaderBar({
  sync,
  actions,
  leading,
}: {
  title: string;
  sync: SyncState;
  actions?: ReactNode;
  /** Checkout customer search. Sits in the open space before language and theme. */
  leading?: ReactNode;
}) {
  const headerRef = useRef<HTMLElement>(null);
  const { setRegisterStatus, view, busy, drawerHeld } = useShell();
  const { t } = useLocale();
  const { practice } = useCapabilities();
  const reduced = useReducedMotion() === true;
  const [more, setMore] = useState(false);
  const moreId = useId();

  useEffect(() => {
    if (headerRef.current?.closest(".hidden")) return;
    setRegisterStatus(sync);
    return () => setRegisterStatus(null);
  }, [view, sync.tone, sync.label, sync.title, setRegisterStatus]);

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
    <header ref={headerRef} className="relative z-30 flex h-14 shrink-0 items-center gap-2 border-b border-zinc-200 bg-white px-3 dark:border-zinc-800 dark:bg-zinc-900 min-[80rem]:gap-3 min-[80rem]:px-4">
      <div className="min-w-0 flex-1">{leading ? <div className="w-full min-w-[14rem] max-w-md">{leading}</div> : null}</div>
      <div className="flex shrink-0 items-center gap-1.5 min-[85.375rem]:gap-2">
        {practice ? (
          <span
            title={t("Practice mode")}
            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-500/25 dark:text-amber-300"
          >
            <FlaskConical size={14} aria-hidden="true" />
            <span className="hidden min-[90rem]:inline">{t("Practice mode")}</span>
          </span>
        ) : null}
        <LanguageSwitch compact />
        <ThemeToggle />
        <ScreenToggle />
        <OpenDrawerButton className={drawerButtonClass} disabled={busy || drawerHeld} iconOnly />
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
              <MoreHorizontal aria-hidden="true" className="h-[1.125rem] w-[1.125rem]" />
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
