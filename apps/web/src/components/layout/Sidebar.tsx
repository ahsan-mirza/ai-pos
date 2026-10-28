import { BrandLogo } from "@ai-pos/ui";
import { LogOut, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState, type FocusEvent, type MouseEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTenant } from "../../context/TenantContext";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { portalHomePath } from "../../lib/portal-home";
import { useCapabilities } from "../../lib/capabilities";
import { useCanManageSettings } from "../../lib/currency";
import { AiMark } from "../ui/AiMark";
import { ProfileAvatar } from "../ui/ProfileAvatar";
import { labelOf, navGroups, settingsTabAllowed, settingsTabs, type NavGroup, type NavItem } from "./navigation";
import { StoreSwitcher } from "./StoreSwitcher";

type VisibleItem = NavItem & { label: string };

/** The groups this user may open for this business type, with names resolved for it. */
function useVisibleGroups(): { label: NavGroup["label"]; items: VisibleItem[] }[] {
  const { can } = useAuth();
  const canManageSettings = useCanManageSettings();
  const superAdmin = useIsSuperAdmin();
  const capabilities = useCapabilities();
  const tenant = useTenant();
  const gate = { can, canManageSettings, superAdmin, has: capabilities.has, allows: tenant.allows };
  return navGroups
    .map((group) => ({
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

type TipHandler = (tip: Tip | null) => void;

function tipEvents(collapsed: boolean, onTip: TipHandler | undefined, label: ReactNode) {
  if (!collapsed || !onTip) return {};
  const show = (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label, top: rect.top + rect.height / 2 });
  };
  const hide = () => onTip(null);
  return { onMouseEnter: show, onMouseLeave: hide, onFocus: show, onBlur: hide };
}

/** The signed-in admin, shown only here: name and role when expanded, an avatar with a tooltip when collapsed. */
function SidebarProfile({ collapsed, onTip }: { collapsed: boolean; onTip?: TipHandler }) {
  const { user, logout } = useAuth();
  if (user === null) return null;
  const details = (
    <>
      <span className="block font-semibold">{user.full_name}</span>
      <span className="block text-[11px] font-normal text-white/70">
        {user.role.name} · @{user.username}
      </span>
    </>
  );

  return (
    <div className="shrink-0 space-y-1 border-t border-line p-3">
      <div
        tabIndex={collapsed ? 0 : undefined}
        role={collapsed ? "img" : undefined}
        aria-label={collapsed ? `Signed in as ${user.full_name}, ${user.role.name}` : undefined}
        title={collapsed ? undefined : `${user.full_name} · ${user.role.name}`}
        {...tipEvents(collapsed, onTip, details)}
        className={`flex items-center gap-3 overflow-hidden rounded-xl px-2.5 py-2 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 ${
          collapsed ? "" : "bg-[#f8fafc] ring-1 ring-line"
        }`}
      >
        <ProfileAvatar name={user.full_name} url={user.avatar_url} />
        <span className={`min-w-0 transition-opacity duration-200 ${collapsed ? "pointer-events-none opacity-0" : "opacity-100"}`}>
          <span className="block truncate text-[13px] font-semibold">{user.full_name}</span>
          <span className="block truncate text-[11px] text-charcoal/50">{user.role.name}</span>
        </span>
      </div>
      <Link
        to="/account"
        aria-label={collapsed ? "Your account" : undefined}
        {...tipEvents(collapsed, onTip, "Your account")}
        className="group flex h-10 w-full items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium text-charcoal/70 outline-none transition-colors hover:bg-charcoal/[0.04] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <UserRound size={16} strokeWidth={1.75} className="shrink-0" aria-hidden="true" />
        <span className={`truncate transition-opacity duration-200 ${collapsed ? "opacity-0" : "opacity-100"}`}>Your account</span>
      </Link>
      <button
        type="button"
        onClick={logout}
        aria-label={collapsed ? "Sign out" : undefined}
        {...tipEvents(collapsed, onTip, "Sign out")}
        className="group flex h-10 w-full items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium text-charcoal/70 outline-none transition-colors hover:bg-charcoal/[0.04] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <LogOut size={18} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-charcoal/50 group-hover:text-charcoal/80" />
        <span className={`whitespace-nowrap transition-opacity duration-200 ${collapsed ? "opacity-0" : "opacity-100"}`}>
          Sign out
        </span>
      </button>
    </div>
  );
}

function SidebarNav({
  collapsed,
  onNavigate,
  onTip,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  onTip?: (tip: Tip | null) => void;
}) {
  const { pathname, hash } = useLocation();
  const groups = useVisibleGroups();

  const showTip = (item: VisibleItem) => (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    if (!collapsed || !onTip) return;
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label: item.label, top: rect.top + rect.height / 2 });
  };
  const hideTip = () => onTip?.(null);

  return (
    <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4" onScroll={hideTip}>
      {groups.map((group, index) => (
        <div key={group.label} className={index ? "mt-5" : ""}>
          <div className="relative mb-1 h-6" aria-hidden={collapsed}>
            <span
              className={`absolute inset-0 flex items-center px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-charcoal/40 transition-opacity duration-200 ${
                collapsed ? "opacity-0" : "opacity-100"
              }`}
            >
              {group.label}
            </span>
            <span
              className={`absolute inset-x-3 top-1/2 h-px bg-line transition-opacity duration-200 ${
                collapsed && index ? "opacity-100" : "opacity-0"
              }`}
            />
          </div>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const active = item.isActive(pathname, hash);
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={onNavigate}
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
        </div>
      ))}
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
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

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
        <SidebarNav collapsed={collapsed} onTip={setTip} />
        <SidebarProfile collapsed={collapsed} onTip={setTip} />
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
            <SidebarNav collapsed={false} onNavigate={onCloseMobile} />
            <SidebarProfile collapsed={false} />
          </div>
        </div>
      ) : null}
    </>
  );
}
