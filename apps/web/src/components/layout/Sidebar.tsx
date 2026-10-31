import { BrandLogo } from "@ai-pos/ui";
import { ChevronDown, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type FocusEvent, type MouseEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTenant } from "../../context/TenantContext";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { portalHomePath } from "../../lib/portal-home";
import { useCapabilities } from "../../lib/capabilities";
import { useCanManageSettings } from "../../lib/currency";
import { AiMark } from "../ui/AiMark";
import { labelOf, navGroups, settingsTabAllowed, settingsTabs, type NavItem } from "./navigation";
import { revealSection, toggleSection } from "./sidebarSections";
import { StoreSwitcher } from "./StoreSwitcher";

type VisibleItem = NavItem & { label: string };

interface VisibleGroup {
  id: string;
  label: string;
  items: VisibleItem[];
}

/** The groups this user may open for this business type, with names resolved for it. */
function useVisibleGroups(): VisibleGroup[] {
  const { can } = useAuth();
  const canManageSettings = useCanManageSettings();
  const superAdmin = useIsSuperAdmin();
  const capabilities = useCapabilities();
  const tenant = useTenant();
  const gate = { can, canManageSettings, superAdmin, has: capabilities.has, allows: tenant.allows };
  return navGroups
    .map((group) => ({
      id: group.id,
      label: group.label,
      items: group.items.flatMap((item) => {
        if (item.hub) {
          const open = settingsTabs.filter((tab) => settingsTabAllowed(tab, gate));
          const first = open[0];
          if (first === undefined) return [];
          return [{ ...item, to: first.to, label: labelOf(item, capabilities) }];
        }
        const visible =
          tenant.allows(item.profiles) &&
          (item.capability === undefined || capabilities.has(item.capability)) &&
          (!item.superAdminOnly || superAdmin) &&
          (item.settingsOnly ? canManageSettings : can(item.permission));
        return visible ? [{ ...item, label: labelOf(item, capabilities) }] : [];
      }),
    }))
    .filter((group) => group.items.length > 0);
}

interface Tip {
  label: ReactNode;
  top: number;
}

function sectionId(id: string): string {
  return `nav-section-${id}`;
}

/**
 * One expansion set for the desktop rail and the mobile drawer.
 * The first visible section starts open. A route change opens the section
 * that contains the page and leaves every other section as the user left it.
 */
function useSectionExpansion() {
  const { pathname, hash } = useLocation();
  const groups = useVisibleGroups();
  const activeId = groups.find((group) => group.items.some((item) => item.isActive(pathname, hash)))?.id ?? null;
  const followed = activeId ?? groups[0]?.id ?? null;
  const [openIds, setOpenIds] = useState<ReadonlySet<string>>(() => new Set());
  const touched = useRef(false);
  const revealedRoute = useRef<string | null>(null);

  useLayoutEffect(() => {
    const route = `${pathname}${hash}`;
    const routeChanged = revealedRoute.current !== route;
    revealedRoute.current = route;
    setOpenIds((current) => {
      if (!touched.current && current.size === 0) return new Set(followed ? [followed] : []);
      if (!routeChanged) return current;
      return revealSection(current, activeId);
    });
  }, [pathname, hash, activeId, followed]);

  const toggle = (id: string) => {
    touched.current = true;
    setOpenIds((current) => toggleSection(current, id));
  };

  return { groups, isOpen: (id: string) => openIds.has(id), toggle };
}

function SidebarNav({
  instance,
  collapsed,
  groups,
  isOpen,
  onToggle,
  onNavigate,
  onTip,
  subscriptionLocked,
}: {
  instance: "rail" | "drawer";
  collapsed: boolean;
  groups: VisibleGroup[];
  isOpen: (id: string) => boolean;
  onToggle: (id: string) => void;
  onNavigate?: () => void;
  onTip?: (tip: Tip | null) => void;
  subscriptionLocked: boolean;
}) {
  const { pathname, hash } = useLocation();

  const showTip = (item: VisibleItem) => (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    if (!collapsed || !onTip) return;
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label: item.label, top: rect.top + rect.height / 2 });
  };
  const hideTip = () => onTip?.(null);

  return (
    <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4" onScroll={hideTip}>
      {groups.map((group, index) => {
        const open = isOpen(group.id);
        const showItems = collapsed || open;
        const panelId = `${sectionId(group.id)}-${instance}`;
        return (
          <div key={group.id} className={index ? "mt-2" : ""}>
            {collapsed ? (
              index ? <div className="mx-3 mb-1 h-px bg-line" /> : null
            ) : (
              <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => onToggle(group.id)}
                className={`flex h-8 w-full items-center justify-between rounded-lg px-3 text-[11px] font-semibold uppercase tracking-[0.12em] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 ${
                  open
                    ? "text-charcoal/40 hover:bg-charcoal/[0.04] hover:text-charcoal"
                    : "text-charcoal/40 hover:bg-accent/[0.08] hover:text-accent"
                }`}
              >
                <span>{group.label}</span>
                <ChevronDown
                  size={14}
                  aria-hidden="true"
                  className={`shrink-0 transition-transform duration-200 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
                />
              </button>
            )}
            {showItems ? (
              <ul id={panelId} className="space-y-0.5">
                {group.items.map((item) => {
                  const active = item.isActive(pathname, hash);
                  return (
                    <li key={item.to}>
                      <Link
                        to={subscriptionLocked ? "/subscription" : item.to}
                        onClick={onNavigate}
                        title={subscriptionLocked ? "Locked until payment is verified" : undefined}
                        aria-disabled={subscriptionLocked || undefined}
                        aria-current={active ? "page" : undefined}
                        aria-label={collapsed ? item.label : undefined}
                        onMouseEnter={showTip(item)}
                        onMouseLeave={hideTip}
                        onFocus={showTip(item)}
                        onBlur={hideTip}
                        className={`group relative flex h-10 items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 ${
                          active
                            ? "bg-accent/[0.08] text-accent"
                            : "text-charcoal/70 hover:bg-charcoal/[0.04] hover:text-charcoal"
                        }`}
                      >
                        {active ? (
                          <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[3px] rounded-r-full bg-accent" />
                        ) : null}
                        {item.ai ? <AiMark size={13} /> : null}
                        <item.icon
                          aria-hidden="true"
                          size={18}
                          strokeWidth={active ? 2 : 1.75}
                          className={`shrink-0 ${active ? "" : "text-charcoal/50 group-hover:text-charcoal/80"}`}
                        />
                        <span
                          className={`whitespace-nowrap transition-opacity duration-200 ${
                            collapsed ? "pointer-events-none opacity-0" : "opacity-100"
                          } ${active ? "font-semibold" : ""}`}
                        >
                          {item.label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

function SidebarBrand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link
      to={portalHomePath()}
      aria-label="AxizPOS Business home"
      className={`flex h-16 shrink-0 items-center overflow-hidden border-b border-line outline-none focus-visible:bg-charcoal/[0.03] ${collapsed ? "justify-center px-2" : "px-[22px]"}`}
    >
      <BrandLogo variant={collapsed ? "mark" : "wordmark"} tone="light" alt="" className={collapsed ? "h-8 w-8" : "h-8 max-w-full"} />
    </Link>
  );
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
  subscriptionLocked = false,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  subscriptionLocked?: boolean;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const sections = useSectionExpansion();

  useEffect(() => {
    if (!collapsed) setTip(null);
  }, [collapsed]);

  useEffect(() => {
    if (!mobileOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseMobile();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen, onCloseMobile]);

  return (
    <>
      <aside
        className={`relative z-20 hidden shrink-0 flex-col border-r border-line bg-white transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none lg:flex ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        <SidebarBrand collapsed={collapsed} />
        <SidebarNav instance="rail" collapsed={collapsed} groups={sections.groups} isOpen={sections.isOpen} onToggle={sections.toggle} onTip={setTip} subscriptionLocked={subscriptionLocked} />
      </aside>

      {tip ? (
        <div
          role="tooltip"
          style={{ top: tip.top }}
          className="sidebar-tip pointer-events-none fixed left-[88px] z-50 -translate-y-1/2 whitespace-nowrap rounded-md bg-charcoal px-2.5 py-1.5 text-xs font-medium text-white shadow-lg"
        >
          <span aria-hidden="true" className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 bg-charcoal" />
          {tip.label}
        </div>
      ) : null}

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="drawer-backdrop absolute inset-0 bg-charcoal/40 backdrop-blur-[2px]" onClick={onCloseMobile} />
          <div className="sidebar-sheet absolute inset-y-0 left-0 flex w-[min(288px,86vw)] flex-col border-r border-line bg-white shadow-2xl">
            <div className="relative">
              <SidebarBrand collapsed={false} />
              <button
                ref={closeRef}
                type="button"
                onClick={onCloseMobile}
                aria-label="Close navigation"
                className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-charcoal/60 hover:bg-charcoal/[0.05] hover:text-charcoal"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <div className="border-b border-line px-4 py-3 md:hidden">
              <StoreSwitcher />
            </div>
            <SidebarNav instance="drawer" collapsed={false} groups={sections.groups} isOpen={sections.isOpen} onToggle={sections.toggle} onNavigate={onCloseMobile} subscriptionLocked={subscriptionLocked} />
          </div>
        </div>
      ) : null}
    </>
  );
}
