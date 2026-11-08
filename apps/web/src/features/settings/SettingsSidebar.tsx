import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, MotionConfig } from "framer-motion";
import { ChevronDown, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import type { SettingsTab } from "../../components/layout/navigation";
import {
  generalSections,
  sectionHints,
  SETTINGS_NAV_WIDTH,
  tabAppearance,
  type SettingsNavMode,
} from "./settingsNav";

const ease = [0.4, 0, 0.2, 1] as const;

function onTab(tab: SettingsTab, pathname: string): boolean {
  if (tab.end) return pathname === tab.to;
  return pathname === tab.to || pathname.startsWith(`${tab.to}/`);
}

function itemClass(active: boolean): string {
  return `relative flex h-10 w-full items-center gap-2.5 rounded-xl px-2.5 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
    active ? "text-white" : "text-white/80 hover:bg-white/10"
  }`;
}

export function SidebarCollapseToggle({
  label,
  expands,
  onClick,
}: {
  label: string;
  expands: boolean;
  onClick: () => void;
}) {
  const { t } = useLocale();
  const Icon = expands ? PanelLeftOpen : PanelLeftClose;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t(label)}
      title={t(label)}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white/70 outline-none hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-white/70"
    >
      <Icon size={16} aria-hidden="true" />
    </button>
  );
}

export function SettingsSidebarHeader({
  title,
  mode,
  actionLabel,
  onAction,
}: {
  title: string;
  mode: SettingsNavMode;
  actionLabel: string;
  onAction: () => void;
}) {
  const { t } = useLocale();
  const expands = actionLabel === "Expand navigation" || actionLabel === "Show compact labels";
  return (
    <div className={`flex shrink-0 items-start gap-2 ${mode === "collapsed" ? "justify-center px-2" : "px-3"}`}>
      {mode === "collapsed" ? null : (
        <div className="min-w-0 flex-1">
          <h2 className="line-clamp-2 text-sm font-semibold leading-5">{title}</h2>
          {mode === "expanded" ? (
            <p className="mt-0.5 text-xs leading-4 text-white/55">{t("Each section opens on its own.")}</p>
          ) : null}
        </div>
      )}
      <SidebarCollapseToggle label={actionLabel} expands={expands && mode === "collapsed"} onClick={onAction} />
    </div>
  );
}

function ActiveWash({ active }: { active: boolean }) {
  return (
    <AnimatePresence>
      {active ? (
        <motion.span
          layoutId="settings-nav-active"
          className="absolute inset-0 rounded-xl bg-accent"
          transition={{ duration: 0.22, ease }}
        />
      ) : null}
    </AnimatePresence>
  );
}

export function SettingsNavigationTooltip({
  label,
  enabled,
  children,
}: {
  label: string;
  enabled: boolean;
  children: ReactNode;
}) {
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);
  if (!enabled) return children;
  return (
    <span
      className="relative flex"
      onPointerEnter={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const rtl = document.documentElement.dir === "rtl";
        setBox({ top: rect.top + rect.height / 2, left: rtl ? rect.left - 8 : rect.right + 8 });
      }}
      onPointerLeave={() => setBox(null)}
      onFocus={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const rtl = document.documentElement.dir === "rtl";
        setBox({ top: rect.top + rect.height / 2, left: rtl ? rect.left - 8 : rect.right + 8 });
      }}
      onBlur={() => setBox(null)}
    >
      {children}
      {box
        ? createPortal(
            <span
              role="tooltip"
              style={{ top: box.top, left: box.left }}
              className={`pointer-events-none fixed z-50 -translate-y-1/2 whitespace-nowrap rounded-md bg-white px-2 py-1 text-xs font-medium text-charcoal shadow-lg ${
                document.documentElement.dir === "rtl" ? "-translate-x-full" : ""
              }`}
            >
              {label}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}

export function SettingsSubmenu({
  openSection,
  mode,
  onNavigate,
}: {
  openSection: string;
  mode: SettingsNavMode;
  onNavigate?: () => void;
}) {
  const { t } = useLocale();
  const onGeneral = true;
  return (
    <ul id="settings-general-sections" className={mode === "collapsed" ? "space-y-0.5" : "ms-3 space-y-0.5 border-s border-white/15 ps-1.5"}>
      {generalSections.map((section) => {
        const current = onGeneral && openSection === section.id;
        const Icon = section.icon;
        const text = mode === "compact" ? t(section.short) : t(section.label);
        return (
          <li key={section.id}>
            <Link
              to={`/settings#${section.id}`}
              aria-current={current ? "page" : undefined}
              aria-label={mode === "collapsed" ? t(section.label) : undefined}
              title={mode === "collapsed" ? t(section.label) : undefined}
              onClick={onNavigate}
              className={itemClass(current)}
            >
              <ActiveWash active={current} />
              <Icon size={16} aria-hidden="true" className="relative z-10 shrink-0" />
              {mode === "collapsed" ? null : <span className="relative z-10 truncate">{text}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function SettingsAccordion({
  open,
  mode,
  children,
}: {
  open: boolean;
  mode: SettingsNavMode;
  children: ReactNode;
}) {
  if (mode === "collapsed") return null;
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          key="settings-general"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease }}
          className="overflow-hidden"
        >
          <div className="pt-1">{children}</div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function GeneralPopover({
  anchor,
  openSection,
  onClose,
}: {
  anchor: DOMRect;
  openSection: string;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const rtl = document.documentElement.dir === "rtl";
  const left = rtl ? Math.max(8, anchor.left - 232) : anchor.right + 8;
  return createPortal(
    <motion.div
      role="menu"
      aria-label={t("General")}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 4 }}
      transition={{ duration: 0.18, ease }}
      style={{ top: anchor.top, left }}
      className="fixed z-50 w-56 rounded-xl bg-charcoal p-2 text-white shadow-xl"
    >
      <SettingsSubmenu openSection={openSection} mode="expanded" onNavigate={onClose} />
    </motion.div>,
    document.body,
  );
}

export function SettingsNavigationItem({
  tab,
  pathname,
  mode,
  generalOpen,
  openSection,
  showGeneral,
  onToggleGeneral,
  onNavigate,
}: {
  tab: SettingsTab;
  pathname: string;
  mode: SettingsNavMode;
  generalOpen: boolean;
  openSection: string;
  showGeneral: boolean;
  onToggleGeneral: (anchor: DOMRect | null) => void;
  onNavigate?: () => void;
}) {
  const { t } = useLocale();
  const here = onTab(tab, pathname);
  const appearance = tabAppearance(tab.to);
  const Icon = appearance.icon;
  const label = t(tab.label);
  const short = t(appearance.short);
  const shown = mode === "compact" ? short : label;
  const hint = sectionHints[tab.to];
  const isGeneral = tab.to === "/settings" && showGeneral;
  const selected = !tab.end && here;
  const grouped = Boolean(tab.end && here);

  const body = (
    <>
      <ActiveWash active={selected} />
      <Icon size={18} aria-hidden="true" className="relative z-10 shrink-0" />
      {mode === "collapsed" ? null : (
        <span className="relative z-10 min-w-0 flex-1">
          <span className="block truncate font-medium">{shown}</span>
          {mode === "expanded" && hint ? (
            <span className={`mt-0.5 block truncate text-[11px] leading-4 ${selected ? "text-white/80" : "text-white/45"}`}>
              {t(hint)}
            </span>
          ) : null}
        </span>
      )}
    </>
  );

  const row = isGeneral ? (
    <button
      type="button"
      className={`${itemClass(false)} ${grouped ? "bg-white/10" : ""} ${mode === "expanded" && hint ? "h-auto min-h-10 py-2" : ""}`}
      aria-expanded={mode === "collapsed" ? undefined : generalOpen}
      aria-controls={mode === "collapsed" ? undefined : "settings-general-sections"}
      aria-label={mode === "collapsed" ? label : undefined}
      data-settings-general=""
      onClick={(event) => onToggleGeneral(mode === "collapsed" ? event.currentTarget.getBoundingClientRect() : null)}
    >
      {body}
      {mode === "collapsed" ? null : (
        <motion.span className="relative z-10 text-white/60" animate={{ rotate: generalOpen ? 180 : 0 }} transition={{ duration: 0.22, ease }}>
          <ChevronDown size={16} aria-hidden="true" />
        </motion.span>
      )}
    </button>
  ) : (
    <Link
      to={tab.to}
      aria-current={selected ? "page" : undefined}
      aria-label={mode === "collapsed" ? label : undefined}
      onClick={onNavigate}
      className={`${itemClass(false)} ${mode === "expanded" && hint ? "h-auto min-h-10 py-2" : ""}`}
    >
      {body}
    </Link>
  );

  return (
    <li>
      <SettingsNavigationTooltip label={label} enabled={mode === "collapsed"}>
        {row}
      </SettingsNavigationTooltip>
      {isGeneral ? (
        <SettingsAccordion open={generalOpen} mode={mode}>
          <SettingsSubmenu openSection={pathname === "/settings" ? openSection : ""} mode={mode} onNavigate={onNavigate} />
        </SettingsAccordion>
      ) : null}
    </li>
  );
}

export function SettingsMobileDrawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useLocale();
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open ? (
        <div className="fixed inset-0 z-50">
          <motion.button
            type="button"
            aria-label={t("Close settings menu")}
            className="absolute inset-0 bg-charcoal/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="absolute inset-y-0 start-0 flex w-[min(288px,86vw)] flex-col bg-charcoal pt-[max(0.75rem,env(safe-area-inset-top))] text-white shadow-2xl"
            initial={{ x: document.documentElement.dir === "rtl" ? "100%" : "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: document.documentElement.dir === "rtl" ? "100%" : "-100%" }}
            transition={{ duration: 0.24, ease }}
          >
            <div className="flex items-center justify-between gap-3 px-4 pb-3">
              <h2 id={titleId} className="text-base font-semibold">
                {title}
              </h2>
              <button
                type="button"
                onClick={onClose}
                aria-label={t("Close settings menu")}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 hover:bg-white/10 hover:text-white"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{children}</div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

export function SettingsSidebar({
  mode,
  title,
  actionLabel,
  onAction,
  tabs,
  pathname,
  generalOpen,
  openSection,
  showGeneral,
  onToggleGeneral,
  popoverAnchor,
  onClosePopover,
}: {
  mode: SettingsNavMode;
  title: string;
  actionLabel: string;
  onAction: () => void;
  tabs: SettingsTab[];
  pathname: string;
  generalOpen: boolean;
  openSection: string;
  showGeneral: boolean;
  onToggleGeneral: (anchor: DOMRect | null) => void;
  popoverAnchor: DOMRect | null;
  onClosePopover: () => void;
}) {
  return (
    <MotionConfig reducedMotion="user">
      <motion.aside
        initial={false}
        animate={{ width: SETTINGS_NAV_WIDTH[mode] }}
        transition={{ duration: 0.22, ease }}
        className="flex h-full min-h-0 shrink-0 flex-col overflow-hidden rounded-none bg-charcoal py-3 text-white"
        aria-label={title}
      >
        <SettingsSidebarHeader title={title} mode={mode} actionLabel={actionLabel} onAction={onAction} />
        <nav className="mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain px-2" aria-label={title}>
          <ul className="space-y-1">
            {tabs.map((tab) => (
              <SettingsNavigationItem
                key={tab.to}
                tab={tab}
                pathname={pathname}
                mode={mode}
                generalOpen={generalOpen}
                openSection={openSection}
                showGeneral={showGeneral}
                onToggleGeneral={onToggleGeneral}
              />
            ))}
          </ul>
        </nav>
      </motion.aside>
      <AnimatePresence>
        {popoverAnchor ? (
          <GeneralPopover key="general-popover" anchor={popoverAnchor} openSection={openSection} onClose={onClosePopover} />
        ) : null}
      </AnimatePresence>
    </MotionConfig>
  );
}
